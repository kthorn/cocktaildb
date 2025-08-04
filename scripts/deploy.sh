#!/bin/bash

# CocktailDB Deployment Script for Linux/macOS
# Equivalent to deploy.bat for Unix-like systems

set -e  # Exit on any error

# Parse arguments
TARGET_ENV="$1"
NO_BUILD=0

# Default to dev if no environment specified
if [ -z "$TARGET_ENV" ]; then
    echo "No environment specified, defaulting to 'dev'."
    TARGET_ENV="dev"
elif [ "$TARGET_ENV" = "--no-build" ]; then
    echo "Error: Please specify environment first, e.g., dev --no-build"
    exit 1
else
    echo "Target environment: $TARGET_ENV"
fi

# Check for no-build flag
if [ "$2" = "--no-build" ]; then
    NO_BUILD=1
    echo "Skipping SAM build and deploy steps..."
fi

# Validate environment
if [ "$TARGET_ENV" != "dev" ] && [ "$TARGET_ENV" != "prod" ]; then
    echo "Error: Invalid environment '$TARGET_ENV'. Use 'dev' or 'prod'."
    exit 1
fi

# Validate HOSTED_ZONE_ID for prod deployments
if [ "$TARGET_ENV" = "prod" ]; then
    if [ -z "$HOSTED_ZONE_ID" ]; then
        echo "ERROR: HOSTED_ZONE_ID environment variable required for prod deployment."
        echo "Please set the HOSTED_ZONE_ID environment variable to the Route 53 Hosted Zone ID for the domain you want to use."
        exit 1
    fi
else
    if [ -z "$HOSTED_ZONE_ID" ]; then
        echo "WARNING: HOSTED_ZONE_ID not set for dev. Using placeholder."
        HOSTED_ZONE_ID="NONE"
    fi
fi

# Change to project root
cd "$(dirname "$0")/.."

# Define deployment variables
STACK_NAME="cocktail-db-${TARGET_ENV}"
REGION="us-east-1"
DB_NAME_PARAM="cocktaildb-${TARGET_ENV}"
USER_POOL_NAME_PARAM="CocktailDB-UserPool-${TARGET_ENV}-v2"
AUTH_CERT_ARN="arn:aws:acm:us-east-1:732940910135:certificate/ef4e8b26-0806-4d73-80a1-682201322d1f"
PARAM_OVERRIDES="Environment=${TARGET_ENV} HostedZoneId=${HOSTED_ZONE_ID} DatabaseName=${DB_NAME_PARAM} UserPoolName=${USER_POOL_NAME_PARAM} AuthCertificateArn=${AUTH_CERT_ARN}"

echo "Stack name: $STACK_NAME"

# Build and deploy with SAM (if not skipped)
if [ $NO_BUILD -eq 0 ]; then
    echo "Building application with SAM..."
    sam build --template-file template.yaml --region "$REGION"
    
    if [ $? -ne 0 ]; then
        echo "Error building with SAM"
        exit 1
    fi

    echo "Deploying with SAM to $TARGET_ENV environment..."
    sam deploy \
        --template-file .aws-sam/build/template.yaml \
        --stack-name "$STACK_NAME" \
        --parameter-overrides $PARAM_OVERRIDES \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
        --no-fail-on-empty-changeset \
        --resolve-s3 \
        --on-failure DELETE \
        --region "$REGION"

    if [ $? -ne 0 ]; then
        echo "Error deploying with SAM to $TARGET_ENV"
        exit 1
    fi

    echo "Deployment to $TARGET_ENV complete!"
else
    echo "Skipped SAM build and deploy steps for $STACK_NAME"
fi

# Get S3 bucket name for web content
echo "Getting S3 bucket name..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='WebsiteBucketName'].OutputValue" \
    --output text \
    --region "$REGION")

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
    echo "Error: Could not retrieve bucket name from CloudFormation outputs for stack $STACK_NAME"
    echo "Please check if the stack deployment completed successfully"
    exit 1
fi

echo "Found bucket name: $BUCKET_NAME"

# Generate config.js using Python script
echo "Generating config.js..."
python scripts/generate_config.py "$STACK_NAME" "$TARGET_ENV" --region "$REGION"
if [ $? -ne 0 ]; then
    echo "Error generating config.js"
    exit 1
fi

# Upload web content to S3
echo "Uploading web content to S3..."
aws s3 sync src/web/ "s3://$BUCKET_NAME/" --delete --region "$REGION"
if [ $? -ne 0 ]; then
    echo "Error uploading web content"
    exit 1
fi

echo "Web content uploaded successfully!"

# Invalidate CloudFront cache
echo "Invalidating CloudFront cache..."
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistribution'].OutputValue" \
    --output text \
    --region "$REGION")

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
    aws cloudfront create-invalidation \
        --distribution-id "$DISTRIBUTION_ID" \
        --paths "/*" \
        --region "$REGION"
    echo "CloudFront cache invalidation initiated!"
else
    echo "Warning: Could not retrieve CloudFront distribution ID"
fi

# Display final CloudFormation outputs
echo ""
echo "CloudFormation stack outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs" \
    --output table \
    --region "$REGION"

echo ""
echo "Deployment completed successfully!"