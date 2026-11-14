#!/bin/bash
# Generate a local development config.js that points to the dev API.
# Values come from the dev Ansible inventory, the same source the deployment
# uses, so no AWS credentials are needed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_PATH="$PROJECT_ROOT/src/web/js/config.js"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" "$SCRIPT_DIR/generate_config.py" dev \
    --app-url "http://localhost:8000" \
    --app-name "Cocktail Database (local dev)" \
    --output "$CONFIG_PATH"

echo ""
echo "🚀 Next steps:"
echo "  1. Run: ./scripts/serve.sh"
echo "  2. Open: http://localhost:8000"
