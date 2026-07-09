# Operational Runbook

Procedures for the top 10 operational scenarios encountered while running the agentic supply chain system.

## Scenario 1: Circuit Breaker Tripped

**Symptom:** CloudWatch alarm "CircuitBreakerAlarm" fires. All agents stop making autonomous decisions.

**Impact:** No new decisions execute until manual acknowledgment. Escalation queue fills.

**Root cause:** Decision volume exceeded 1,000/hour threshold, indicating either legitimate demand surge or a feedback loop between agents.

**Response:*\

\Check CloudWatch dashboard — identify which agent(s) are producing the volume spik\

\Check for oscillation pattern: Agent A adjusting, Agent B reacting, Agent A re-adjustin\

\If oscillation: identify the triggering event and suppress the feedback loop by temporarily disabling one agent's subscription to the other's event\

\If legitimate surge (e.g., major disruption): raise the circuit breaker threshold temporarily, acknowledge the alarm, and monito\

\Document the incident in the decision log

**Prevention:** Tune per-agent cooldown periods in `agent-config.yaml`. Ensure the demand sensing agent's `cooldown_seconds` prevents rapid-fire adjustments.

---

## Scenario 2: Bedrock Throttling

**Symptom:** Lambda errors with "ThrottlingException" from Bedrock. Agent decisions fail or timeout.

**Impact:** Agents cannot reason. Decisions either fail or fall back to the Haiku model (lower quality).

**Response:*\

