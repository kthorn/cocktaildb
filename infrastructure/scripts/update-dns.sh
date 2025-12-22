#!/bin/bash
# infrastructure/scripts/update-dns.sh
# Update Route53 DNS to point to EC2 instance
#
# Usage:
#   ./update-dns.sh                    # Uses env vars
#   ./update-dns.sh --dry-run          # Show what would be done
#   ./update-dns.sh --rollback         # Point back to CloudFront (if set)

set -euo pipefail

# Parse arguments
DRY_RUN=false
ROLLBACK=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Required environment variables
: "${HOSTED_ZONE_ID:?Must set HOSTED_ZONE_ID}"
: "${DOMAIN_NAME:?Must set DOMAIN_NAME}"

if [ "$ROLLBACK" = true ]; then
    : "${CLOUDFRONT_DOMAIN:?Must set CLOUDFRONT_DOMAIN for rollback}"
    TARGET_TYPE="CNAME"
    TARGET_VALUE="$CLOUDFRONT_DOMAIN"
    echo "=== Rolling Back to CloudFront ==="
else
    : "${EC2_PUBLIC_IP:?Must set EC2_PUBLIC_IP}"
    TARGET_TYPE="A"
    TARGET_VALUE="$EC2_PUBLIC_IP"
    echo "=== Updating DNS to EC2 ==="
fi

echo "Domain: $DOMAIN_NAME"
echo "Target: $TARGET_VALUE ($TARGET_TYPE record)"
echo "Hosted Zone: $HOSTED_ZONE_ID"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would create $TARGET_TYPE record:"
    echo "  $DOMAIN_NAME -> $TARGET_VALUE"
    exit 0
fi

# Create appropriate change batch based on record type
if [ "$TARGET_TYPE" = "A" ]; then
    CHANGE_BATCH=$(cat <<EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_NAME}",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          {"Value": "${TARGET_VALUE}"}
        ]
      }
    }
  ]
}
EOF
)
else
    CHANGE_BATCH=$(cat <<EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_NAME}",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [
          {"Value": "${TARGET_VALUE}"}
        ]
      }
    }
  ]
}
EOF
)
fi

# Submit change
echo "Submitting DNS change..."
CHANGE_ID=$(aws route53 change-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --change-batch "$CHANGE_BATCH" \
    --query 'ChangeInfo.Id' \
    --output text)

echo "Change submitted: $CHANGE_ID"

# Wait for propagation
echo "Waiting for DNS propagation..."
aws route53 wait resource-record-sets-changed --id "$CHANGE_ID"

echo ""
echo "=== DNS Update Complete ==="
echo "$DOMAIN_NAME now points to $TARGET_VALUE"
echo ""
echo "Note: Full DNS propagation may take up to 48 hours globally,"
echo "but should be active within minutes for most users."
