# CloudWatch Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship all EC2 logs (API container, backup/analytics services, Caddy) to CloudWatch with proper retention policies.

**Architecture:** Docker's built-in `awslogs` driver for the API container (zero additional software), CloudWatch Agent for systemd journal logs (backup, analytics) and Caddy file-based access logs. Log groups pre-created via CloudFormation with environment-specific retention. IAM permissions scoped to `/cocktaildb/{env}/*`.

**Tech Stack:** AWS CloudWatch Logs, Docker awslogs driver, Amazon CloudWatch Agent, CloudFormation, Ansible

**Tradeoff:** With `awslogs`, `docker logs` no longer works on the instance. Use `aws logs tail /cocktaildb/{env}/api --follow` instead.

**Log Groups:**

| Log Group | Source | Retention |
|-----------|--------|-----------|
| `/cocktaildb/{env}/api` | Docker awslogs driver | 30d dev / 90d prod |
| `/cocktaildb/{env}/backup` | CW Agent (journald) | 30d |
| `/cocktaildb/{env}/analytics` | CW Agent (journald) | 14d |
| `/cocktaildb/{env}/caddy` | CW Agent (file) | 14d dev / 30d prod |

**Deployment Order:** IAM policy → log groups stack → provision (install agent) → deploy (config + docker-compose)

---

### Task 1: Add CloudWatch Logs IAM Policy

**Files:**
- Modify: `infrastructure/cloudformation/ec2-iam.yaml:33-50`

**Step 1: Add the CloudWatchLogsAccess policy**

Add a second policy entry to `EC2Role.Properties.Policies`, after the existing `S3Access` policy:

```yaml
        - PolicyName: CloudWatchLogsAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                  - logs:DescribeLogStreams
                Resource:
                  - !Sub arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/cocktaildb/${Environment}/*
                  - !Sub arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/cocktaildb/${Environment}/*:*
```

**Step 2: Validate the template**

Run: `aws cloudformation validate-template --template-body file://infrastructure/cloudformation/ec2-iam.yaml`
Expected: Valid template response with parameters listed

**Step 3: Deploy to dev**

Run: `aws cloudformation deploy --template-file infrastructure/cloudformation/ec2-iam.yaml --stack-name cocktaildb-ec2-dev --parameter-overrides Environment=dev --capabilities CAPABILITY_NAMED_IAM`
Expected: Stack update completes successfully

**Step 4: Deploy to prod**

Run: `aws cloudformation deploy --template-file infrastructure/cloudformation/ec2-iam.yaml --stack-name cocktaildb-ec2-prod --parameter-overrides Environment=prod --capabilities CAPABILITY_NAMED_IAM`
Expected: Stack update completes successfully

**Step 5: Commit**

```bash
git add infrastructure/cloudformation/ec2-iam.yaml
git commit -m "feat: add CloudWatch Logs IAM policy to EC2 role"
```

---

### Task 2: Create CloudWatch Log Groups via CloudFormation

**Files:**
- Create: `infrastructure/cloudformation/cloudwatch-logs.yaml`

**Step 1: Create the log groups stack template**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: CocktailDB CloudWatch Log Groups

Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, prod]
    Description: The deployment environment

Conditions:
  IsProd: !Equals [!Ref Environment, prod]

Resources:
  ApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub /cocktaildb/${Environment}/api
      RetentionInDays: !If [IsProd, 90, 30]
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Project
          Value: cocktaildb

  BackupLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub /cocktaildb/${Environment}/backup
      RetentionInDays: 30
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Project
          Value: cocktaildb

  AnalyticsLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub /cocktaildb/${Environment}/analytics
      RetentionInDays: 14
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Project
          Value: cocktaildb

  CaddyLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub /cocktaildb/${Environment}/caddy
      RetentionInDays: !If [IsProd, 30, 14]
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Project
          Value: cocktaildb

Outputs:
  ApiLogGroupName:
    Value: !Ref ApiLogGroup
  BackupLogGroupName:
    Value: !Ref BackupLogGroup
  AnalyticsLogGroupName:
    Value: !Ref AnalyticsLogGroup
  CaddyLogGroupName:
    Value: !Ref CaddyLogGroup
