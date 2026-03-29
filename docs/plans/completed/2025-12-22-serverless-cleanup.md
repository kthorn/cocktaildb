# Serverless Resource Cleanup Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all serverless infrastructure from CloudFormation after EC2 migration is complete and verified.

**Architecture:** Delete ~60 CloudFormation resources in dependency-safe order, update DNS to point to EC2, update Cognito URLs, and clean up orphaned AWS resources.

**Tech Stack:** CloudFormation/SAM, AWS CLI, Route 53

**Prerequisites:**
- EC2 migration complete and verified working for 48+ hours
- EC2 has Elastic IP assigned (for stable DNS)
- Database migrated to PostgreSQL on EC2
- All API endpoints tested on EC2

---

## Phase 1: Pre-Cleanup Configuration Changes

### Task 1: Update Cognito Callback URLs for EC2

The Cognito client currently references CloudFront URLs. Update to use the custom domain (which will point to EC2).

**Files:**
- Modify: `template.yaml:1149-1158`

**Step 1: Update CallbackURLs and LogoutURLs**

Replace the CloudFront-based dev URLs with API Gateway URLs (dev) or keep domain-based (prod):

```yaml
      CallbackURLs: !If
        - IsProdEnvironment
        - - !Sub "https://${DomainName}/callback.html"
          - !Sub "https://${DomainName}/login.html"
        - - "http://localhost:8000/callback.html"
          - "http://localhost:8000/login.html"
      LogoutURLs: !If
        - IsProdEnvironment
        - - !Sub "https://${DomainName}/logout.html"
        - - "http://localhost:8000/logout.html"
```

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`
Expected: "is a valid SAM Template"

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: update Cognito URLs for EC2 migration"
```

---

### Task 2: Update DomainRecordSet to Point to EC2

Change DNS from CloudFront to EC2 Elastic IP.

**Files:**
- Modify: `template.yaml:476-486`

**Step 1: Add EC2ElasticIP parameter**

Add after line 54 (after AmazonClientSecret parameter):

```yaml
  EC2ElasticIP:
    Type: String
    Default: ""
    Description: Elastic IP address of the EC2 instance (required for prod after migration)
```

**Step 2: Update DomainRecordSet resource**

Replace the existing DomainRecordSet:

```yaml
  # Route 53 Record Set for EC2
  DomainRecordSet:
    Type: AWS::Route53::RecordSet
    Condition: IsProdEnvironment
    Properties:
      HostedZoneId: !Ref HostedZoneId
      Name: !Ref DomainName
      Type: A
      TTL: 300
      ResourceRecords:
        - !Ref EC2ElasticIP
```

**Step 3: Validate template**

Run: `sam validate --template-file template.yaml`
Expected: "is a valid SAM Template"

**Step 4: Commit**

```bash
git add template.yaml
git commit -m "chore: update DNS to point to EC2 Elastic IP"
```

---

## Phase 2: Remove Serverless Resources

Resources are removed in dependency-safe order. Each task removes a logical group.

### Task 3: Remove Backup Schedule Resources (Prod Only)

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `BackupSchedule` (lines ~1533-1543)
- `BackupLambdaInvokePermission` (lines ~1545-1553)

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove backup schedule resources"
```

---

### Task 4: Remove Lambda Functions

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `BackupLambda` (entire resource block, ~70 lines)
- `AnalyticsTriggerFunction` (entire resource block, ~25 lines)
- `SchemaDeployFunction` (entire resource block, ~30 lines)
- `CocktailLambda` (entire resource block, ~400+ lines including all Events)

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove Lambda functions"
```

---

### Task 5: Remove API Gateway Resources

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `CocktailAPI` (entire resource block)
- `ApiGatewayAccount`
- `ApiGatewayCloudWatchRole`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove API Gateway resources"
```

---

### Task 6: Remove AWS Batch Resources

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `AnalyticsJobDefinition`
- `AnalyticsJobQueue`
- `AnalyticsComputeEnvironment`
- `BatchLogGroup`
- `FargateExecutionRole`
- `BatchServiceRole`
- `AnalyticsECRRepository`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove AWS Batch resources"
```

