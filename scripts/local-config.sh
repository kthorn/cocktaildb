#!/bin/bash
# Generate a local development config.js that points to the dev API
# This allows testing frontend changes locally without deploying

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_PATH="$PROJECT_ROOT/src/web/js/config.js"
STACK_NAME="${1:-cocktail-db-dev}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Get dev API endpoint from CloudFormation
echo "🔧 Fetching dev API endpoint from CloudFormation..."
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)

# Get Cognito configuration
echo "🔐 Fetching Cognito configuration..."
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
    --output text)

COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoDomainURLV3`].OutputValue' \
    --output text)

# Check if we got all values
if [ -z "$API_URL" ] || [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ] || [ -z "$COGNITO_DOMAIN" ]; then
    echo "❌ Error: Could not retrieve all required configuration values"
    exit 1
fi

# Serialize through the same validated public-config renderer used by the CLI.
echo "📝 Writing config.js..."
CONFIG_CONTENT=$(
    API_URL="$API_URL" \
        USER_POOL_ID="$USER_POOL_ID" \
        CLIENT_ID="$CLIENT_ID" \
        COGNITO_DOMAIN="$COGNITO_DOMAIN" \
        PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$PYTHON_BIN" - <<'PY'
import os
import sys

from scripts.generate_config import render_public_config

try:
    sys.stdout.write(
        render_public_config(
            {
                "apiUrl": os.environ["API_URL"],
                "userPoolId": os.environ["USER_POOL_ID"],
                "clientId": os.environ["CLIENT_ID"],
                "cognitoDomain": os.environ["COGNITO_DOMAIN"],
                "appUrl": "http://localhost:8000",
                "appName": "Cocktail Database (local dev)",
            }
        )
    )
except ValueError as error:
    print(f"Error: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
)
printf '%s' "$CONFIG_CONTENT" >"$CONFIG_PATH"

echo "✅ Config generated successfully!"
echo "  Remote API configured; local app URL: http://localhost:8000"
echo ""
echo "🚀 Next steps:"
echo "  1. Start local server: ./scripts/serve.sh"
echo "  2. Open browser: http://localhost:8000"
echo "  3. Test your changes!"
echo ""
echo "⚠️  Remember: Don't commit config.js changes to git"
