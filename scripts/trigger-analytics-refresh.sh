#!/bin/bash

# CocktailDB Analytics Refresh Script
# Triggers the analytics Batch job via the trigger Lambda

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

# Get the analytics trigger function ARN from CloudFormation outputs
echo "Getting Analytics Trigger Function ARN..."
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='AnalyticsTriggerFunctionArn'].OutputValue" \
    --output text \
    --region "$REGION")

if [ -z "$FUNCTION_ARN" ] || [ "$FUNCTION_ARN" = "None" ]; then
    echo "Error: Could not retrieve Analytics Trigger Function ARN from CloudFormation outputs"
    echo "Please check if the stack '$STACK_NAME' exists and has been deployed successfully"
    exit 1
fi

echo "Found function ARN: $FUNCTION_ARN"
echo ""

# Invoke the trigger Lambda function
echo "Invoking analytics trigger function..."

# Create temporary file for response
RESPONSE_FILE=$(mktemp)
trap "rm -f $RESPONSE_FILE" EXIT

# Invoke Lambda and capture response to file
INVOKE_OUTPUT=$(aws lambda invoke \
    --function-name "$FUNCTION_ARN" \
    --invocation-type RequestResponse \
    --region "$REGION" \
    --payload '{}' \
    "$RESPONSE_FILE" 2>&1)

# Check if invocation succeeded
if [ $? -ne 0 ]; then
    echo "Error invoking Lambda function"
    echo "$INVOKE_OUTPUT"
    exit 1
fi

echo "Trigger Lambda invoked successfully!"
echo ""

# Read response from file
RESPONSE_JSON=$(cat "$RESPONSE_FILE")
echo "Response:"
echo "$RESPONSE_JSON" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_JSON"
echo ""

# Extract job ID from response
# Lambda returns {statusCode: 200, body: '{"jobId": "..."}'}
JOB_ID=$(echo "$RESPONSE_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Check if body exists and is a string (API Gateway format)
    if 'body' in data and isinstance(data['body'], str):
        body = json.loads(data['body'])
        print(body.get('jobId', ''))
    # Check if jobId is directly in response
    elif 'jobId' in data:
        print(data['jobId'])
    else:
        print('')
except:
    print('')
" 2>/dev/null)

if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "None" ]; then
    echo "Warning: Could not extract job ID from response. Cannot track job status."
    echo "Batch job submitted! Check AWS Batch console for job status."
    echo "Job queue: cocktail-db-${TARGET_ENV}-analytics"
    exit 0
fi

echo "Batch job submitted with ID: $JOB_ID"
echo "Job queue: cocktail-db-${TARGET_ENV}-analytics"
echo ""
echo "Tracking job status (polling every 30 seconds)..."
echo ""

# Poll job status until terminal state
PREV_STATUS=""
POLL_INTERVAL=30

while true; do
    # Get current job status
    JOB_INFO=$(aws batch describe-jobs \
        --jobs "$JOB_ID" \
        --region "$REGION" \
        --query 'jobs[0].[status,statusReason]' \
        --output json 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$JOB_INFO" ]; then
        echo "Error: Failed to retrieve job status"
        exit 1
    fi

    CURRENT_STATUS=$(echo "$JOB_INFO" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0] if data else 'UNKNOWN')")
    STATUS_REASON=$(echo "$JOB_INFO" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[1] if len(data) > 1 and data[1] else '')")

    # Report status change
    if [ "$CURRENT_STATUS" != "$PREV_STATUS" ]; then
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        if [ -n "$STATUS_REASON" ]; then
            echo "[$TIMESTAMP] Status: $CURRENT_STATUS - $STATUS_REASON"
        else
            echo "[$TIMESTAMP] Status: $CURRENT_STATUS"
        fi
        PREV_STATUS="$CURRENT_STATUS"
    fi

    # Check for terminal states
    case "$CURRENT_STATUS" in
        SUCCEEDED)
            echo ""
            echo "Analytics refresh completed successfully!"
            exit 0
            ;;
        FAILED)
            echo ""
            echo "Analytics refresh failed!"
            echo "Check CloudWatch logs for details."
            exit 1
            ;;
        UNKNOWN)
            echo "Error: Could not determine job status"
            exit 1
            ;;
    esac

    # Wait before next poll
    sleep $POLL_INTERVAL
done