```

**Step 2: Validate the template**

Run: `aws cloudformation validate-template --template-body file://infrastructure/cloudformation/cloudwatch-logs.yaml`
Expected: Valid template response

**Step 3: Deploy to dev**

Run: `aws cloudformation deploy --template-file infrastructure/cloudformation/cloudwatch-logs.yaml --stack-name cocktaildb-logs-dev --parameter-overrides Environment=dev`
Expected: Stack creates 4 log groups

**Step 4: Verify log groups exist**

Run: `aws logs describe-log-groups --log-group-name-prefix /cocktaildb/dev/ --query 'logGroups[*].[logGroupName, retentionInDays]' --output table`
Expected: 4 log groups with correct retention values (30, 30, 14, 14)

**Step 5: Deploy to prod**

Run: `aws cloudformation deploy --template-file infrastructure/cloudformation/cloudwatch-logs.yaml --stack-name cocktaildb-logs-prod --parameter-overrides Environment=prod`
Expected: Stack creates 4 log groups

**Step 6: Commit**

```bash
git add infrastructure/cloudformation/cloudwatch-logs.yaml
git commit -m "feat: add CloudWatch log group definitions with retention policies"
```

---

### Task 3: Switch Docker to awslogs Driver

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.dev.yml`

**Step 1: Update docker-compose.prod.yml**

Replace the existing `logging` block (lines 7-11):

```yaml
# docker-compose.prod.yml
# Production overrides for CocktailDB

services:
  api:
    image: cocktaildb-api:latest
    logging:
      driver: "awslogs"
      options:
        awslogs-region: "us-east-1"
        awslogs-group: "/cocktaildb/${ENVIRONMENT}/api"
        awslogs-stream-prefix: "api"
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

The `ENVIRONMENT` variable is already set in `.env` via `infrastructure/ansible/files/env.j2` (line 25: `ENVIRONMENT={{ app_env }}`). Docker Compose substitutes it automatically.

**Step 2: Add logging to docker-compose.dev.yml**

Add a `logging` block to the dev compose file (used on dev EC2 instance, not local laptops):

```yaml
# docker-compose.dev.yml
# Development overrides for local testing

services:
  api:
    build:
      context: ./api
      dockerfile: Dockerfile.prod
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
    logging:
      driver: "awslogs"
      options:
        awslogs-region: "us-east-1"
        awslogs-group: "/cocktaildb/dev/api"
        awslogs-stream-prefix: "api"
    ports:
      - "8000:8000"  # Expose to all interfaces for local dev
    volumes:
      # Mount code for hot-reload (optional - remove for production-like testing)
      # - ./api:/app:ro
```

Note: The base `docker-compose.yml` keeps `json-file` driver so local laptop development still uses `docker logs` normally. The dev/prod overrides switch to `awslogs` for EC2.

**Step 3: Validate compose config**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet`
Expected: No errors (validates variable substitution and structure)

**Step 4: Commit**

```bash
git add docker-compose.prod.yml docker-compose.dev.yml
git commit -m "feat: switch Docker logging to CloudWatch awslogs driver"
```

---

### Task 4: Install CloudWatch Agent via Ansible

**Files:**
- Modify: `infrastructure/ansible/playbooks/provision.yml:11-22`

**Step 1: Add the package**

Add `amazon-cloudwatch-agent` to the `packages` list in `provision.yml` (after `rsync`):

```yaml
  vars:
    packages:
      - docker
      - postgresql16-server
      - postgresql16
      - postgresql16-contrib
      - python3
      - python3-pip
      - git
      - htop
      - tmux
      - awscli
      - rsync
      - amazon-cloudwatch-agent
```

This is available via dnf on Amazon Linux 2023.

**Step 2: Add enable task**

Add after the "Install required packages" task (after line 33):

```yaml
    # CloudWatch Agent setup
    - name: Enable CloudWatch Agent service
      systemd:
        name: amazon-cloudwatch-agent
        enabled: yes
