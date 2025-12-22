#!/bin/bash
# infrastructure/scripts/launch-ec2.sh
# Launch EC2 instance for CocktailDB

set -euo pipefail

# Environment (dev or prod)
ENVIRONMENT="${1:-dev}"

# Instance sizing based on environment
if [ "$ENVIRONMENT" = "prod" ]; then
    INSTANCE_TYPE="t4g.medium"
else
    INSTANCE_TYPE="t4g.small"
fi

KEY_NAME="${KEY_NAME:-cocktaildb-ec2}"
SECURITY_GROUP_NAME="cocktaildb-${ENVIRONMENT}"

echo "=== Launching CocktailDB $ENVIRONMENT Instance ==="
echo "Instance type: $INSTANCE_TYPE"

# Get latest Amazon Linux 2023 ARM64 AMI
get_ami() {
    aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-arm64" \
                  "Name=state,Values=available" \
        --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
        --output text
}

# Create security group if not exists
create_security_group() {
    local vpc_id
    vpc_id=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text)

    local sg_id
    sg_id=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${SECURITY_GROUP_NAME}" "Name=vpc-id,Values=${vpc_id}" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

    if [ "$sg_id" = "None" ] || [ -z "$sg_id" ]; then
        echo "Creating security group: ${SECURITY_GROUP_NAME}" >&2
        sg_id=$(aws ec2 create-security-group \
            --group-name "${SECURITY_GROUP_NAME}" \
            --description "CocktailDB ${ENVIRONMENT} server" \
            --vpc-id "${vpc_id}" \
            --query 'GroupId' --output text)

        # Add inbound rules
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 22 --cidr 0.0.0.0/0
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 80 --cidr 0.0.0.0/0
        aws ec2 authorize-security-group-ingress --group-id "$sg_id" \
            --protocol tcp --port 443 --cidr 0.0.0.0/0
        echo "Security group created: $sg_id" >&2
    else
        echo "Using existing security group: $sg_id" >&2
    fi

    echo "$sg_id"
}

AMI_ID=$(get_ami)
echo "Using AMI: $AMI_ID"

SG_ID=$(create_security_group)

# Launch instance
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --associate-public-ip-address \
    --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=cocktaildb-${ENVIRONMENT}},{Key=Environment,Value=${ENVIRONMENT}},{Key=Project,Value=cocktaildb}]" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Launched instance: $INSTANCE_ID"

# Wait for running
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "=== Instance Ready ==="
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo "Environment: $ENVIRONMENT"
echo ""
echo "Set environment variable:"
echo "  export COCKTAILDB_HOST=$PUBLIC_IP"
echo ""
echo "SSH access:"
echo "  ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@$PUBLIC_IP"
echo ""
echo "To stop instance (save money):"
echo "  ./infrastructure/scripts/stop-ec2.sh $ENVIRONMENT"
