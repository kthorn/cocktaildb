#!/bin/bash
# infrastructure/scripts/start-ec2.sh
# Start a stopped CocktailDB EC2 instance

set -euo pipefail

ENVIRONMENT="${1:-dev}"

echo "=== Starting CocktailDB $ENVIRONMENT Instance ==="

# Find instance by tags
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=cocktaildb-${ENVIRONMENT}" \
              "Name=instance-state-name,Values=stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "No stopped instance found for environment: $ENVIRONMENT"
    echo "Either the instance is already running or doesn't exist."
    echo ""
    echo "Check status with: ./infrastructure/scripts/ec2-status.sh $ENVIRONMENT"
    exit 1
fi

echo "Starting instance: $INSTANCE_ID"
aws ec2 start-instances --instance-ids "$INSTANCE_ID" > /dev/null

echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# Get new public IP (may change after stop/start)
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "=== Instance Started ==="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo ""
echo "Update environment variable:"
echo "  export COCKTAILDB_HOST=$PUBLIC_IP"
echo ""
echo "Note: Public IP may have changed. Update Ansible inventory if needed."
