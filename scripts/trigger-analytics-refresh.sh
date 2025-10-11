#!/bin/bash

# CocktailDB Analytics Refresh Script
# Manually triggers the analytics refresh Lambda function for a given environment

set -e  # Exit on any error

# Parse arguments
TARGET_ENV="$1"

# Default to dev if no environment specified
if [ -z "$TARGET_ENV" ]; then
    echo "No environment specified, defaulting to 'dev'."
    TARGET_ENV="dev"
fi

# Validate environment
if [ "$TARGET_ENV" != "dev" ] && [ "$TARGET_ENV" != "prod" ]; then
    echo "Error: Invalid environment '$TARGET_ENV'. Use 'dev' or 'prod'."
    exit 1
fi

# Change to project root
cd "$(dirname "$0")/.."

# Define deployment variables
STACK_NAME="cocktail-db-${TARGET_ENV}"
REGION="us-east-1"

echo "Triggering analytics refresh for environment: $TARGET_ENV"
echo "Stack name: $STACK_NAME"
echo ""

# Get the analytics refresh function ARN from CloudFormation outputs
echo "Getting Analytics Refresh Function ARN..."
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='AnalyticsRefreshFunctionArn'].OutputValue" \
    --output text \
    --region "$REGION")

if [ -z "$FUNCTION_ARN" ] || [ "$FUNCTION_ARN" = "None" ]; then
    echo "Error: Could not retrieve Analytics Refresh Function ARN from CloudFormation outputs"
    echo "Please check if the stack '$STACK_NAME' exists and has been deployed successfully"
    exit 1
fi

echo "Found function ARN: $FUNCTION_ARN"
echo ""

# Invoke the Lambda function
echo "Invoking analytics refresh function..."
RESPONSE=$(aws lambda invoke \
    --function-name "$FUNCTION_ARN" \
    --invocation-type RequestResponse \
    --region "$REGION" \
    --payload '{}' \
    /dev/stdout 2>&1)

# Check if invocation succeeded
if [ $? -ne 0 ]; then
    echo "Error invoking Lambda function"
    echo "$RESPONSE"
    exit 1
fi

echo "Lambda function invoked successfully!"
echo ""
echo "Response:"
echo "$RESPONSE" | tail -n 1 | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "Analytics refresh completed successfully!"
