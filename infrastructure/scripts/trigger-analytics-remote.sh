#!/bin/bash
# infrastructure/scripts/trigger-analytics-remote.sh
# Trigger analytics refresh on a remote EC2 instance over SSH.
#
# Usage:
#   ./trigger-analytics-remote.sh [host] [--bg|--status]
#   SSH_USER=ec2-user SSH_KEY=~/.ssh/cocktaildb-ec2.pem ./trigger-analytics-remote.sh mixology.tools --bg
#   SSH_HOST=mixology.tools ./trigger-analytics-remote.sh --status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-/opt/cocktaildb}"
REMOTE_SCRIPT="${APP_HOME}/scripts/trigger-analytics.sh"

usage() {
    echo "Usage: $0 [host] [--bg|--status|--help]"
    echo ""
    echo "Environment:"
    echo "  SSH_HOST   Remote host (if not passed as [host])"
    echo "  SSH_USER   SSH user (default: ec2-user)"
    echo "  SSH_KEY    SSH private key path (optional)"
    echo "  APP_HOME   Remote app home (default: /opt/cocktaildb)"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

HOST="${1:-${SSH_HOST:-mixology.tools}}"
ACTION="${2:-}"
SSH_USER="${SSH_USER:-ec2-user}"
SSH_KEY="${SSH_KEY:-}"

SSH_OPTS=(
    -o BatchMode=yes
    -o StrictHostKeyChecking=accept-new
)

if [[ -n "${SSH_KEY}" ]]; then
    SSH_OPTS+=(-i "${SSH_KEY}")
fi

REMOTE_CMD="${REMOTE_SCRIPT}"
case "${ACTION}" in
    --bg|--status|"")
        if [[ -n "${ACTION}" ]]; then
            REMOTE_CMD="sudo -n ${REMOTE_SCRIPT} ${ACTION}"
        else
            REMOTE_CMD="sudo -n -u cocktaildb ${REMOTE_SCRIPT}"
        fi
        ;;
    --help|-h)
        REMOTE_CMD="sudo -n ${REMOTE_SCRIPT} --help"
        ;;
    *)
        echo "Unknown option: ${ACTION}"
        usage
        exit 1
        ;;
esac

ssh "${SSH_OPTS[@]}" "${SSH_USER}@${HOST}" "${REMOTE_CMD}"
