# Memory Monitoring for Lightsail Sizing — Design

**Date:** 2026-05-16
**Status:** Draft (pending user review)
**Goal:** Collect ~3–4 weeks of memory and swap data from the production EC2 instance to right-size a future Lightsail tier (and potentially downsize current EC2). Minimize cost.

## Context

We're exploring migration from EC2 to Lightsail. Lightsail tiers are fixed (512 MB / 1 / 2 / 4 / 8 / 16 / 32 GB RAM), so picking the right tier requires actual peak memory data — which we don't have. The host runs PostgreSQL, the FastAPI container, and Caddy on a single instance; only system-wide totals matter for tier selection.

Audit of current observability:

- `CocktailDB` and `CWAgent` CloudWatch namespaces are **empty** — no custom metrics today.
- AWS/EC2 default metrics are present for free at 5-min resolution: CPU, network, EBS, CPU credits, status checks. **Memory and swap are not** — those are Linux agent-side only.
- Detailed (1-min) EC2 monitoring is disabled on prod. We will not enable it.
- CloudWatch Agent is **already installed** on EC2 via `infrastructure/ansible/playbooks/provision.yml` and currently ships only Caddy access logs.
- The EC2 IAM role has the AWS managed policy `CloudWatchAgentServerPolicy` attached, which already grants `cloudwatch:PutMetricData`. No IAM changes required.
- A 2 GB swap file exists with `vm.swappiness=10`, so non-zero swap usage is a meaningful "memory pressure" signal.

## Decision

Extend the existing CloudWatch Agent config (`infrastructure/cloudwatch/amazon-cloudwatch-agent.json`) with a `metrics` block that ships three system-wide metrics from the **prod** instance only.

### Metrics

| Metric | Source plugin | Purpose |
|---|---|---|
| `mem_used_percent` | `mem` | Primary sizing signal — pick the smallest Lightsail tier where p95 stays under ~70%. |
| `mem_available` | `mem` | Absolute MB headroom (avoids math against total when comparing to tier sizes). |
| `swap_used` | `swap` | Any sustained non-zero value = RAM is the bottleneck, regardless of `mem_used_percent`. |

- **Cadence:** 60 seconds. Per-metric pricing is flat regardless of cadence; 60s catches analytics-refresh spikes that 5-min would miss.
- **Namespace:** `CWAgent` (the agent default — keeps things discoverable in the standard CloudWatch UI).
- **Dimensions:** `InstanceId` only (the agent's default `append_dimensions`). Single prod instance, so no need for an `Environment` dimension.
- **Per-process / procstat:** Explicitly **out of scope**. If system-wide shows headroom, we don't care which process is using it. If system is tight, we add procstat then.

### Cost

3 custom metrics × $0.30/month = **$0.90/month** while the campaign runs. PutMetricData API requests are within the 1 B/month free tier. Total expected spend: ~$2.70–$3.60 over the 3–4 week window.

### Scope: prod only

Only the prod EC2 instance (`i-048ae4e6b93c1abdf`) is currently running. Dev is stopped and would not produce representative sizing data anyway. The agent config file is shared across environments, so the metrics block applies wherever the agent runs — if dev is later started, it will begin emitting too. That's fine and incurs at most another $0.90/month, but is not the intent.

## Implementation outline

The implementation plan (created next) will cover at least:

1. **Edit** `infrastructure/cloudwatch/amazon-cloudwatch-agent.json` to add a `metrics` section alongside the existing `logs` section. The new block will declare `mem` (measurement: `mem_used_percent`, `mem_available`), `swap` (measurement: `swap_used`), and `metrics_collection_interval: 60`.
2. **Deploy** by running the existing provision playbook against prod (`ansible-playbook -i inventory/prod.yml playbooks/provision.yml`). The playbook already copies the JSON to `/etc/cocktaildb/` and fires the `Restart CloudWatch Agent` handler when the file changes.
3. **Verify** within ~5 minutes via `aws cloudwatch list-metrics --namespace CWAgent` showing the three metric names with the prod `InstanceId` dimension, and a `get-metric-statistics` call returning recent datapoints.
4. **Commit** the JSON change.

## Analysis plan

After 3–4 weeks (covers at least one full analytics refresh cycle plus weekday/weekend traffic variance):

- Pull `Maximum` and `p95` of `mem_used_percent` and `mem_available` over the window via `aws cloudwatch get-metric-statistics` (or the console).
- Pull `Maximum` of `swap_used` — any sustained non-zero value rules out the next-smaller tier.
- Map the peak `mem_available` to the smallest Lightsail tier that leaves a reasonable buffer (rule of thumb: stay at least 1.3× peak working-set size to absorb growth and transient spikes).

## Cleanup

After the tier decision is made, delete the `metrics` block from `infrastructure/cloudwatch/amazon-cloudwatch-agent.json` and redeploy. The agent continues shipping Caddy logs. Custom-metric billing stops within the next CloudWatch billing cycle.

## Out of scope

- CloudWatch dashboards or alarms (use ad-hoc Metrics console views).
- Per-process / per-container memory breakdown via `procstat` or cAdvisor.
- Disk usage metrics (could be added later for $0.30/month if Lightsail SSD sizing becomes uncertain).
- CPU metrics (already free via AWS/EC2 namespace).
- Memory monitoring on the dev instance.
- Any changes to the Lightsail migration itself — this spec only adds measurement.
