# Analytics Batch Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate analytics refresh from Lambda (15-min timeout) to AWS Batch on Graviton Spot instances.

**Architecture:** Thin trigger Lambda submits Batch job, which runs container with EFS (read-only) access and writes results to S3. Same ECR repo, new CLI entrypoint.

**Tech Stack:** AWS Batch, AWS SAM/CloudFormation, Python 3.12, boto3, EFS, S3

---

## Task 1: Refactor analytics_refresh.py to Extract Core Logic

**Files:**
- Modify: `api/analytics/analytics_refresh.py`

**Step 1: Extract core logic into `regenerate_analytics()` function**

The `lambda_handler` currently contains all logic. Extract it so it can be called from both Lambda and CLI.

Replace the entire file with:

```python
"""Analytics regeneration - core logic for Batch job"""
import json
import logging
import os
import sys
from typing import Dict, Any

import pandas as pd

from db.database import get_database
from db.db_analytics import AnalyticsQueries
from utils.analytics_cache import AnalyticsStorage

# Configure logging
logger = logging.getLogger(__name__)


def enrich_tree_with_recipe_counts(tree_node: Dict[str, Any], recipe_counts: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Recursively enrich tree nodes with recipe count data

    Args:
        tree_node: Tree node dictionary from build_ingredient_tree
        recipe_counts: Dict mapping ingredient_id to {direct, hierarchical} counts

    Returns:
        Enriched tree node with recipe_count and hierarchical_recipe_count fields
    """
    node_id = str(tree_node['id'])

    # Add recipe counts if available (skip for root node)
    if node_id in recipe_counts:
        tree_node['recipe_count'] = recipe_counts[node_id]['direct']
        tree_node['hierarchical_recipe_count'] = recipe_counts[node_id]['hierarchical']
    else:
        # Root node or missing data
        tree_node['recipe_count'] = 0
        tree_node['hierarchical_recipe_count'] = 0

    # Recursively process children
    if 'children' in tree_node:
        tree_node['children'] = [
            enrich_tree_with_recipe_counts(child, recipe_counts)
            for child in tree_node['children']
        ]

    return tree_node


def regenerate_analytics() -> Dict[str, Any]:
    """
    Core analytics regeneration logic.

    Generates:
    - Root-level ingredient usage statistics
    - Recipe complexity distribution
    - Cocktail space UMAP projections (Manhattan and EM-based)
    - Ingredient tree with recipe counts

    Stores results in S3 via AnalyticsStorage.

    Returns:
        dict: Summary of generated analytics with counts

    Raises:
        ValueError: If ANALYTICS_BUCKET environment variable not set
        Exception: If analytics generation or storage fails
    """
    # Get environment configuration
    bucket_name = os.environ.get('ANALYTICS_BUCKET')
    if not bucket_name:
        raise ValueError("ANALYTICS_BUCKET environment variable not set")

    logger.info("Starting analytics regeneration")

    # Initialize components
    db = get_database()
    analytics_queries = AnalyticsQueries(db)
    storage = AnalyticsStorage(bucket_name)

    # Query all ingredient data once (used for both stats and tree)
    logger.info("Querying all ingredient usage statistics")
    all_ingredient_stats = analytics_queries.get_ingredient_usage_stats(all_ingredients=True)

    # Filter to root-level ingredients for the ingredient-usage endpoint
    ingredient_stats = [
        ing for ing in all_ingredient_stats
        if ing['parent_id'] is None
    ]
    logger.info(f"Filtered to {len(ingredient_stats)} root-level ingredients")

    # Convert all ingredients to DataFrame for tree building
    ingredients_df = pd.DataFrame(all_ingredient_stats)
    if not ingredients_df.empty:
        ingredients_df = ingredients_df.rename(columns={
            "path": "ingredient_path",
            "direct_usage": "direct_recipe_count",
            "hierarchical_usage": "hierarchical_recipe_count",
        })
        ingredients_df["substitution_level"] = 1.0

    # Generate recipe complexity distribution
    logger.info("Generating recipe complexity distribution")
    complexity_stats = analytics_queries.get_recipe_complexity_distribution()

    # Generate both cocktail space variants for comparison
    logger.info("Generating Manhattan-based cocktail space")
    cocktail_space_manhattan = analytics_queries.compute_cocktail_space_umap()

    logger.info("Generating EM-based cocktail space with rollup")
    cocktail_space_em = analytics_queries.compute_cocktail_space_umap_em()

    # Generate ingredient tree
    logger.info("Building ingredient tree with recipe counts")
    from barcart.distance import build_ingredient_tree

    if not ingredients_df.empty:
        # Build the tree structure
        tree_dict, parent_map = build_ingredient_tree(
            ingredients_df,
            id_col='ingredient_id',
            name_col='ingredient_name',
            path_col='ingredient_path',
            weight_col='substitution_level',
            root_id='root',
            root_name='All Ingredients',
            default_edge_weight=1.0
        )

        # Create recipe count lookup from DataFrame
        recipe_counts = {}
        for _, row in ingredients_df.iterrows():
            ing_id = str(row['ingredient_id'])
            recipe_counts[ing_id] = {
                'direct': int(row['direct_recipe_count']),
                'hierarchical': int(row['hierarchical_recipe_count'])
            }

        # Enrich tree with recipe counts
        enriched_tree = enrich_tree_with_recipe_counts(tree_dict, recipe_counts)

        logger.info(f"Built ingredient tree with {len(recipe_counts)} ingredients")
    else:
        logger.warning("No ingredient data available for tree building")
        enriched_tree = {
            "id": "root",
            "name": "All Ingredients",
            "recipe_count": 0,
            "hierarchical_recipe_count": 0,
            "children": []
        }
        recipe_counts = {}

    # Store in S3
    logger.info("Storing analytics in S3")
    storage.put_analytics('ingredient-usage', ingredient_stats)
    storage.put_analytics('recipe-complexity', complexity_stats)
    storage.put_analytics('cocktail-space', cocktail_space_manhattan)
    storage.put_analytics('cocktail-space-em', cocktail_space_em)
    storage.put_analytics('ingredient-tree', enriched_tree)

    logger.info("Analytics regeneration completed successfully")

    return {
        "ingredient_stats_count": len(ingredient_stats),
        "complexity_stats_count": len(complexity_stats),
        "cocktail_space_count": len(cocktail_space_manhattan),
        "cocktail_space_em_count": len(cocktail_space_em),
        "ingredient_tree_nodes": len(recipe_counts)
    }


def main():
    """CLI entrypoint for Batch job"""
    # Configure logging for CLI
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        result = regenerate_analytics()
        print(json.dumps({
            "status": "success",
            "message": "Analytics regenerated successfully",
            **result
        }))
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error regenerating analytics: {str(e)}", exc_info=True)
        print(json.dumps({
            "status": "error",
            "error": "Failed to regenerate analytics",
            "details": str(e)
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Verify the refactored module is syntactically correct**

Run:
```bash
python -m py_compile api/analytics/analytics_refresh.py
```

Expected: No output (success)

**Step 3: Commit**

```bash
git add api/analytics/analytics_refresh.py
git commit -m "refactor: extract analytics core logic for Batch migration

