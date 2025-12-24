#!/bin/bash
# infrastructure/scripts/stop-ec2.sh
# Stop a running CocktailDB EC2 instance (to save money)

set -euo pipefail

ENVIRONMENT="${1:-dev}"

# Safety check for prod
if [ "$ENVIRONMENT" = "prod" ]; then
    echo "WARNING: You are about to stop the PRODUCTION instance!"
    read -p "Are you sure? Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
fi

echo "=== Stopping CocktailDB $ENVIRONMENT Instance ==="

# Find instance by tags
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=cocktaildb-${ENVIRONMENT}" \
              "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "No running instance found for environment: $ENVIRONMENT"
    exit 1
fi

echo "Stopping instance: $INSTANCE_ID"
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" > /dev/null

echo "Waiting for instance to stop..."
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"

echo ""
echo "=== Instance Stopped ==="
echo "Instance $INSTANCE_ID is now stopped."
echo "You are no longer being charged for compute (only EBS storage)."
echo ""
echo "To restart: ./infrastructure/scripts/start-ec2.sh $ENVIRONMENT"
