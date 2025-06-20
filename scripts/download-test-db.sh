#!/bin/bash

# Download latest production backup for local testing
# Usage: ./scripts/download-test-db.sh

set -e

echo "Downloading latest production backup for testing..."

# Create test fixtures directory
mkdir -p tests/fixtures

# Get backup bucket name from CloudFormation
echo "Finding backup bucket..."
BACKUP_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name cocktail-db-prod \
  --query "Stacks[0].Outputs[?OutputKey=='BackupBucketName'].OutputValue" \
  --output text)

if [ -z "$BACKUP_BUCKET" ] || [ "$BACKUP_BUCKET" = "None" ]; then
    echo "Error: Could not find backup bucket from cocktail-db-prod stack"
    echo "Make sure you have AWS access and the stack exists"
    exit 1
fi

echo "Backup bucket: $BACKUP_BUCKET"

# Get latest backup file
echo "Finding latest backup..."
LATEST_BACKUP=$(aws s3 ls s3://$BACKUP_BUCKET/ | grep backup- | sort -r | head -1 | awk '{print $4}')

if [ -z "$LATEST_BACKUP" ]; then
    echo "Error: No backup files found in bucket $BACKUP_BUCKET"
    exit 1
fi

echo "Latest backup: $LATEST_BACKUP"

# Download the backup
echo "Downloading backup to tests/fixtures/test_cocktaildb.db..."
aws s3 cp s3://$BACKUP_BUCKET/$LATEST_BACKUP tests/fixtures/test_cocktaildb.db

echo "✓ Database downloaded successfully!"
echo "You can now run integration tests with:"
echo "  python -m pytest tests/test_api_integration.py -v"