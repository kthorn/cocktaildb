#!/bin/bash

# Apply database migration script for CocktailDB
# Unix/Linux equivalent of apply-migration.ps1

set -e  # Exit on any error

# Default values
ENVIRONMENT="dev"
SQL_FILE_PATH=""
LAMBDA_FUNCTION_NAME=""
DB_NAME=""
FORCE_INIT=false
STACK_ID=""
LOGICAL_RESOURCE_ID="SchemaDeployResource"
REGION="us-east-1"

# Validate environment early if provided as first argument (like deploy.sh)
if [ -n "$1" ] && [ "$1" != "-f" ] && [ "$1" != "--file" ] && [ "$1" != "-h" ] && [ "$1" != "--help" ]; then
    if [ "$1" = "dev" ] || [ "$1" = "prod" ]; then
        ENVIRONMENT="$1"
        shift
        echo "Environment set to: $ENVIRONMENT"
    fi
fi

# Help function
show_help() {
    cat << EOF
Usage: $0 -f SQL_FILE_PATH [OPTIONS]

Apply a database migration or schema to the CocktailDB database.

Required arguments:
  -f, --file SQL_FILE_PATH    Path to the SQL migration file

Optional arguments:
  -e, --env ENVIRONMENT       Environment (dev or prod, default: dev)
  -l, --lambda FUNCTION_NAME  Lambda function name (auto-detected if not provided)
  -d, --db DB_NAME            Database name (auto-detected if not provided)
  -r, --region REGION         AWS region (default: us-east-1)
  -s, --stack-id STACK_ID     CloudFormation stack ID (auto-detected if not provided)
  --force-init                Force database reinitialization
  -h, --help                  Show this help message

Examples:
  # Apply migration to dev environment (default)
  $0 -f migrations/02_migration_add_top_and_rinse_units.sql

  # Apply migration to prod environment
  $0 -f migrations/02_migration_add_top_and_rinse_units.sql -e prod
  # or
  $0 prod -f migrations/02_migration_add_top_and_rinse_units.sql

  # Force reinitialization with schema
  $0 -f schema-deploy/schema.sql --force-init

  # Specify custom lambda function
  $0 -f migration.sql -l my-custom-schema-deploy-function
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file)
            SQL_FILE_PATH="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
                echo "Error: Environment must be 'dev' or 'prod'"
                exit 1
            fi
            shift 2
            ;;
        -l|--lambda)
            LAMBDA_FUNCTION_NAME="$2"
            shift 2
            ;;
        -d|--db)
            DB_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -s|--stack-id)
            STACK_ID="$2"
            shift 2
            ;;
        --force-init)
            FORCE_INIT=true
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

# Check required arguments
if [ -z "$SQL_FILE_PATH" ]; then
    echo "Error: SQL file path is required"
    show_help
    exit 1
fi

# Validate environment (consistent with deploy.sh)
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Error: Invalid environment '$ENVIRONMENT'. Use 'dev' or 'prod'."
    exit 1
fi

# Set environment-specific defaults if not provided (consistent with deploy.sh naming)
STACK_NAME="cocktail-db-${ENVIRONMENT}"

if [ -z "$LAMBDA_FUNCTION_NAME" ]; then
    LAMBDA_FUNCTION_NAME="${STACK_NAME}-schema-deploy"
fi

if [ -z "$DB_NAME" ]; then
    DB_NAME="cocktaildb-${ENVIRONMENT}"
fi

if [ -z "$STACK_ID" ]; then
    # Try to get actual stack ID from CloudFormation
    echo "Attempting to retrieve stack ID from CloudFormation..."
    STACK_INFO=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].StackId" \
        --output text 2>/dev/null || echo "None")
    
    if [ "$STACK_INFO" != "None" ] && [ -n "$STACK_INFO" ]; then
        STACK_ID="$STACK_INFO"
        echo "Retrieved stack ID from CloudFormation: $STACK_ID"
    else
        # Fallback to placeholder format
        ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text 2>/dev/null || echo "123456789012")
        STACK_ID="arn:aws:cloudformation:${REGION}:${ACCOUNT_ID}:stack/${STACK_NAME}/placeholder-stack-id"
        echo "Using placeholder stack ID: $STACK_ID"
    fi