Extract regenerate_analytics() function from lambda_handler so it can be
called from both Lambda and CLI entrypoints. Add main() as CLI entrypoint."
```

---

## Task 2: Update Dockerfile for Batch

**Files:**
- Modify: `api/analytics/Dockerfile`

**Step 1: Replace Lambda base image with standard Python image**

Replace the entire Dockerfile with:

```dockerfile
FROM public.ecr.aws/docker/library/python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: Install barcart dependencies (heavy, rarely change)
COPY packages/barcart/requirements.txt /tmp/barcart-requirements.txt
RUN pip install --no-cache-dir -r /tmp/barcart-requirements.txt

# Layer 2: Install analytics dependencies (rarely change)
COPY api/analytics/requirements.txt /tmp/analytics-requirements.txt
RUN pip install --no-cache-dir -r /tmp/analytics-requirements.txt

# Layer 3: Copy shared modules (change occasionally)
COPY api/db/ /app/db/
COPY api/utils/ /app/utils/
COPY api/core/ /app/core/

# Layer 4: Install barcart package code (changes frequently)
COPY packages/barcart/ /app/packages/barcart/
RUN pip install --no-deps /app/packages/barcart/

# Layer 5: Copy analytics module (changes frequently)
COPY api/analytics/ /app/analytics/

