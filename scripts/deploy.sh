#!/bin/bash

# Exit on error
set -e

# Check if environment is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <environment>"
    echo "Environment must be one of: dev, staging, prod"
    exit 1
fi

ENVIRONMENT=$1

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo "Invalid environment. Must be one of: dev, staging, prod"
    exit 1
fi

# Build the application
echo "Building application..."
sam build

# Deploy the application
echo "Deploying to $ENVIRONMENT environment..."
sam deploy \
    --stack-name cocktail-db-$ENVIRONMENT \
    --parameter-overrides Environment=$ENVIRONMENT \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset

echo "Deployment complete!" 