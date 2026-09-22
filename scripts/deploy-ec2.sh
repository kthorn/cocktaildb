#!/bin/bash
# scripts/deploy-ec2.sh
# Deploy CocktailDB to EC2 instance
#
# Usage:
#   ./scripts/deploy-ec2.sh              # Deploy to dev
#   ./scripts/deploy-ec2.sh prod         # Deploy to prod
#   ./scripts/deploy-ec2.sh --provision  # Full provision + deploy
#   ./scripts/deploy-ec2.sh --frontend-artifact dist

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ANSIBLE_DIR="${PROJECT_ROOT}/infrastructure/ansible"

# Default to dev environment
ENVIRONMENT=dev
PROVISION=false
FRONTEND_ARTIFACT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --frontend-artifact)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "--frontend-artifact requires a directory" >&2
                exit 1
            fi
            FRONTEND_ARTIFACT="$2"
            shift 2
            ;;
        --frontend-artifact=*)
            FRONTEND_ARTIFACT="${1#*=}"
            if [[ -z "$FRONTEND_ARTIFACT" ]]; then
                echo "--frontend-artifact requires a directory" >&2
                exit 1
            fi
            shift
            ;;
        --provision)
            PROVISION=true
            shift
            ;;
        dev | prod)
            ENVIRONMENT="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [dev|prod] [--frontend-artifact DIRECTORY] [--provision]" >&2
            exit 1
            ;;
    esac
done

# Check required environment variables
: "${COCKTAILDB_DB_PASSWORD:?Must set COCKTAILDB_DB_PASSWORD}"

if [[ -z "$FRONTEND_ARTIFACT" ]]; then
    echo "=== Building frontend artifact on controller ==="
    (cd "$PROJECT_ROOT" && npm ci && npm run build)
    FRONTEND_ARTIFACT="$PROJECT_ROOT/dist"
fi

if ! command -v node &>/dev/null; then
    echo "Error: node is required to validate the frontend artifact" >&2
    exit 1
fi
if [[ "$FRONTEND_ARTIFACT" != /* ]]; then
    FRONTEND_ARTIFACT="$(pwd -P)/$FRONTEND_ARTIFACT"
fi
node "$PROJECT_ROOT/scripts/frontend-artifact.mjs" validate "$FRONTEND_ARTIFACT"

# Set defaults for optional vars
export AWS_REGION="${AWS_REGION:-us-east-1}"
export ENVIRONMENT="$ENVIRONMENT"
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"

echo "========================================"
echo "  CocktailDB EC2 Deployment"
echo "========================================"
echo ""
echo "Environment: $ENVIRONMENT"
echo "Inventory:   inventory/${ENVIRONMENT}.yml"
echo "Provision:   $PROVISION"
echo "Release:     $RELEASE_ID"
echo "Frontend:    $FRONTEND_ARTIFACT"
echo ""

# Check if Ansible is installed
if ! command -v ansible-playbook &>/dev/null; then
    echo "Error: ansible-playbook not found"
    echo "Install with: pip install ansible"
    exit 1
fi

# Playbook paths and the inventory are relative to the Ansible directory.
cd "$ANSIBLE_DIR"

# Run provisioning if requested
if [ "$PROVISION" = true ]; then
    echo ""
    echo "=== Running Provisioning Playbook ==="
    ansible-playbook -i "inventory/${ENVIRONMENT}.yml" playbooks/provision.yml -v

    echo ""
    echo "=== Running Database Setup Playbook ==="
    ansible-playbook -i "inventory/${ENVIRONMENT}.yml" playbooks/setup-database.yml -v

    echo ""
    echo "=== Running Caddy Deployment Playbook ==="
    ansible-playbook -i "inventory/${ENVIRONMENT}.yml" playbooks/deploy-caddy.yml -v
fi

# Run deployment
echo ""
echo "=== Running Deployment Playbook ==="
ansible-playbook -i "inventory/${ENVIRONMENT}.yml" playbooks/deploy.yml -v \
    -e "deployment_release_id=${RELEASE_ID}" \
    -e "frontend_artifact_dir=${FRONTEND_ARTIFACT}"

# Show completion message
echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
echo ""
echo "Useful commands:"
echo "  Status: ./infrastructure/scripts/ec2-status.sh $ENVIRONMENT"
echo ""
