#!/bin/bash
# infrastructure/scripts/ec2-status.sh
# Check status of CocktailDB EC2 instances

set -euo pipefail

ENVIRONMENT="${1:-}"

echo "=== CocktailDB EC2 Instance Status ==="
echo ""

if [ -n "$ENVIRONMENT" ]; then
    FILTER="Name=tag:Name,Values=cocktaildb-${ENVIRONMENT}"
else
    FILTER="Name=tag:Project,Values=cocktaildb"
fi

aws ec2 describe-instances \
    --filters "$FILTER" \
    --query 'Reservations[].Instances[].{
        Name: Tags[?Key==`Name`].Value | [0],
        InstanceId: InstanceId,
        Type: InstanceType,
        State: State.Name,
        PublicIP: PublicIpAddress,
        LaunchTime: LaunchTime
    }' \
    --output table

echo ""
echo "Commands:"
echo "  Start:  ./infrastructure/scripts/start-ec2.sh [dev|prod]"
echo "  Stop:   ./infrastructure/scripts/stop-ec2.sh [dev|prod]"
echo "  Launch: ./infrastructure/scripts/launch-ec2.sh [dev|prod]"
