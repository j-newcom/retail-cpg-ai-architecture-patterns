# Deployment Guide

Step-by-step instructions for deploying the Agentic Supply Chain system to an AWS account.

## Prerequisites

| Requirement | Details |
|---|---|
| AWS Account | With Bedrock model access enabled for Claude Sonnet |
| AWS CDK v2 | `npm install -g aws-cdk` (v2.140.0+) |
| Python 3.11+ | For CDK app and Lambda code |
| VPC | With at least 2 private subnets across 2 AZs |
| ERP Connectivity | VPN or Direct Connect to on-premises ERP |
| Bedrock Access | Request model access for `anthropic.claude-sonnet-4-20250514` in target region |

## Step 1: Enable Bedrock Model Access

1. Open the [Bedrock console](https://console.aws.amazon.com/bedrock/) in your target region
2. Navigate to **Model access** in the left nav
3. Click **Manage model access**
4. Enable **Anthropic Claude Sonnet** (and optionally Claude Haiku as fallback)
5. Wait for access status to show "Access granted" (typically immediate for on-demand)

## Step 2: Store ERP Credentials

Create a secret in Secrets Manager for your ERP API credentials:

```bash
aws secretsmanager create-secret \
  --name erp/api-credentials \
  --description "ERP API credentials for supply chain agent integration" \
  --secret-string '{"erp_base_url":"https://your-erp.example.com/api","api_token":"YOUR_TOKEN","api_user":"svc-supply-chain-agent"}'
```

## Step 3: Configure Agent Parameters

Edit `config/agent-config.yaml` to set your environment-specific values:

- **region** — AWS region for deployment
- **confidence thresholds** — Start conservative (0.80+), loosen as you calibrate
- **guardrail limits** — Set based on your approval matrix and risk tolerance
- **model_id** — Update if using a different Bedrock model version

## Step 4: Bootstrap CDK

If this is your first CDK deployment in this account/region:

```bash
cd aws-implementation/cdk
cdk bootstrap aws://ACCOUNT_ID/REGION
```

## Step 5: Deploy

Deploy all stacks in dependency order:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Deploy all stacks
cdk deploy --all --require-approval broadening
```

CDK will prompt you to approve IAM policy changes. Review them against the policies in the `policies/` directory to verify they match expectations.

**Deployment order (handled automatically by CDK dependencies):**
1. SupplyChainEventBus
2. SupplyChainReasoning
3. SupplyChainAgents
4. SupplyChainIntegration
5. SupplyChainMonitoring

## Step 6: Verify Deployment

After deployment completes:

```bash
# Verify EventBridge bus exists
aws events describe-event-bus --name supply-chain-events

# Verify Lambda functions deployed
aws lambda list-functions --query "Functions[?starts_with(FunctionName, 'sc-agent')].[FunctionName, Runtime, MemorySize]" --output table

# Verify CloudWatch dashboard
aws cloudwatch list-dashboards --query "DashboardEntries[?DashboardName=='SupplyChainAgents']"

# Test the demand sensing agent with a synthetic event
aws events put-events --entries '[{
  "Source": "supply-chain.signal.test",
  "DetailType": "SocialSignalUpdate",
  "EventBusName": "supply-chain-events",
  "Detail": "{\"signal_type\":\"social_media\",\"metric\":\"mentions_up_200pct\",\"region\":\"chicago_metro\",\"category\":\"oat_milk\"}"
}]'
```

Check CloudWatch Logs for the demand-sensing Lambda to verify it processed the event.

## Step 7: Shadow Mode (Weeks 1-4)

Before enabling autonomous execution, run agents in shadow mode:

1. Set all confidence thresholds to `1.0` in `agent-config.yaml` (forces all decisions to escalate)
2. Deploy with `cdk deploy --all`
3. Monitor the escalation queue — every decision routes to human review
4. Compare agent recommendations against human decisions for 4 weeks
5. Track accuracy: what percentage of agent recommendations match the human's final action?

Once accuracy exceeds 85% for a given agent, lower its threshold to the production value and redeploy.

## Step 8: Production Cutover

1. Lower confidence thresholds to production values (per agent-config.yaml)
2. Verify monitoring alarms are configured and tested
3. Confirm on-call rotation is staffed
4. Deploy with `cdk deploy --all`
5. Monitor the CloudWatch dashboard for the first 48 hours

## Teardown

To remove all resources:

```bash
cdk destroy --all
```

Note: S3 buckets with `RemovalPolicy.RETAIN` (decision logs) and Neptune clusters will NOT be deleted automatically. Remove them manually if desired.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Lambda timeout (120s) | Bedrock cold start + complex prompt | Increase timeout to 180s or enable provisioned concurrency |
| "AccessDeniedException" on Bedrock | Model access not enabled | Step 1 above |
| SQS message stuck in queue | ERP integration Lambda failing | Check CloudWatch logs for erp-integration function |
| All decisions escalating | Confidence thresholds set to 1.0 (shadow mode) | Lower thresholds per Step 8 |
| Neptune connection refused | Lambda not in VPC or security group misconfigured | Verify Lambda VPC config and Neptune SG allows inbound on port 8182 |