---

### Task 7: Remove CloudFront and Website Resources

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `BucketPolicyResource`
- `WebsiteBucketPolicyFunction`
- `CloudFrontDistribution`
- `CloudFrontOAC` (note: has DeletionPolicy: Retain, may need manual cleanup)
- `CloudFrontLogsBucket`
- `CloudFrontCertificate`
- `WebsiteBucket`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove CloudFront and website resources"
```

---

### Task 8: Remove EFS Resources

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `EFSAccessPoint`
- `MountTarget`
- `CocktailEFS`
- `EFSIngressFromLambda`
- `EFSIngressFromBatch`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove EFS resources"
```

---

### Task 9: Remove VPC Endpoints

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `S3VPCEndpoint`
- `EFSVPCEndpoint`
- `LambdaVPCEndpoint`
- `ECRAPIVPCEndpoint`
- `ECRDKRVPCEndpoint`
- `LogsVPCEndpoint`
- `STSVPCEndpoint`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove VPC endpoints"
```

---

### Task 10: Remove Security Groups

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `LambdaIngressHTTPS`
- `LambdaSecurityGroup`
- `EFSSecurityGroup`
- `EFSVPCEndpointSecurityGroup`
- `BatchSecurityGroup`
- `BatchVPCEndpointSecurityGroup`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove security groups"
```

---

### Task 11: Remove VPC and Network Resources

**Files:**
- Modify: `template.yaml`

**Step 1: Delete these resources**

Remove completely:
- `CocktailVpcFlowLogs`
- `VpcFlowLogsRole`
- `VpcFlowLogGroup`
- `PrivateSubnetRouteTableAssociation`
- `PrivateRouteTable`
- `PrivateSubnet`
- `CocktailVPC`

**Step 2: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove VPC and network resources"
```

---

### Task 12: Remove Obsolete Outputs

**Files:**
- Modify: `template.yaml` Outputs section

**Step 1: Delete these outputs**

Remove:
- `VpcId`
- `PrivateSubnetId`
- `EFSFileSystemId`
- `EFSMountPath`
- `WebsiteURL`
- `WebsiteBucketName`
- `CloudFrontURL`
- `CloudFrontDistribution`
- `ApiEndpoint`
- `CertificateARN`
- `AnalyticsTriggerFunctionArn`
- `AnalyticsJobQueueArn`
- `AnalyticsJobDefinitionArn`
- `CloudFrontLogsBucketName`

**Step 2: Keep these outputs**

Verify these remain:
- `UserPoolId`
- `UserPoolClientId`
- `CognitoDomainURLV3`
- `CustomDomainURL`
- `AuthCertificateARN`
- `BackupBucketName`
- `AdminGroupName`
- `EditorGroupName`
- `AnalyticsBucketName`
- `EC2RoleArn`
- `EC2InstanceProfileName`

**Step 3: Validate template**

Run: `sam validate --template-file template.yaml`

**Step 4: Commit**

```bash
git add template.yaml
git commit -m "chore: remove obsolete CloudFormation outputs"
```

---

### Task 13: Remove Unused Condition

**Files:**
- Modify: `template.yaml`

**Step 1: Delete unused condition**

Remove:
- `HasAuthCertificate` condition (line ~65) - flagged by linter as unused

**Step 2: Validate template with lint**

Run: `sam validate --template-file template.yaml --lint`
Expected: No errors

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "chore: remove unused HasAuthCertificate condition"
```

---

## Phase 3: Deploy and Cleanup

### Task 14: Deploy Updated Stack

**Step 1: Build**

Run: `sam build --template-file template.yaml`

**Step 2: Deploy to dev first**

