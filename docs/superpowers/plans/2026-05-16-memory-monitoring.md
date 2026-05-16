# Memory Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `mem_used_percent`, `mem_available`, and `swap_used` from the prod EC2 instance to CloudWatch every 60 seconds so we can right-size a future Lightsail tier.

**Architecture:** Extend the existing CloudWatch Agent config (already installed and running on prod) with a `metrics` block. No new packages, no IAM changes (the role already has `CloudWatchAgentServerPolicy`), no new files — one JSON edit + an Ansible provision run + verification.

**Tech Stack:** Amazon CloudWatch Agent, Ansible, AWS CLI (CloudWatch), bash.

**Spec:** `docs/superpowers/specs/2026-05-16-memory-monitoring-design.md`

---

## Pre-flight notes for the implementer

- The CloudWatch Agent config file is `infrastructure/cloudwatch/amazon-cloudwatch-agent.json` — a static JSON, not a Jinja template. Ansible copies it verbatim to `/etc/cocktaildb/amazon-cloudwatch-agent.json` on the instance.
- Running `playbooks/provision.yml` against prod is idempotent. The `Deploy CloudWatch Agent config` task detects a JSON content change and fires the `Restart CloudWatch Agent` handler, which calls `amazon-cloudwatch-agent-ctl -a fetch-config ... -s` to reload.
- The provision playbook reads `COCKTAILDB_DB_PASSWORD` from the env (used by postgres tasks which will no-op). You must export this before running.
- Prod inventory: host `54.208.125.45`, user `ec2-user`, key `~/.ssh/cocktaildb-ec2.pem`. SSH is direct (key-based), not Instance Connect.
- There are no automated tests for this config — verification is performed against CloudWatch and the agent's own status command after deploy.

---

## Task 1: Add memory and swap metrics to the agent config

**Files:**
- Modify: `infrastructure/cloudwatch/amazon-cloudwatch-agent.json`

- [ ] **Step 1: Replace the contents of the agent config file**

The current file contains only a `logs` section (Caddy access logs). Add a sibling `metrics` section. The full new file content:

```json
{
  "metrics": {
    "namespace": "CWAgent",
    "metrics_collected": {
      "mem": {
        "measurement": [
          "mem_used_percent",
          "mem_available"
        ],
        "metrics_collection_interval": 60
      },
      "swap": {
        "measurement": [
          "swap_used"
        ],
        "metrics_collection_interval": 60
      }
    },
    "append_dimensions": {
      "InstanceId": "${aws:InstanceId}"
    }
  },
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

Notes:
- `namespace: "CWAgent"` is the agent's documented default. Stating it explicitly avoids surprises.
- `${aws:InstanceId}` is a literal placeholder the agent resolves at runtime; it is NOT shell interpolation.
- `mem_available` is reported in **bytes** by the `mem` plugin. The console will display with unit auto-scaling.
- `swap_used` is reported in bytes. Non-zero sustained values indicate memory pressure.

- [ ] **Step 2: Validate JSON syntax locally**

Run: `python3 -m json.tool infrastructure/cloudwatch/amazon-cloudwatch-agent.json > /dev/null && echo OK`
Expected: `OK` (no JSON parse errors).

- [ ] **Step 3: Commit the change**

```bash
git add infrastructure/cloudwatch/amazon-cloudwatch-agent.json
git commit -m "$(cat <<'EOF'
feat(monitoring): collect mem and swap metrics via CloudWatch Agent

Adds a metrics block to the agent config for prod memory sizing
(Lightsail tier selection). Ships mem_used_percent, mem_available,
and swap_used to CWAgent namespace at 60s interval. ~$0.90/month
while running.