\Check [Service Quotas](https://console.aws.amazon.com/servicequotas/) for Bedrock invoke limit\

\If at quota: request increase via Service Quotas console (approved within hours for modest increases\

\Immediate mitigation: reduce `reserved_concurrent_executions` per agent to spread loa\

\If persistent: enable the fallback model (Claude Haiku) in agent-config.yaml — lower quality but unthrottled for most accounts

**Prevention:** Set `reserved_concurrent_executions` per Lambda to stay within Bedrock's per-model tokens-per-minute limit. Monitor the `Bedrock/InvocationsThrottled` CloudWatch metric.

---

## Scenario 3: ERP Integration Failures

**Symptom:** Messages accumulating in `erp-decision-queue.fifo`. CloudWatch metric `ERPExecutionFailed` elevated.

**Impact:** Agent decisions are made but not executed. Supply chain actions stall.

**Response:*\

\Check the ERP integration Lambda logs for error detail\

\Common causes: ERP maintenance window, expired API token, network connectivity los\

\If credential issue: rotate the secret in Secrets Manager, Lambda will pick up new value on next cold star\

\If connectivity: verify VPN/Direct Connect status, check security group rule\

\Messages remain in FIFO queue and will retry automatically. Do NOT manually delete them\

\If DLQ is filling: messages have exceeded max retry attempts. Review DLQ contents and manually resolve or replay after fixing the root cause.

**Prevention:** Set up a CloudWatch alarm on SQS `ApproximateAgeOfOldestMessage` for the ERP queue. Alert if messages are older than 30 minutes.

---

## Scenario 4: Agent Producing Low-Confidence Decisions Consistently

**Symptom:** High escalation rate (>80%) for a specific agent over 24+ hours. Planner queue overwhelmed.

**Impact:** The value proposition breaks down — planners spend more time reviewing agent recommendations than making decisions themselves.

**Response:*\

\Identify the agent and check recent signal quality — has input data degraded\

\Check if a data source went stale (e.g., POS feed stopped refreshing, weather API returning errors\

\If data quality issue: fix upstream, agent confidence will recove\

\If model calibration drift: the signal landscape may have changed. Schedule a prompt review session\

\Temporary mitigation: raise the agent's confidence threshold by 0.10 to reduce volume of low-quality escalations

**Prevention:** Monitor the `ConfidenceScore` metric per agent. Set an alarm when 7-day average drops below the threshold by more than 0.10.

---

## Scenario 5: Escalation Queue SLA Breach

**Symptom:** Decisions sitting in escalation queue longer than 4 hours without human action.

**Impact:** Time-sensitive decisions (disruption responses, expedite requests) become stale. Downstream agents operating on outdated assumptions.

**Response:*\

\Notify planning team via SNS/Slack escalatio\

\If specific planner overloaded: redistribute queue items to backup planner\

\For stale decisions (>8 hours): re-run the agent to generate a fresh recommendation with updated contex\

\Review whether the threshold that triggered the escalation can be widened without increasing risk

**Prevention:** Implement tiered escalation — if primary planner doesn't respond in 2 hours, route to their manager. Never auto-approve stale decisions.

---

## Scenario 6: Neptune Database Performance Degradation

**Symptom:** Agent Lambda duration increases. CloudWatch metric `NeptuneClusterStatus` shows elevated latency.

**Impact:** Agents take longer to gather context, potentially hitting timeouts.

**Response:*\

\Check Neptune CloudWatch metrics: `GremlinRequestsPerSec`, `GremlinLatency`, `CPUUtilization\

\If capacity issue: Neptune Serverless should auto-scale, but check if NCU max is reache\

\If query issue: identify slow queries via Neptune slow query log, optimize traversal\

\Immediate mitigation: increase Lambda timeout to accommodate slower responses

**Prevention:** Review query patterns quarterly. Ensure graph indexes cover the most common traversal patterns used by agents.

---

## Scenario 7: Unexpected Cost Spike

**Symptom:** AWS Cost Explorer shows Bedrock costs exceeding budget by 50%+.

**Impact:** Financial. No operational impact unless spend controls trigger account-level throttling.

**Response:*\

\Identify which agent is consuming the most tokens (check CloudWatch `DecisionCount` per agent × average prompt size\

\Common cause: feedback loop generating excess decisions, or a disruption event triggering many parallel analyse\

\If loop: address via circuit breaker (Scenario 1\

\If legitimate: verify the business value justifies the cost. If yes, update budget. If no, tighten agent invocation limits.

**Prevention:** Set AWS Budgets alarm at 80% of monthly target. Review `agent-config.yaml` `max_daily_adjustments` per agent.

---

## Scenario 8: Data Drift Detected

**Symptom:** Model monitoring (external to this system) reports input distribution shift for demand signals.

**Impact:** Agent recommendations may degrade in accuracy without warning. Confidence scores may not reflect actual decision quality.

**Response:*\

\Identify which signals drifted (seasonal shift, new data source format, upstream system change\

\If seasonal: expected — verify prompts account for seasonal contex\

\If format change: update data ingestion/normalization laye\

\If novel pattern: consider adding the new signal type to the prompt context, or temporarily increase confidence thresholds until the agent's accuracy on the new distribution is validated

**Prevention:** Run weekly distribution comparison (current week vs. training period) on all agent input signals. Alert on KL divergence > 0.5.

---

## Scenario 9: Single Agent Failure (Others Healthy)

**Symptom:** One agent Lambda returning errors while all others operate normally.

**Impact:** Downstream agents lose input from the failed agent. Coordination degrades.

**Response:*\

\Check the failed agent's CloudWatch logs for error detail\

\Common causes: code bug in latest deployment, dependency version conflict, secrets rotation not picked u\

\Rollback: `cdk deploy SupplyChainAgents` with previous version if recent deployment caused i\

\If not deployment-related: manually invoke the Lambda with a test event to reproduc\

\Downstream impact: other agents should gracefully handle missing upstream signals (check null handling in their prompts)

**Prevention:** Deploy one agent at a time in production (not all simultaneously). Run integration tests before each deployment.

---

## Scenario 10: Full System Recovery After Outage

**Symptom:** Multiple agents were down simultaneously (region event, deployment failure, etc.). System needs clean restart.

**Impact:** Backlog of unprocessed events in EventBridge archive. Decisions made during outage window were not captured.

**Response:*\

\Verify all Lambda functions are healthy: `aws lambda list-functions --query "Functions[?starts_with(FunctionName, 'sc-agent')]"\

\Verify EventBridge bus is receiving events: publish a test event and confirm deliver\

\Replay archived events for the outage window: use EventBridge Archive replay featur\

\Monitor decision volume during replay — may spike and trigger circuit breaker. Temporarily raise the threshold\

\Verify ERP integration is processing backlog from FIFO queue (ordered execution preserved\

\After backlog clears, return all thresholds to normal and confirm steady-state metrics

**Prevention:** Deploy across multiple AZs (already handled by Lambda). For Bedrock dependency, configure fallback model. For Neptune, enable multi-AZ deployment.