Run: `sam deploy --parameter-overrides Environment=dev`

Monitor CloudFormation console for deletion progress. Some resources may take 5-10 minutes to delete.

**Step 3: Verify dev deployment**

Run: `aws cloudformation describe-stacks --stack-name cocktail-db-dev --query 'Stacks[0].StackStatus'`
Expected: "UPDATE_COMPLETE"

**Step 4: Deploy to prod**

Run: `sam deploy --parameter-overrides Environment=prod EC2ElasticIP=<your-elastic-ip> HostedZoneId=<your-zone-id>`

**Step 5: Verify prod deployment**

Run: `aws cloudformation describe-stacks --stack-name cocktail-db-prod --query 'Stacks[0].StackStatus'`
Expected: "UPDATE_COMPLETE"

---

### Task 15: Manual Cleanup of Orphaned Resources

CloudFormation won't delete these - manual cleanup required.

**Step 1: Delete CloudWatch Log Groups**

```bash
# List log groups to delete
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/cocktail-db" --query 'logGroups[].logGroupName'
aws logs describe-log-groups --log-group-name-prefix "/aws/batch/cocktail-db" --query 'logGroups[].logGroupName'
aws logs describe-log-groups --log-group-name-prefix "/aws/apigateway/cocktail-db" --query 'logGroups[].logGroupName'
aws logs describe-log-groups --log-group-name-prefix "/aws/vpc/flowlogs/cocktail-db" --query 'logGroups[].logGroupName'

# Delete each one (replace with actual names)
aws logs delete-log-group --log-group-name "<log-group-name>"
```

**Step 2: Delete retained CloudFront OAC**

The CloudFrontOAC has `DeletionPolicy: Retain`. Check if it exists and delete:

```bash
# List OACs
aws cloudfront list-origin-access-controls --query 'OriginAccessControlList.Items[?contains(Name, `cocktail`)].{Id:Id,Name:Name}'

# Delete if found (replace ID)
aws cloudfront delete-origin-access-control --id <oac-id> --if-match <etag>
```

**Step 3: Empty and delete S3 buckets (if desired)**

Only if you want to remove website/logs buckets:

```bash
# Empty bucket first
aws s3 rm s3://cocktailwebsite-<account-id>-<env> --recursive
aws s3 rm s3://cocktailcflogs-<account-id>-<env> --recursive

# Delete bucket
aws s3 rb s3://cocktailwebsite-<account-id>-<env>
aws s3 rb s3://cocktailcflogs-<account-id>-<env>
```

**Step 4: Delete ECR repository images**

```bash
# List images
aws ecr list-images --repository-name cocktail-db-<env>-analytics

# Delete repository (will fail if images exist, use --force)
aws ecr delete-repository --repository-name cocktail-db-<env>-analytics --force
```

**Step 5: Verify cleanup**

```bash
# Check for lingering resources
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=cocktaildb --query 'ResourceTagMappingList[].ResourceARN'
```

---

## Summary

**Resources Removed (59 total):**
- VPC/Network: 7 resources
- VPC Endpoints: 7 resources
- Security Groups: 6 resources
- EFS: 5 resources
- Lambda: 4 functions
- API Gateway: 3 resources
- Batch: 7 resources
- CloudFront/Website: 7 resources
- Schedules: 2 resources
- ECR: 1 resource
- Outputs: 14 outputs
- Conditions: 1 condition

**Resources Kept (16 total):**
- S3: BackupBucket, AnalyticsBucket
- Cognito: UserPool, Client, Domain, Groups, UI, Identity Providers (8 resources)
- DNS: DomainRecordSet, AuthDomainRecordSet
- Certificates: AuthCertificate
- IAM: EC2Role, EC2InstanceProfile

**Manual Cleanup Required:**
- CloudWatch Log Groups
- CloudFront OAC (retained)
- S3 bucket contents (optional)
- ECR images
