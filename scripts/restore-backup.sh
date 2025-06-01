#!/bin/bash

# Database restore script for CocktailDB
# Downloads backups from S3 and restores them to target environment

set -e  # Exit on any error

# Default values
TARGET_ENVIRONMENT="dev"
SOURCE_ENVIRONMENT="prod"
BACKUP_FILE="latest"
BACKUP_BUCKET=""
REGION="us-east-1"
LIST_BACKUPS=false
DRY_RUN=false
FORCE=false

# Help function
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Restore CocktailDB database from S3 backup to target environment.

Options:
  -t, --target ENV         Target environment (dev or prod, default: dev)
  -s, --source ENV         Source environment for backups (dev or prod, default: prod)
  -f, --file BACKUP        Backup file name or 'latest' (default: latest)
  -b, --bucket BUCKET      S3 backup bucket (auto-detected if not provided)
  -r, --region REGION      AWS region (default: us-east-1)
  -l, --list               List available backups and exit
  -d, --dry-run            Show what would be done without executing
  --force                  Skip confirmation for prod restoration
  -h, --help               Show this help message

Examples:
  # List available backups
  $0 --list

  # Restore latest prod backup to dev (most common use case)
  $0 --target dev --source prod

  # Restore specific backup to dev
  $0 --target dev --file backup-2024-01-15_10-30-00.db

  # Restore to prod (requires confirmation)
  $0 --target prod --source prod

  # Restore to prod with force (no confirmation)
  $0 --target prod --source prod --force

  # Dry run - see what would happen
  $0 --target dev --dry-run
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--target)
            TARGET_ENVIRONMENT="$2"
            if [[ "$TARGET_ENVIRONMENT" != "dev" && "$TARGET_ENVIRONMENT" != "prod" ]]; then
                echo "Error: Target environment must be 'dev' or 'prod'"
                exit 1
            fi
            shift 2
            ;;
        -s|--source)
            SOURCE_ENVIRONMENT="$2"
            if [[ "$SOURCE_ENVIRONMENT" != "dev" && "$SOURCE_ENVIRONMENT" != "prod" ]]; then
                echo "Error: Source environment must be 'dev' or 'prod'"
                exit 1
            fi
            shift 2
            ;;
        -f|--file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        -b|--bucket)
            BACKUP_BUCKET="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -l|--list)
            LIST_BACKUPS=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set environment-specific defaults
SOURCE_STACK_NAME="cocktail-db-${SOURCE_ENVIRONMENT}"
TARGET_STACK_NAME="cocktail-db-${TARGET_ENVIRONMENT}"

if [ -z "$BACKUP_BUCKET" ]; then
    # Use the actual backup bucket naming pattern from the CloudFormation template
    BACKUP_BUCKET="cocktail-db-${SOURCE_ENVIRONMENT}-db-backups"
fi

echo "=== Database Restore Configuration ==="
echo "Source Environment: $SOURCE_ENVIRONMENT"
echo "Target Environment: $TARGET_ENVIRONMENT"
echo "Backup Bucket: $BACKUP_BUCKET"
echo "Backup File: $BACKUP_FILE"
echo "Region: $REGION"
echo "Dry Run: $DRY_RUN"
echo "====================================="

# Function to format file size
format_file_size() {
    local size=$1
    if [ $size -gt 1073741824 ]; then
        echo "$(echo "scale=2; $size / 1073741824" | bc) GB"
    elif [ $size -gt 1048576 ]; then
        echo "$(echo "scale=2; $size / 1048576" | bc) MB"
    elif [ $size -gt 1024 ]; then
        echo "$(echo "scale=2; $size / 1024" | bc) KB"
    else
        echo "${size} B"
    fi
}

# Function to list available backups
list_backups() {
    echo "Listing available backups in s3://$BACKUP_BUCKET..."
    
    # Get list of backup files
    local backup_list=$(aws s3 ls "s3://$BACKUP_BUCKET/" --region "$REGION" | grep "backup-.*\.db$" | sort -r)
    
    if [ -z "$backup_list" ]; then
        echo "No backups found in bucket."
        return 1
    fi
    
    echo ""
    echo "Available backups (newest first):"
    echo "Date                Size        File Name"
    echo "---                 ----        ---------"
    
    while IFS= read -r line; do
        if [[ $line =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2})\ +([0-9]+)\ +(backup-.+\.db) ]]; then
            date_part="${BASH_REMATCH[1]}"
            size_part="${BASH_REMATCH[2]}"
            file_part="${BASH_REMATCH[3]}"
            formatted_size=$(format_file_size "$size_part")
            printf "%-19s %10s %s\n" "$date_part" "$formatted_size" "$file_part"
        fi
    done <<< "$backup_list"
    
    return 0
}

# Function to get latest backup
get_latest_backup() {
    local latest=$(aws s3 ls "s3://$BACKUP_BUCKET/" --region "$REGION" | grep "backup-.*\.db$" | sort -r | head -1)
    if [[ $latest =~ backup-.+\.db ]]; then
        echo "${BASH_REMATCH[0]}"
    else
        echo ""
    fi
}

# Function to check if backup exists
backup_exists() {
    local backup_file="$1"
    aws s3 ls "s3://$BACKUP_BUCKET/$backup_file" --region "$REGION" >/dev/null 2>&1
}