# Set PYTHONPATH so imports work
ENV PYTHONPATH=/app

# Run the analytics module
CMD ["python", "-m", "analytics.analytics_refresh"]
```

**Step 2: Commit**

```bash
git add api/analytics/Dockerfile
git commit -m "build: update Dockerfile for Batch (non-Lambda base image)

Switch from Lambda Python runtime to standard Python 3.12 slim image.
Change entrypoint to CLI mode (python -m analytics.analytics_refresh)."
```

---

## Task 3: Create Trigger Lambda

**Files:**
- Create: `api/analytics/trigger.py`

**Step 1: Create the trigger Lambda handler**

```python
"""Lambda function to trigger analytics Batch job"""
import json
import logging
import os
from typing import Dict, Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Batch client at module level
_batch_client = None


def _get_batch_client():
    """Get or create the Batch client (cached at module level)"""
    global _batch_client
    if _batch_client is None:
        _batch_client = boto3.client('batch')
    return _batch_client


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to submit analytics Batch job.

    Environment variables:
        BATCH_JOB_QUEUE: Name of the Batch job queue
        BATCH_JOB_DEFINITION: Name of the Batch job definition

    Returns:
        dict: Lambda response with jobId and jobArn
    """
    try:
        job_queue = os.environ.get('BATCH_JOB_QUEUE')
        job_definition = os.environ.get('BATCH_JOB_DEFINITION')

        if not job_queue or not job_definition:
            raise ValueError(
                "BATCH_JOB_QUEUE and BATCH_JOB_DEFINITION environment variables required"
            )

        logger.info(f"Submitting Batch job to queue: {job_queue}")

        batch_client = _get_batch_client()
        response = batch_client.submit_job(
            jobName='analytics-refresh',
            jobQueue=job_queue,
            jobDefinition=job_definition
        )

        job_id = response['jobId']
        job_arn = response['jobArn']

        logger.info(f"Batch job submitted: {job_id}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analytics Batch job submitted",
                "jobId": job_id,
                "jobArn": job_arn
            })
        }

    except Exception as e:
        logger.error(f"Error submitting Batch job: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to submit analytics Batch job",
                "details": str(e)
            })
        }
```

**Step 2: Verify syntax**

Run:
```bash
python -m py_compile api/analytics/trigger.py
```

Expected: No output (success)

**Step 3: Commit**

```bash
git add api/analytics/trigger.py
git commit -m "feat: add trigger Lambda for analytics Batch job

Thin Lambda that submits Batch job and returns jobId/jobArn for
optional status polling."
```

---

## Task 4: Update analytics_helpers.py

**Files:**
- Modify: `api/utils/analytics_helpers.py`

**Step 1: Update to use new env var name (interface unchanged)**

Replace entire file with:

```python
"""Helper functions for analytics operations"""

import logging
import os

logger = logging.getLogger(__name__)

# Initialize boto3 client at module level for Lambda optimization
# This avoids creating a new client on every request, which is slow
_lambda_client = None


def _get_lambda_client():
    """Get or create the Lambda client (cached at module level)"""
    global _lambda_client
    if _lambda_client is None:
        try:
            import boto3
            _lambda_client = boto3.client('lambda')
        except Exception as e:
            logger.error(f"Failed to create Lambda client: {str(e)}")
            raise
    return _lambda_client


def trigger_analytics_refresh():
    """Trigger async analytics regeneration

    Invokes the analytics trigger Lambda function asynchronously,
    which submits an AWS Batch job.
    Failures are logged but don't fail the main operation.
    """
    try:
        function_name = os.environ.get("ANALYTICS_TRIGGER_FUNCTION")
        if not function_name:
            logger.debug("ANALYTICS_TRIGGER_FUNCTION not configured, skipping trigger")
            return

        lambda_client = _get_lambda_client()
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event'  # Async - non-blocking
        )
        logger.info("Analytics Batch job trigger invoked")
    except Exception as e:
        logger.warning(f"Failed to trigger analytics regeneration: {str(e)}")
        # Don't fail the main operation if analytics trigger fails
```

**Step 2: Commit**

```bash
git add api/utils/analytics_helpers.py
git commit -m "refactor: update analytics helper for Batch trigger

Change env var from ANALYTICS_REFRESH_FUNCTION to ANALYTICS_TRIGGER_FUNCTION.
The trigger Lambda now submits a Batch job instead of running analytics directly."
```

---

## Task 5: Add Batch Infrastructure to template.yaml (Part 1 - IAM Roles)

**Files:**
- Modify: `template.yaml`

**Step 1: Add Batch service role after existing IAM roles (around line 1226)**

Find the line `ApiGatewayAccount:` and add BEFORE it:

```yaml
  # --- AWS Batch Resources ---

  # IAM Role for AWS Batch service
  BatchServiceRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: batch.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole

  # IAM Role for Batch EC2 instances
  BatchInstanceRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ec2.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role
      Policies:
        - PolicyName: BatchInstanceEFSAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: EFSReadOnlyAccess
                Effect: Allow
                Action:
                  - elasticfilesystem:ClientMount
                  - elasticfilesystem:DescribeMountTargets
                Resource: !GetAtt CocktailEFS.Arn
        - PolicyName: BatchInstanceS3Access
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - s3:GetObject
                  - s3:PutObject
                  - s3:ListBucket
                Resource:
                  - !Sub "arn:aws:s3:::${AnalyticsBucket}"
                  - !Sub "arn:aws:s3:::${AnalyticsBucket}/*"
        - PolicyName: BatchInstanceECRAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - ecr:GetAuthorizationToken
                  - ecr:BatchCheckLayerAvailability
                  - ecr:GetDownloadUrlForLayer
                  - ecr:BatchGetImage
                Resource: "*"
        - PolicyName: BatchInstanceLogsAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: "*"

  BatchInstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Roles:
        - !Ref BatchInstanceRole

```

**Step 2: Commit**

```bash
git add template.yaml
git commit -m "infra: add Batch IAM roles for analytics migration

Add BatchServiceRole, BatchInstanceRole, and BatchInstanceProfile
with permissions for EFS (read-only), S3, ECR, and CloudWatch Logs."
```

---

## Task 6: Add Batch Infrastructure to template.yaml (Part 2 - Security Group & Compute)

**Files:**
- Modify: `template.yaml`

**Step 1: Add security group and compute environment after BatchInstanceProfile**

Add after the `BatchInstanceProfile` resource:

```yaml
  # Security group for Batch instances
  BatchSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for Batch compute instances
      VpcId: !Ref CocktailVPC
      SecurityGroupEgress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.0.0.0/0
        - IpProtocol: tcp
          FromPort: 2049
          ToPort: 2049
          DestinationSecurityGroupId: !Ref EFSSecurityGroup

  # Allow Batch instances to access EFS
  EFSIngressFromBatch:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref EFSSecurityGroup
      IpProtocol: tcp
      FromPort: 2049
      ToPort: 2049
      SourceSecurityGroupId: !Ref BatchSecurityGroup

  # Batch Compute Environment - Graviton Spot
  AnalyticsComputeEnvironment:
    Type: AWS::Batch::ComputeEnvironment
    Properties:
      Type: MANAGED
      ServiceRole: !GetAtt BatchServiceRole.Arn
      ComputeResources:
        Type: SPOT
        AllocationStrategy: SPOT_PRICE_CAPACITY_OPTIMIZED
        MinvCpus: 0
        MaxvCpus: 8
        InstanceTypes:
          - c7g.medium
          - c7g.large
          - c7g.xlarge
          - c7g.2xlarge
        Subnets:
          - !Ref PrivateSubnet
        SecurityGroupIds:
          - !Ref BatchSecurityGroup
        InstanceRole: !GetAtt BatchInstanceProfile.Arn
        SpotIamFleetRole: !Sub arn:aws:iam::${AWS::AccountId}:role/aws-ec2-spot-fleet-tagging-role
        Tags:
          Name: !Sub ${AWS::StackName}-batch-analytics
      State: ENABLED

  # Batch Job Queue
  AnalyticsJobQueue:
    Type: AWS::Batch::JobQueue
    Properties:
      Priority: 1
      ComputeEnvironmentOrder:
        - Order: 1
          ComputeEnvironment: !Ref AnalyticsComputeEnvironment
      State: ENABLED

```

**Step 2: Commit**

```bash
git add template.yaml
git commit -m "infra: add Batch compute environment and job queue

Add BatchSecurityGroup with EFS access, AnalyticsComputeEnvironment
with Graviton Spot instances (c7g.medium-2xlarge), and AnalyticsJobQueue."
```

---

## Task 7: Add Batch Infrastructure to template.yaml (Part 3 - Job Definition)

**Files:**
- Modify: `template.yaml`

**Step 1: Add job definition after AnalyticsJobQueue**

Add after the `AnalyticsJobQueue` resource:

```yaml
  # Batch Job Definition
  AnalyticsJobDefinition:
    Type: AWS::Batch::JobDefinition
    Properties:
      Type: container
      PlatformCapabilities:
        - EC2
      RetryStrategy:
        Attempts: 3
        EvaluateOnExit:
          - OnStatusReason: "Host EC2*"
            Action: RETRY
          - OnReason: "*spot*"
            Action: RETRY
          - OnReason: "*Spot*"
            Action: RETRY
          - OnExitCode: "*"
            Action: EXIT
      Timeout:
        AttemptDurationSeconds: 3600
      ContainerProperties:
        Image: !Sub ${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/${AnalyticsECRRepository}:latest
        ResourceRequirements:
          - Type: VCPU
            Value: "2"
          - Type: MEMORY
            Value: "2048"
        Environment:
          - Name: DB_NAME
            Value: !Ref DatabaseName
          - Name: DB_PATH
            Value: !Sub /mnt/efs/${DatabaseName}.db
          - Name: ANALYTICS_BUCKET
            Value: !Ref AnalyticsBucket
        MountPoints:
          - ContainerPath: /mnt/efs
            ReadOnly: true
            SourceVolume: efs-volume
        Volumes:
          - Name: efs-volume
            EfsVolumeConfiguration:
              FileSystemId: !Ref CocktailEFS
              RootDirectory: /lambda
              TransitEncryption: ENABLED
              AuthorizationConfig:
                AccessPointId: !Ref EFSAccessPoint
                Iam: ENABLED
        LogConfiguration:
          LogDriver: awslogs
          Options:
            awslogs-group: !Sub /aws/batch/${AWS::StackName}-analytics
            awslogs-region: !Ref AWS::Region
            awslogs-stream-prefix: analytics

  # CloudWatch Log Group for Batch jobs
  BatchLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub /aws/batch/${AWS::StackName}-analytics
      RetentionInDays: 14

  # --- End AWS Batch Resources ---

```

**Step 2: Commit**

```bash
git add template.yaml
git commit -m "infra: add Batch job definition with EFS mount

Add AnalyticsJobDefinition with:
- 2 vCPU, 2048MB memory
- EFS mount (read-only) at /mnt/efs
- Retry strategy for Spot interruptions (3 attempts)
- 1 hour timeout
- CloudWatch Logs integration"
```

---

## Task 8: Add Trigger Lambda to template.yaml

**Files:**
- Modify: `template.yaml`

**Step 1: Add trigger Lambda after BatchLogGroup**

Add after the `BatchLogGroup` resource (before `# --- End AWS Batch Resources ---`):

```yaml
  # Analytics Trigger Lambda (submits Batch job)
  AnalyticsTriggerFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub ${AWS::StackName}-analytics-trigger
      CodeUri: api/analytics/
      Handler: trigger.lambda_handler
      Runtime: python3.12
      Timeout: 30
      MemorySize: 128
      Environment:
        Variables:
          BATCH_JOB_QUEUE: !Ref AnalyticsJobQueue
          BATCH_JOB_DEFINITION: !Ref AnalyticsJobDefinition
      Policies:
        - Statement:
            - Effect: Allow
              Action:
                - batch:SubmitJob
                - batch:DescribeJobs
              Resource: "*"
            - Effect: Allow
              Action:
                - logs:CreateLogGroup
                - logs:CreateLogStream
                - logs:PutLogEvents
              Resource: "*"

```

**Step 2: Commit**

```bash
git add template.yaml
git commit -m "infra: add analytics trigger Lambda

Add AnalyticsTriggerFunction that submits Batch jobs.
Lightweight Lambda (128MB, 30s timeout) with batch:SubmitJob permission."
```

---

## Task 9: Update CocktailLambda Environment Variable

**Files:**
- Modify: `template.yaml`

**Step 1: Find and update CocktailLambda environment variable**

In the `CocktailLambda` resource (around line 530), find:
```yaml
          ANALYTICS_REFRESH_FUNCTION: !Ref AnalyticsRefreshFunction
```

Replace with:
```yaml
          ANALYTICS_TRIGGER_FUNCTION: !Ref AnalyticsTriggerFunction
```

**Step 2: Update the CocktailLambda policy**

Find the policy section (around line 576):
```yaml
            - Sid: AnalyticsRefreshFunctionInvoke
              Effect: Allow
              Action:
                - lambda:InvokeFunction
              Resource: !GetAtt AnalyticsRefreshFunction.Arn
```

Replace with:
```yaml
            - Sid: AnalyticsTriggerFunctionInvoke
              Effect: Allow
              Action:
                - lambda:InvokeFunction
              Resource: !GetAtt AnalyticsTriggerFunction.Arn
```

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "infra: update CocktailLambda to use trigger function

Change ANALYTICS_REFRESH_FUNCTION to ANALYTICS_TRIGGER_FUNCTION
and update IAM policy to reference new trigger Lambda."
```

---

## Task 10: Remove Old AnalyticsRefreshFunction Lambda

**Files:**
- Modify: `template.yaml`

**Step 1: Delete the AnalyticsRefreshFunction resource**

Find and delete the entire `AnalyticsRefreshFunction` resource block (approximately lines 990-1046):

```yaml
  # Lambda Function for Analytics Refresh (Docker Container)
  AnalyticsRefreshFunction:
    Type: AWS::Serverless::Function
    DependsOn:
      - MountTarget
    Properties:
      PackageType: Image
      ...
    Metadata:
      DockerTag: latest
      DockerContext: .
      Dockerfile: api/analytics/Dockerfile
```

Delete this entire block.

**Step 2: Update the Outputs section**

Find and update the output (around line 1452):
```yaml
  AnalyticsRefreshFunctionArn:
    Description: ARN of the Analytics Refresh Lambda function
    Value: !GetAtt AnalyticsRefreshFunction.Arn
```

Replace with:
```yaml
  AnalyticsTriggerFunctionArn:
    Description: ARN of the Analytics Trigger Lambda function
    Value: !GetAtt AnalyticsTriggerFunction.Arn

  AnalyticsJobQueueArn:
    Description: ARN of the Analytics Batch Job Queue
    Value: !Ref AnalyticsJobQueue

  AnalyticsJobDefinitionArn:
    Description: ARN of the Analytics Batch Job Definition
    Value: !Ref AnalyticsJobDefinition
```

**Step 3: Commit**

```bash
git add template.yaml
git commit -m "infra: remove old AnalyticsRefreshFunction Lambda

Replace with Batch-based analytics. Update outputs to expose
trigger Lambda ARN and Batch job queue/definition ARNs."
```

---

## Task 11: Update trigger-analytics-refresh.sh Script

**Files:**
- Modify: `scripts/trigger-analytics-refresh.sh`

**Step 1: Update script to invoke trigger Lambda**

Replace entire file with:

```bash
#!/bin/bash

# CocktailDB Analytics Refresh Script
# Triggers the analytics Batch job via the trigger Lambda

set -e  # Exit on any error

# Parse arguments
TARGET_ENV="$1"

# Default to dev if no environment specified
if [ -z "$TARGET_ENV" ]; then
    echo "No environment specified, defaulting to 'dev'."
    TARGET_ENV="dev"
fi

# Validate environment
if [ "$TARGET_ENV" != "dev" ] && [ "$TARGET_ENV" != "prod" ]; then
    echo "Error: Invalid environment '$TARGET_ENV'. Use 'dev' or 'prod'."
    exit 1
fi

# Change to project root
cd "$(dirname "$0")/.."

# Define deployment variables
STACK_NAME="cocktail-db-${TARGET_ENV}"
REGION="us-east-1"

echo "Triggering analytics refresh for environment: $TARGET_ENV"
echo "Stack name: $STACK_NAME"
echo ""

# Get the analytics trigger function ARN from CloudFormation outputs
echo "Getting Analytics Trigger Function ARN..."
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='AnalyticsTriggerFunctionArn'].OutputValue" \
    --output text \
    --region "$REGION")

if [ -z "$FUNCTION_ARN" ] || [ "$FUNCTION_ARN" = "None" ]; then
    echo "Error: Could not retrieve Analytics Trigger Function ARN from CloudFormation outputs"
    echo "Please check if the stack '$STACK_NAME' exists and has been deployed successfully"
    exit 1
fi

echo "Found function ARN: $FUNCTION_ARN"
echo ""

# Invoke the trigger Lambda function
echo "Invoking analytics trigger function..."
RESPONSE=$(aws lambda invoke \
    --function-name "$FUNCTION_ARN" \
    --invocation-type RequestResponse \
    --region "$REGION" \
    --payload '{}' \
    /dev/stdout 2>&1)

# Check if invocation succeeded
if [ $? -ne 0 ]; then
    echo "Error invoking Lambda function"
    echo "$RESPONSE"
    exit 1
fi

echo "Trigger Lambda invoked successfully!"
echo ""
echo "Response:"
echo "$RESPONSE" | tail -n 1 | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "Batch job submitted! Check AWS Batch console for job status."
echo "Job queue: cocktail-db-${TARGET_ENV}-analytics"
```

**Step 2: Commit**

```bash
git add scripts/trigger-analytics-refresh.sh
git commit -m "script: update trigger script for Batch

Invoke trigger Lambda instead of analytics Lambda directly.
Output now shows Batch job submission confirmation."
```

---

## Task 12: Build and Deploy to Dev

**Step 1: Build the SAM application**

Run:
```bash
sam build --template-file template.yaml
```

Expected: Build succeeds, shows built resources including new Batch resources

**Step 2: Deploy to dev**

Run:
```bash
sam deploy --config-env dev
```

Expected: Deployment succeeds, new Batch resources created

**Step 3: Commit any SAM-generated changes**

```bash
git add samconfig.toml .aws-sam/build.toml 2>/dev/null || true
git commit -m "build: update SAM config after Batch migration" || true
```

---

## Task 13: Test the Migration

**Step 1: Trigger analytics refresh via script**

Run:
```bash
./scripts/trigger-analytics-refresh.sh dev
```

Expected: Output shows Batch job submitted with jobId

**Step 2: Monitor Batch job**

Run:
```bash
aws batch describe-jobs --jobs <JOB_ID_FROM_STEP_1> --region us-east-1
```

Or check AWS Batch console for job status.

Expected: Job transitions SUBMITTED → PENDING → RUNNABLE → STARTING → RUNNING → SUCCEEDED

**Step 3: Verify analytics were generated**

Run:
```bash
curl -s "https://<API_ENDPOINT>/api/v1/analytics/ingredient-usage" | head -c 500
```

Expected: JSON response with ingredient usage data

**Step 4: Commit verification notes**

```bash
git add docs/plans/2025-11-30-analytics-batch-migration.md
git commit -m "docs: mark Batch migration as verified in dev"
```

---

## Task 14: Deploy to Production

**Step 1: Deploy to prod**

Run:
```bash
sam deploy --config-env prod
```

Expected: Deployment succeeds

**Step 2: Test prod**

Run:
```bash
./scripts/trigger-analytics-refresh.sh prod
```

Expected: Batch job submitted and completes successfully

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Refactor analytics_refresh.py - extract core logic |
| 2 | Update Dockerfile for Batch |
| 3 | Create trigger Lambda |
| 4 | Update analytics_helpers.py |
| 5 | Add Batch IAM roles |
| 6 | Add security group and compute environment |
| 7 | Add job definition |
| 8 | Add trigger Lambda to template |
| 9 | Update CocktailLambda env var |
| 10 | Remove old AnalyticsRefreshFunction |
| 11 | Update trigger script |
| 12 | Build and deploy to dev |
| 13 | Test the migration |
| 14 | Deploy to production |
