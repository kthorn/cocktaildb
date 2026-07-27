# CloudWatch Agent for Caddy Access Logs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Caddy access logs from the prod EC2 instance to CloudWatch Logs for ad-hoc traffic analysis via Logs Insights.

**Architecture:** Install the CloudWatch Agent on EC2 via Ansible, configure it to tail `/var/log/caddy/access.log` and send entries to a CloudWatch Logs group. IAM permissions added to the prod EC2 role via CloudFormation. Prod-only — no dev changes.

**Tech Stack:** CloudWatch Agent, CloudFormation (IAM), Ansible (provisioning)

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `infrastructure/cloudformation/ec2-iam.yaml` | Add CloudWatch Agent IAM policy to prod EC2 role |
| Create | `infrastructure/cloudwatch/amazon-cloudwatch-agent.json` | Agent config — what logs to collect and where to send them |
| Modify | `infrastructure/ansible/playbooks/provision.yml` | Install agent, deploy config, start service |

---

### Task 1: Add CloudWatch Agent IAM permissions to prod EC2 role

**Files:**
- Modify: `infrastructure/cloudformation/ec2-iam.yaml:17-55` (EC2Role resource)

- [ ] **Step 1: Add the managed policy to EC2Role**

In `infrastructure/cloudformation/ec2-iam.yaml`, add a `ManagedPolicyArns` property to the `EC2Role` resource, after the existing `Policies` block (after line 51, before `Tags`):

```yaml
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
```

The full `EC2Role` resource should look like:

```yaml
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
                  # Analytics bucket
                  - !Sub arn:aws:s3:::cocktailanalytics-${AWS::AccountId}-${Environment}
                  - !Sub arn:aws:s3:::cocktailanalytics-${AWS::AccountId}-${Environment}/*
                  # Backup bucket (prod only, but safe to include for dev)
                  - !Sub arn:aws:s3:::cocktaildbbackups-${AWS::AccountId}-${Environment}
                  - !Sub arn:aws:s3:::cocktaildbbackups-${AWS::AccountId}-${Environment}/*
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Project
          Value: cocktaildb
```

- [ ] **Step 2: Validate the template**

Run:
```bash
aws cloudformation validate-template --template-body file://infrastructure/cloudformation/ec2-iam.yaml
```
Expected: No errors, returns template description and parameters.

- [ ] **Step 3: Commit**

```bash
git add infrastructure/cloudformation/ec2-iam.yaml
git commit -m "feat: add CloudWatch Agent IAM permissions to prod EC2 role"
```

---

### Task 2: Create CloudWatch Agent config file

**Files:**
- Create: `infrastructure/cloudwatch/amazon-cloudwatch-agent.json`

- [ ] **Step 1: Create the config directory and file**

Create `infrastructure/cloudwatch/amazon-cloudwatch-agent.json`:

```json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/caddy/access.log",
            "log_group_name": "/cocktaildb/prod/caddy-access",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC",
            "retention_in_days": 30
          }
        ]
      }
    }
  }
}
```

- [ ] **Step 2: Validate the JSON is well-formed**

Run:
```bash
python3 -c "import json; json.load(open('infrastructure/cloudwatch/amazon-cloudwatch-agent.json')); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add infrastructure/cloudwatch/amazon-cloudwatch-agent.json
git commit -m "feat: add CloudWatch Agent config for Caddy access logs"
```

---

### Task 3: Add CloudWatch Agent installation to Ansible provisioning

**Files:**
- Modify: `infrastructure/ansible/playbooks/provision.yml:211-231` (after Caddy log directory setup, before Python packages)

- [ ] **Step 1: Add agent tasks to provision.yml**

Insert the following block after the "Enable Caddy" task (after line 231) and before the "Install Python packages" comment (line 233):

```yaml
    # CloudWatch Agent for log shipping
    - name: Check if CloudWatch Agent is installed
      command: rpm -q amazon-cloudwatch-agent
      register: cw_agent_installed
      changed_when: false
      failed_when: false

    - name: Download CloudWatch Agent RPM
      get_url:
        url: "https://amazoncloudwatch-agent.s3.amazonaws.com/amazon_linux/arm64/latest/amazon-cloudwatch-agent.rpm"
        dest: /tmp/amazon-cloudwatch-agent.rpm
      when: cw_agent_installed.rc != 0

    - name: Install CloudWatch Agent
      dnf:
        name: /tmp/amazon-cloudwatch-agent.rpm
        state: present
        disable_gpg_check: true
      when: cw_agent_installed.rc != 0

    - name: Deploy CloudWatch Agent config
      copy:
        src: ../../cloudwatch/amazon-cloudwatch-agent.json
        dest: /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
        owner: root
        group: root
        mode: '0644'
      notify: Restart CloudWatch Agent

    - name: Start and enable CloudWatch Agent
      shell: >
        /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
        -a fetch-config
        -m ec2
        -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
        -s
      args:
        creates: /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

- [ ] **Step 2: Add the handler for config changes**

Add this handler to the `handlers:` section at the bottom of `provision.yml` (after the existing "Daemon reload" handler):

```yaml
    - name: Restart CloudWatch Agent
      shell: >
        /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
        -a fetch-config
        -m ec2
        -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
        -s
```

- [ ] **Step 3: Validate the playbook syntax**

Run:
```bash
ansible-playbook --syntax-check -i infrastructure/ansible/inventory/prod.yml infrastructure/ansible/playbooks/provision.yml
```
Expected: `playbook: infrastructure/ansible/playbooks/provision.yml` (no errors)

- [ ] **Step 4: Commit**

```bash
git add infrastructure/ansible/playbooks/provision.yml
git commit -m "feat: add CloudWatch Agent installation and config to Ansible provisioning"
```

---

### Task 4: Deploy

This task is manual — run these commands yourself after the code changes are committed and pushed.

- [ ] **Step 1: Deploy CloudFormation stack update (IAM)**

```bash
aws cloudformation deploy \
  --template-file infrastructure/cloudformation/ec2-iam.yaml \
  --stack-name cocktaildb-prod-ec2 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=prod
```

Wait for completion. Verify:
```bash
aws cloudformation describe-stacks --stack-name cocktaildb-prod-ec2 --query 'Stacks[0].StackStatus'
```
Expected: `"UPDATE_COMPLETE"`

- [ ] **Step 2: Run Ansible provisioning on prod**

```bash
ansible-playbook -i infrastructure/ansible/inventory/prod.yml infrastructure/ansible/playbooks/provision.yml
```

Expected: Tasks for CloudWatch Agent show as "changed" on first run.

- [ ] **Step 3: Verify logs are flowing**

Wait 2-3 minutes for the agent to start shipping logs, then check:

```bash
aws logs describe-log-groups --log-group-name-prefix /cocktaildb/prod/caddy-access
```
Expected: Log group appears in the output.

```bash
aws logs filter-log-events \
  --log-group-name /cocktaildb/prod/caddy-access \
  --limit 5
```
Expected: Recent Caddy access log entries in JSON format.

- [ ] **Step 4: Test a Logs Insights query**

In the AWS Console, go to CloudWatch > Logs Insights, select `/cocktaildb/prod/caddy-access`, and run:

```
fields @timestamp, request.uri, status, duration
| stats count() as requests by request.uri
| sort requests desc
| limit 20
```

Or via CLI:
```bash
aws logs start-query \
  --log-group-name /cocktaildb/prod/caddy-access \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | limit 10'
```