# Function to restore database
restore_database() {
    local backup_bucket="$1"
    local backup_file="$2"
    local target_env="$3"
    local region="$4"
    local is_dry_run="$5"
    
    local target_stack_name="cocktail-db-$target_env"
    local lambda_function_name="$target_stack_name-schema-deploy"
    local db_name="cocktaildb-$target_env"
    
    # Generate a unique RequestId
    local request_id="restore-invoke-$(uuidgen 2>/dev/null || date +%s)"
    
    # Get stack ID
    echo "Retrieving stack ID for $target_stack_name..."
    local stack_id=$(aws cloudformation describe-stacks \
        --stack-name "$target_stack_name" \
        --region "$region" \
        --query "Stacks[0].StackId" \
        --output text 2>/dev/null || echo "None")
    
    if [ "$stack_id" = "None" ] || [ -z "$stack_id" ]; then
        local account_id=$(aws sts get-caller-identity --query "Account" --output text)
        stack_id="arn:aws:cloudformation:${region}:${account_id}:stack/${target_stack_name}/placeholder-stack-id"
        echo "Using placeholder stack ID: $stack_id"
    fi
    
    # Create JSON payload
    local payload=$(cat << EOF
{
  "RequestType": "Update",
  "StackId": "$stack_id",
  "RequestId": "$request_id",
  "LogicalResourceId": "SchemaDeployResource",
  "ResourceProperties": {
    "DBName": "$db_name",
    "ForceInit": "true",
    "RestoreFromS3": "true",
    "BackupS3Bucket": "$backup_bucket",
    "BackupS3Key": "$backup_file"
  }
}
EOF
)
    
    if [ "$is_dry_run" = true ]; then
        echo ""
        echo "=== DRY RUN - Would execute the following ==="
        echo "Lambda Function: $lambda_function_name"
        echo "Payload:"
        echo "$payload" | jq .
        echo "============================================="
        return 0
    fi
    
    echo ""
    echo "Restoring database from backup..."
    echo "Target Lambda: $lambda_function_name"
    echo "Backup: s3://$backup_bucket/$backup_file"
    
    local output_file="restore-output.txt"
    local temp_payload_file=$(mktemp)
    
    # Cleanup function for this restoration
    cleanup_restore() {
        if [ -f "$temp_payload_file" ]; then
            rm -f "$temp_payload_file"
        fi
    }
    
    # Write payload to temp file and invoke Lambda
    echo "$payload" > "$temp_payload_file"
    
    echo "Invoking Lambda function for database restoration..."
    
    if aws lambda invoke \
        --function-name "$lambda_function_name" \
        --payload "file://$temp_payload_file" \
        --cli-binary-format raw-in-base64-out \
        --region "$region" \
        "$output_file"; then
        
        echo "Restoration command executed."
        echo "Output written to '$output_file'. Check this file for details."
        
        if [ -f "$output_file" ]; then
            echo "--- Restoration Result ---"
            cat "$output_file"
            echo ""
            echo "-------------------------"
            
            # Check if restoration was successful
            if grep -q '"errorMessage"' "$output_file"; then
                echo "Restoration failed. Check the error message above."
                cleanup_restore
                return 1
            else
                echo "Database restoration completed successfully!"
                cleanup_restore
                return 0
            fi
        fi
        
        cleanup_restore
        return 0
    else
        echo "Error during Lambda invocation"
        cleanup_restore
        return 1
    fi
}

# Main execution
main() {
    # List backups if requested
    if [ "$LIST_BACKUPS" = true ]; then
        list_backups
        exit $?
    fi
    
    # Check if we can access the bucket
    if ! aws s3 ls "s3://$BACKUP_BUCKET/" --region "$REGION" >/dev/null 2>&1; then
        echo "Error: Cannot access backup bucket s3://$BACKUP_BUCKET/"
        echo "Please check your AWS credentials and bucket permissions."
        exit 1
    fi
    
    # Get available backups
    if ! list_backups >/dev/null 2>&1; then
        echo "Error: No backups available in bucket $BACKUP_BUCKET"
        exit 1
    fi
    
    # Determine which backup to restore
    local backup_to_restore=""
    if [ "$BACKUP_FILE" = "latest" ]; then
        backup_to_restore=$(get_latest_backup)
        if [ -z "$backup_to_restore" ]; then
            echo "Error: No backups found in bucket"
            exit 1
        fi
        echo ""
        echo "Using latest backup: $backup_to_restore"
    else
        backup_to_restore="$BACKUP_FILE"
        if ! backup_exists "$backup_to_restore"; then
            echo "Error: Specified backup file '$backup_to_restore' not found in bucket"
            exit 1
        fi
        echo ""
        echo "Using specified backup: $backup_to_restore"
    fi
    
    # Safety check for prod restoration
    if [ "$TARGET_ENVIRONMENT" = "prod" ] && [ "$FORCE" = false ]; then
        echo ""
        echo "WARNING: You are about to restore data to the PRODUCTION environment!"
        echo "This will OVERWRITE the current production database!"
        echo "Use --force to bypass this confirmation."
        echo ""
        read -p "Type 'RESTORE PROD' to confirm: " confirmation
        if [ "$confirmation" != "RESTORE PROD" ]; then
            echo "Restoration cancelled."
            exit 0
        fi
    fi
    
    # Perform the restoration
    if restore_database "$BACKUP_BUCKET" "$backup_to_restore" "$TARGET_ENVIRONMENT" "$REGION" "$DRY_RUN"; then
        echo ""
        echo "Restore operation completed successfully!"
        if [ "$DRY_RUN" = false ]; then
            echo "Database in $TARGET_ENVIRONMENT environment has been restored from backup: $backup_to_restore"
        fi
    else
        echo "Restore operation failed. Check the output above for details."
        exit 1
    fi
}

# Execute main function
main "$@"