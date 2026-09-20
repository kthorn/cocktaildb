#!/bin/bash
# Start the Vite development server for the frontend.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WEB_DIR="$PROJECT_ROOT/src/web"
PORT=8000

# Check if web directory exists
if [ ! -d "$WEB_DIR" ]; then
    echo "❌ Error: Web directory not found at $WEB_DIR"
    exit 1
fi

# Check if config.js has been generated for local dev
CONFIG_FILE="$WEB_DIR/js/config.js"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  Warning: config.js not found!"
    echo "Run './scripts/local-config.sh' first to generate local config"
    exit 1
fi

# Check if config points to localhost (local development)
if ! grep -Eq "appUrl[[:space:]]*:[[:space:]]*['\"]?http://localhost:8000" "$CONFIG_FILE"; then
    echo "⚠️  Warning: config.js is remote configuration, not local appUrl http://localhost:8000"
    echo "Run './scripts/local-config.sh' to generate local config"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 Starting Vite development server on http://localhost:$PORT..."
echo ""
echo "💡 Tips:"
echo "  - Press Ctrl+C to stop the server"
echo "  - Changes to HTML/CSS/JS will be visible with hot reload"
echo "  - Authentication will use the dev Cognito user pool"
echo "  - API requests will go to the configured remote dev backend"
echo "  - Optional SSR proxy targets a local FastAPI server on port 8001"
echo ""

cd "$PROJECT_ROOT"
exec npm run dev