See docs/superpowers/specs/2026-05-16-memory-monitoring-design.md
EOF
)"
```

---

## Task 2: Deploy to prod and verify

**Files:** (none modified — deploy and verification only)

- [ ] **Step 1: Confirm preconditions**

Run: `aws cloudwatch list-metrics --namespace CWAgent --output text 2>&1 | head -5`
Expected: empty output (or no `Metrics` entries). This confirms there's a clear "before" state — anything that appears later is from our change.

Run: `aws ec2 describe-instances --instance-ids i-048ae4e6b93c1abdf --query 'Reservations[0].Instances[0].State.Name' --output text`
Expected: `running`. If `stopped`, abort and ask the user — the playbook will not deploy to a stopped instance.

- [ ] **Step 2: Run the provision playbook against prod**

Run (you must have `COCKTAILDB_DB_PASSWORD` exported in your shell first; do not hardcode it in the command):

```bash
cd infrastructure/ansible && ansible-playbook -i inventory/prod.yml playbooks/provision.yml
```

Expected output:
- All postgres/swap/docker/package tasks: `ok=...` (idempotent no-ops).
- `Deploy CloudWatch Agent config`: **`changed`** — this is the task that ships our JSON.
- `RUNNING HANDLER [Restart CloudWatch Agent]`: fires at the end of the play.
- `PLAY RECAP` shows `failed=0`.

If the `Deploy CloudWatch Agent config` task reports `ok` instead of `changed`, the playbook didn't see your edit — check that you committed against `main` and that the local working copy is the one Ansible reads from (it copies from the repo path, not git HEAD).

- [ ] **Step 3: Verify the agent loaded the new config**

SSH to prod and check agent status:

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@54.208.125.45 \
  'sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status'
```

Expected JSON output containing:
- `"status": "running"`
- `"configstatus": "configured"`
- A recent `starttime` (within the last minute or two)

If `configstatus` is `not configured` or status is `stopped`, dump the agent log for the failure reason:

```bash
ssh -i ~/.ssh/cocktaildb-ec2.pem ec2-user@54.208.125.45 \
  'sudo tail -50 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log'
```

Common causes: a JSON typo (would have been caught in Task 1 Step 2), a measurement name typo (e.g. `mem_avail` instead of `mem_available`), or a missing plugin name.

- [ ] **Step 4: Wait for the first metrics to land, then verify in CloudWatch**

The agent's first publish happens ~60 seconds after restart; CloudWatch indexing adds another minute or two. Wait ~3 minutes, then:

```bash
aws cloudwatch list-metrics --namespace CWAgent \
  --query 'Metrics[].MetricName' --output text | tr '\t' '\n' | sort -u
```

Expected output:
```
mem_available
mem_used_percent
swap_used
```

If output is empty after ~5 minutes, recheck Step 3 (agent status) — the most likely cause is a config the agent silently degraded.

- [ ] **Step 5: Confirm metrics have actual data points**

```bash
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
START=$(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
aws cloudwatch get-metric-statistics \
  --namespace CWAgent \
  --metric-name mem_used_percent \
  --dimensions Name=InstanceId,Value=i-048ae4e6b93c1abdf \
  --start-time "$START" --end-time "$END" \
  --period 60 --statistics Average Maximum \
  --query 'Datapoints[?Timestamp!=`null`] | sort_by(@, &Timestamp)' \
  --output table
```

Expected: at least one row with non-null `Average` and `Maximum` values between 0 and 100.

Repeat for `mem_available` and `swap_used` (substitute the `--metric-name`). For `swap_used`, a value of `0.0` is normal and expected on a healthy box — that's the baseline we're establishing.

- [ ] **Step 6: Regression check — confirm Caddy log shipping still works**

The same agent process ships both metrics and Caddy logs. A bad metrics config can in rare cases break the whole agent, so confirm logs are still flowing:

```bash
aws logs tail /cocktaildb/prod/caddy-access --since 5m | head -5
```

Expected: at least one recent log line. If empty, hit the site once (e.g. `curl -sI https://mixology.tools/`) and retry — there may simply have been no traffic in the window.

- [ ] **Step 7: No commit needed**

This task makes no code changes. Mark the task complete in any tracking tool and notify the user that the measurement campaign has started.

---

## Rollback procedure

If anything in Task 2 goes wrong and you need to revert immediately (e.g., the agent stops, logs stop flowing, the box otherwise misbehaves):

1. `git revert <commit-sha-from-task-1>` and push.
2. Re-run `ansible-playbook -i inventory/prod.yml playbooks/provision.yml` — this restores the logs-only config and restarts the agent.
3. Verify recovery with `aws logs tail /cocktaildb/prod/caddy-access --since 5m`.

---

## Follow-up (out of scope for this plan)

After ~3–4 weeks, a follow-up plan should:

1. Pull `Maximum` and `p95` of `mem_used_percent` and `mem_available` over the window via `get-metric-statistics`.
2. Map peak working-set to the smallest viable Lightsail tier.
3. Remove the `metrics` block from `infrastructure/cloudwatch/amazon-cloudwatch-agent.json`, re-run provision, and confirm only Caddy logs continue shipping.

That plan should be written separately when the data is in.
