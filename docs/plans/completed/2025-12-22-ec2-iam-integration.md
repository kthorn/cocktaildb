# EC2 IAM Integration Design

## Overview

Integrate IAM role for EC2 instances into the existing CloudFormation stack, enabling S3 access for backups and analytics while keeping EC2 instance lifecycle separate from CloudFormation.

## Decision Summary

- **IAM resources**: Defined in CloudFormation (`template.yaml`)
- **EC2 instance**: Created via `launch-ec2.sh` script, references IAM profile by name
- **Connection**: Naming convention (`cocktaildb-{env}-ec2-profile`)

## Architecture

```
CloudFormation Stack
├── S3 Buckets (keep)
│   ├── BackupBucket
│   └── AnalyticsBucket
├── Cognito (keep)
│   ├── UserPool
│   ├── UserPoolClient
│   └── UserPoolDomain
├── IAM (add)
│   ├── EC2Role (S3 read/write)
│   └── EC2InstanceProfile
└── DNS (keep)
    └── DomainRecordSet

EC2 (outside CloudFormation)
├── Created by launch-ec2.sh
├── References EC2InstanceProfile by name
└── Managed by Ansible
```

## CloudFormation Changes

### Resources to Remove

Serverless compute infrastructure no longer needed:

| Category | Resources |
|----------|-----------|
| VPC/Network | `CocktailVPC`, `PrivateSubnet`, `PrivateRouteTable`, `PrivateSubnetRouteTableAssociation` |
| VPC Endpoints | `EFSVPCEndpoint`, `LambdaVPCEndpoint`, `ECRAPIVPCEndpoint`, `ECRDKRVPCEndpoint`, `LogsVPCEndpoint`, `STSVPCEndpoint` |
| EFS | `CocktailEFS`, `MountTarget`, `EFSAccessPoint` |
| Lambda | `CocktailLambda`, `SchemaDeployFunction`, `BackupLambda`, `AnalyticsTriggerFunction` |
| API Gateway | `CocktailAPI`, `ApiGatewayCloudWatchRole`, `ApiGatewayAccount` |
| Batch | `BatchServiceRole`, `FargateExecutionRole`, `AnalyticsComputeEnvironment`, `AnalyticsJobQueue`, `AnalyticsJobDefinition`, `BatchLogGroup` |
| CloudFront | `CloudFrontDistribution`, `CloudFrontOAC`, `CloudFrontLogsBucket`, `CloudFrontCertificate` |
| Website | `WebsiteBucket`, `WebsiteBucketPolicyFunction`, `BucketPolicyResource` |
| Security Groups | `LambdaSecurityGroup`, `EFSSecurityGroup`, `BatchSecurityGroup`, `EFSVPCEndpointSecurityGroup`, `BatchVPCEndpointSecurityGroup` |
| VPC Flow Logs | `VpcFlowLogGroup`, `VpcFlowLogsRole`, `CocktailVpcFlowLogs` |
| Schedules | `BackupSchedule`, `BackupLambdaInvokePermission` |
| ECR | `AnalyticsECRRepository` |

### Resources to Keep

| Resource | Purpose |
|----------|---------|
| `BackupBucket` | EC2 writes database backups |
| `AnalyticsBucket` | EC2 writes/reads analytics cache |
| Cognito resources | JWT validation for API auth |
| `DomainRecordSet` | DNS pointing to EC2 |
| `AuthDomainRecordSet` | Cognito auth subdomain |
| `AuthCertificate` | SSL for auth subdomain |

### Resources to Add

```yaml
# IAM Role for EC2 instances
EC2Role:
  Type: AWS::IAM::Role
  Properties:
    RoleName: !Sub cocktaildb-${Environment}-ec2-role
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ec2.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: S3Access
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - s3:GetObject
                - s3:PutObject
                - s3:ListBucket
                - s3:DeleteObject
              Resource:
                - !GetAtt BackupBucket.Arn
                - !Sub ${BackupBucket.Arn}/*
                - !GetAtt AnalyticsBucket.Arn
                - !Sub ${AnalyticsBucket.Arn}/*

# Instance Profile for EC2
EC2InstanceProfile:
  Type: AWS::IAM::InstanceProfile
  Properties:
    InstanceProfileName: !Sub cocktaildb-${Environment}-ec2-profile
    Roles:
      - !Ref EC2Role
```

## Launch Script Changes

Modify `infrastructure/scripts/launch-ec2.sh`:

```bash
# Add instance profile lookup
INSTANCE_PROFILE="cocktaildb-${ENVIRONMENT}-ec2-profile"

# Verify profile exists
if ! aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" &>/dev/null; then
    echo "ERROR: Instance profile '$INSTANCE_PROFILE' not found."
    echo "Deploy CloudFormation stack first: sam deploy --parameter-overrides Environment=$ENVIRONMENT"
    exit 1
fi

# Add to run-instances command
aws ec2 run-instances \
    ...
    --iam-instance-profile Name="$INSTANCE_PROFILE" \
    ...
```

## Workflow

### Initial Setup

```bash
# 1. Deploy CloudFormation (creates S3, Cognito, IAM)
sam build
sam deploy --parameter-overrides Environment=dev

# 2. Launch EC2 (attaches IAM profile automatically)
./infrastructure/scripts/launch-ec2.sh dev

# 3. Provision and deploy
export COCKTAILDB_HOST=<ec2-ip>
cd infrastructure/ansible
ansible-playbook playbooks/provision.yml
ansible-playbook playbooks/setup-database.yml
ansible-playbook playbooks/deploy.yml

# 4. Migrate data (one-time)
export COCKTAILDB_BACKUP_BUCKET=<bucket-name>
ansible-playbook playbooks/migrate-data.yml

# 5. Update DNS
export EC2_PUBLIC_IP=<ec2-ip>
./infrastructure/scripts/update-dns.sh
```

### Ongoing Deploys

```bash
cd infrastructure/ansible
ansible-playbook playbooks/deploy.yml
```

### Cost Management

```bash
# Stop instance (saves money)
./infrastructure/scripts/stop-ec2.sh dev

# Start instance
./infrastructure/scripts/start-ec2.sh dev
```

## Migration Path

1. Deploy updated CloudFormation stack (adds IAM, keeps serverless running)
2. Launch EC2 with new IAM profile
3. Provision and deploy to EC2
4. Migrate data to PostgreSQL
5. Test EC2 deployment
6. Update DNS to point to EC2
7. Monitor for 48 hours
8. Deploy CloudFormation again to remove serverless resources
9. Delete orphaned resources (EFS data, CloudWatch logs)

## Security Considerations

- EC2 role has minimal permissions (S3 only)
- No EC2/IAM/VPC management permissions
- Buckets retain existing policies
- Cognito validation unchanged (JWT verification)
