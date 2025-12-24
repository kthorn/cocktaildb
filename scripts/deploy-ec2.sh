#!/bin/bash
# scripts/deploy-ec2.sh
# Deploy CocktailDB to EC2 instance
#
# Usage:
#   ./scripts/deploy-ec2.sh              # Deploy to dev
#   ./scripts/deploy-ec2.sh prod         # Deploy to prod
#   ./scripts/deploy-ec2.sh --provision  # Full provision + deploy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ANSIBLE_DIR="${PROJECT_ROOT}/infrastructure/ansible"

# Default to dev environment
ENVIRONMENT="${1:-dev}"
PROVISION=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --provision)
            PROVISION=true
            shift
            ;;
        dev|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [dev|prod] [--provision]"
            exit 1
            ;;
    esac
done

# Check required environment variables
: "${COCKTAILDB_HOST:?Must set COCKTAILDB_HOST to EC2 IP address}"
: "${COCKTAILDB_DB_PASSWORD:?Must set COCKTAILDB_DB_PASSWORD}"

# Set defaults for optional vars
export COCKTAILDB_DOMAIN="${COCKTAILDB_DOMAIN:-}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export ENVIRONMENT="$ENVIRONMENT"

echo "========================================"
echo "  CocktailDB EC2 Deployment"
echo "========================================"
echo ""
echo "Target Host: $COCKTAILDB_HOST"
echo "Environment: $ENVIRONMENT"
echo "Domain: ${COCKTAILDB_DOMAIN:-<not set>}"
echo "Provision: $PROVISION"
echo ""

# Check if Ansible is installed
if ! command -v ansible-playbook &> /dev/null; then
    echo "Error: ansible-playbook not found"
    echo "Install with: pip install ansible"
    exit 1
fi

# Install Ansible requirements
echo "Installing Ansible requirements..."
cd "$ANSIBLE_DIR"
ansible-galaxy collection install -r requirements.yml --force

# Run provisioning if requested
if [ "$PROVISION" = true ]; then
    echo ""
    echo "=== Running Provisioning Playbook ==="
    ansible-playbook playbooks/provision.yml -v

    echo ""
    echo "=== Running Database Setup Playbook ==="
    ansible-playbook playbooks/setup-database.yml -v

    echo ""
    echo "=== Running Caddy Deployment Playbook ==="
    ansible-playbook playbooks/deploy-caddy.yml -v
fi

# Run deployment
echo ""
echo "=== Running Deployment Playbook ==="
ansible-playbook playbooks/deploy.yml -v

# Show completion message
echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
echo ""
if [ -n "$COCKTAILDB_DOMAIN" ]; then
    echo "Application URL: https://${COCKTAILDB_DOMAIN}"
else
    echo "Application URL: http://${COCKTAILDB_HOST}"
fi
echo ""
echo "Useful commands:"
echo "  SSH:    ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@${COCKTAILDB_HOST}"
echo "  Logs:   ssh ... 'docker logs cocktaildb-api-1'"
echo "  Status: ./infrastructure/scripts/ec2-status.sh $ENVIRONMENT"
echo ""