```

Don't start it yet — it needs a config file first (deployed in Task 6).

**Step 3: Commit**

```bash
git add infrastructure/ansible/playbooks/provision.yml
git commit -m "feat: install CloudWatch Agent in provisioning playbook"
```

---

### Task 5: Create CloudWatch Agent Config Template

**Files:**
- Create: `infrastructure/ansible/files/cloudwatch-agent-config.json.j2`

**Step 1: Create the agent config template**

Reference: `infrastructure/ansible/files/env.j2` uses `app_env` for the environment name (values: `dev` or `prod`).

```json
{
  "agent": {
    "run_as_user": "root"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/caddy/access.log",
            "log_group_name": "/cocktaildb/{{ app_env }}/caddy",
            "log_stream_name": "{instance_id}/caddy-access",
            "timezone": "UTC"
          }
        ]
      },
      "journald": {
        "collect_list": [
          {
            "unit": "cocktaildb-backup.service",
            "log_group_name": "/cocktaildb/{{ app_env }}/backup",
            "log_stream_name": "{instance_id}/backup"
          },
          {
            "unit": "cocktaildb-analytics.service",
            "log_group_name": "/cocktaildb/{{ app_env }}/analytics",
            "log_stream_name": "{instance_id}/analytics"
          },
          {
            "unit": "cocktaildb-analytics-debounce.service",
            "log_group_name": "/cocktaildb/{{ app_env }}/analytics",
            "log_stream_name": "{instance_id}/analytics-debounce"
          }
        ]
      }
    }
  }
}
```

**Step 2: Commit**

```bash
git add infrastructure/ansible/files/cloudwatch-agent-config.json.j2
git commit -m "feat: add CloudWatch Agent config template for journal and Caddy logs"
```

---

### Task 6: Deploy Agent Config via Ansible

**Files:**
- Modify: `infrastructure/ansible/playbooks/deploy.yml`

**Step 1: Add config deployment tasks**

Add after the "Copy analytics debounce script" task (after line 131) and before the Caddy configuration section:

```yaml
    # CloudWatch Agent configuration
    - name: Deploy CloudWatch Agent configuration
      template:
        src: ../files/cloudwatch-agent-config.json.j2
        dest: /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
        owner: root
        group: root
        mode: '0644'
      notify: Restart CloudWatch Agent

    - name: Apply CloudWatch Agent configuration
      command: >
        /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
        -a fetch-config
        -m ec2
        -s
        -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
      changed_when: false
```

**Step 2: Add the handler**

Add to the `handlers` section (after the existing handlers):

```yaml
    - name: Restart CloudWatch Agent
      command: >
        /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
        -a fetch-config
        -m ec2
        -s
        -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

**Step 3: Commit**

```bash
git add infrastructure/ansible/playbooks/deploy.yml
git commit -m "feat: add CloudWatch Agent config deployment to Ansible"
```

---

### Task 7: Deploy and Verify (Dev)

**Step 1: Run provision on dev**

Run: `cd infrastructure/ansible && ansible-playbook -i inventory/dev.yml playbooks/provision.yml`
Expected: `amazon-cloudwatch-agent` installed, service enabled

**Step 2: Run deploy on dev**

Run: `cd infrastructure/ansible && ansible-playbook -i inventory/dev.yml playbooks/deploy.yml`
Expected: Agent config deployed, API container restarted with awslogs driver

**Step 3: Verify API logs in CloudWatch**

Run: `aws logs tail /cocktaildb/dev/api --follow`
Expected: API startup logs appear (uvicorn worker messages)

**Step 4: Verify CloudWatch Agent status**

SSH to dev instance and run: `sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status`
Expected: Status shows running with the config file loaded

**Step 5: Trigger a backup to test journal shipping**

SSH to dev instance and run: `sudo systemctl start cocktaildb-backup.service`
Then: `aws logs tail /cocktaildb/dev/backup --since 5m`
Expected: Backup log entries appear

**Step 6: Verify Caddy logs**

Run: `aws logs tail /cocktaildb/dev/caddy --since 5m`
Expected: Access log entries from Caddy (may need to hit the site first)