fi

echo "=== Migration Configuration ==="
echo "Environment: $ENVIRONMENT"
echo "Stack Name: $STACK_NAME"
echo "Lambda Function: $LAMBDA_FUNCTION_NAME"
echo "Database Name: $DB_NAME"
echo "Region: $REGION"
echo "Force Init: $FORCE_INIT"
echo "SQL File: $SQL_FILE_PATH"
echo "=============================="

# Verify stack exists before attempting migration
echo "Verifying stack '$STACK_NAME' exists..."
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Error: Stack '$STACK_NAME' not found in region $REGION"
    echo "Make sure you have deployed the stack using: ./scripts/deploy.sh $ENVIRONMENT"
    exit 1
fi
echo "Stack verified successfully."

# Check if SQL file exists
if [ ! -f "$SQL_FILE_PATH" ]; then
    echo "Error: SQL file not found at '$SQL_FILE_PATH'"
    exit 1
fi

# Read SQL content
echo "Reading SQL content from '$SQL_FILE_PATH'..."
SQL_CONTENT=$(cat "$SQL_FILE_PATH")

# Generate a unique RequestId
REQUEST_ID="manual-invoke-$(uuidgen 2>/dev/null || date +%s)"

# Determine ForceInit string value
FORCE_INIT_STRING=$([ "$FORCE_INIT" = true ] && echo "true" || echo "false")

# Create JSON payload
PAYLOAD=$(cat << EOF
{
  "RequestType": "Update",
  "StackId": "$STACK_ID",
  "RequestId": "$REQUEST_ID",
  "LogicalResourceId": "$LOGICAL_RESOURCE_ID",
  "ResourceProperties": {
    "DBName": "$DB_NAME",
    "ForceInit": "$FORCE_INIT_STRING",
    "SchemaContent": $(echo "$SQL_CONTENT" | jq -R -s .)
  }
}
EOF
)

echo "Prepared payload JSON:"
echo "$PAYLOAD" | jq .

OUTPUT_FILE="migration-output.txt"
TEMP_PAYLOAD_FILE=$(mktemp)

echo "Invoking Lambda function '$LAMBDA_FUNCTION_NAME'..."

# Cleanup function
cleanup() {
    if [ -f "$TEMP_PAYLOAD_FILE" ]; then
        rm -f "$TEMP_PAYLOAD_FILE"
        echo "Cleaned up temporary payload file: $TEMP_PAYLOAD_FILE"
    fi
}

# Set trap for cleanup
trap cleanup EXIT

try_invoke_lambda() {
    # Write payload to temporary file
    echo "$PAYLOAD" > "$TEMP_PAYLOAD_FILE"
    echo "Payload written to temporary file: $TEMP_PAYLOAD_FILE"

    # Invoke Lambda function
    aws lambda invoke \
        --function-name "$LAMBDA_FUNCTION_NAME" \
        --payload "file://$TEMP_PAYLOAD_FILE" \
        --cli-binary-format raw-in-base64-out \
        --region "$REGION" \
        "$OUTPUT_FILE"

    echo "Lambda invocation command executed."
    echo "Output (if any) written to '$OUTPUT_FILE'. Check this file for details."

    if [ -f "$OUTPUT_FILE" ]; then
        echo "--- Content of $OUTPUT_FILE ---"
        cat "$OUTPUT_FILE"
        echo ""
        echo "-------------------------------"
    fi
}

# Execute the Lambda invocation
if try_invoke_lambda; then
    echo "Script finished successfully."
else
    echo "Error during Lambda invocation"
    exit 1
fi