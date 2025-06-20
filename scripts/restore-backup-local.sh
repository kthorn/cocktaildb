#!/bin/bash

# Simple script to download backup locally and restore to dev environment
# This avoids cross-environment coupling

set -e

BACKUP_BUCKET="cocktail-db-prod-db-backups"
BACKUP_FILE=""  # Will be auto-detected if not specified
TARGET_ENVIRONMENT="dev"
REGION="us-east-1"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        -t|--target)
            TARGET_ENVIRONMENT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [-f backup_file] [-t target_env]"
            echo "  -f, --file: Backup file name (default: latest backup)"
            echo "  -t, --target: Target environment (default: dev)"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

# Auto-detect latest backup file if not specified
if [ -z "$BACKUP_FILE" ]; then
    echo "Finding latest backup file from $BACKUP_BUCKET..."
    BACKUP_FILE=$(aws s3 ls "s3://$BACKUP_BUCKET/" --region "$REGION" | sort | tail -n 1 | awk '{print $4}')
    if [ -z "$BACKUP_FILE" ]; then
        echo "Error: No backup files found in bucket $BACKUP_BUCKET"
        exit 1
    fi
    echo "Latest backup file: $BACKUP_FILE"
fi

echo "Downloading backup $BACKUP_FILE from $BACKUP_BUCKET..."

# Download backup to temp file
TEMP_FILE="/tmp/backup_restore_$$.db"
aws s3 cp "s3://$BACKUP_BUCKET/$BACKUP_FILE" "$TEMP_FILE" --region "$REGION"

echo "Backup downloaded. Size: $(stat -c%s "$TEMP_FILE") bytes"

# Encode backup as base64
echo "Encoding backup data..."
BACKUP_DATA_B64=$(base64 -w 0 "$TEMP_FILE")

# Create Lambda payload file
LAMBDA_FUNCTION="cocktail-db-$TARGET_ENVIRONMENT-schema-deploy"
PAYLOAD_FILE="/tmp/restore_payload_$$.json"

cat > "$PAYLOAD_FILE" << EOF
{
  "DBName": "cocktaildb-$TARGET_ENVIRONMENT",
  "BackupData": "$BACKUP_DATA_B64"
}
EOF

echo "Invoking Lambda function $LAMBDA_FUNCTION..."

# Invoke Lambda using payload file
OUTPUT_FILE="/tmp/restore_output_$$.json"
aws lambda invoke \
    --function-name "$LAMBDA_FUNCTION" \
    --payload "file://$PAYLOAD_FILE" \
    --cli-binary-format raw-in-base64-out \
    --region "$REGION" \
    "$OUTPUT_FILE"

echo "Lambda invocation completed. Output:"
cat "$OUTPUT_FILE"
echo

# Cleanup
rm -f "$TEMP_FILE" "$PAYLOAD_FILE" "$OUTPUT_FILE"

echo "Restore completed!"