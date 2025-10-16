#!/bin/bash
# Start a local development server for testing the cocktail database frontend
# Serves static files from src/web/ directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WEB_DIR="$PROJECT_ROOT/src/web"
PORT="${1:-8000}"

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
if ! grep -q "localhost" "$CONFIG_FILE"; then
    echo "⚠️  Warning: config.js doesn't appear to be configured for local development"
    echo "Run './scripts/local-config.sh' to generate local config"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 Starting local development server..."
echo ""
echo "📂 Serving from: $WEB_DIR"
echo "🌐 URL: http://localhost:$PORT"
echo ""
echo "💡 Tips:"
echo "  - Press Ctrl+C to stop the server"
echo "  - Changes to HTML/CSS/JS will be visible on page refresh"
echo "  - Authentication will use the dev Cognito user pool"
echo "  - API requests will go to the dev backend"
echo ""
echo "🔧 For hot-reloading, consider using: npx live-server src/web --port=$PORT"
echo ""

cd "$WEB_DIR"

# Use Python's built-in HTTP server
python3 -m http.server "$PORT"
