#!/bin/bash
# infrastructure/scripts/trigger-analytics.sh
# Trigger analytics refresh on EC2 instance
#
# Usage:
#   ./trigger-analytics.sh           # Run in foreground
#   ./trigger-analytics.sh --bg      # Run via systemd (background)
#   ./trigger-analytics.sh --status  # Check last run status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-/opt/cocktaildb}"

usage() {
    echo "Usage: $0 [--bg|--status|--help]"
    echo ""
    echo "Options:"
    echo "  (no args)   Run analytics refresh in foreground"
    echo "  --bg        Run via systemd timer (background)"
    echo "  --status    Show status of last analytics run"
    echo "  --help      Show this help message"
}

run_foreground() {
    echo "=== Running Analytics Refresh ==="
    echo "Working directory: $APP_HOME"
    echo ""

    cd "$APP_HOME"

    # Run via docker compose
    docker compose run --rm api python -m analytics.analytics_refresh

    echo ""
    echo "=== Analytics Refresh Complete ==="
}

run_background() {
    echo "Starting analytics refresh via systemd..."
    sudo systemctl start cocktaildb-analytics.service
    echo "Job started. Check status with: $0 --status"
}

show_status() {
    echo "=== Analytics Service Status ==="
    systemctl status cocktaildb-analytics.service --no-pager || true

    echo ""
    echo "=== Recent Logs ==="
    journalctl -u cocktaildb-analytics.service -n 20 --no-pager || true

    echo ""
    echo "=== Timer Status ==="
    systemctl status cocktaildb-analytics.timer --no-pager || true
}

# Parse arguments
case "${1:-}" in
    --bg)
        run_background
        ;;
    --status)
        show_status
        ;;
    --help|-h)
        usage
        ;;
    "")
        run_foreground
        ;;
    *)
        echo "Unknown option: $1"
        usage
        exit 1
        ;;
esac
