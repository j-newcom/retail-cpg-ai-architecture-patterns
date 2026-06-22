"""
Disruption Response Agent — Lambda Handler

Coordinates cross-domain response when a material disruption occurs.
Retrieves similar historical disruptions from vector store, generates
a response plan, and either executes within authority or escalates
to VP-level leadership with full context.

This agent has the highest reasoning complexity and longest timeout.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
events_client = boto3.client("events")
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
MODEL_ID = os.environ.get("MODEL_ID", "anthropic.claude-sonnet-4-20250514")
NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT", "")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
ESCALATION_QUEUE_URL = os.environ["ESCALATION_QUEUE_URL"]
DECISION_LOG_BUCKET = os.environ["DECISION_LOG_BUCKET"]
AGENT_NAME = "disruption-response"

# Guardrails
CONFIDENCE_THRESHOLD = 0.65
MAX_AUTONOMOUS_IMPACT_VALUE_USD = 500000
CUSTOMER_COMMITMENT_ALWAYS_ESCALATES = True
VP_ESCALATION_THRESHOLD_USD = 500000
MAX_CONCURRENT_RESPONSES = 3
SIMILAR_DISRUPTION_RETRIEVAL_COUNT = 5


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Receives disruption events, coordinates a cross-agent response.
    """
    decision_id = f"d-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    try:
        detail = event.get("detail", {})
        signal_type = event.get("detail-type", "Unknown")

        # Retrieve similar historical disruptions
        similar_disruptions = _retrieve_similar_disruptions(detail)

        # Gather current state across all agents
        system_state = _gather_system_state()

        # Generate coordinated response plan
        response_plan = _generate_response_plan(
            signal_type, detail, similar_disruptions, system_state
        )

        # Apply guardrails
        result = _apply_guardrails_and_route(decision_id, response_plan)

        # Log the decision
        _log_decision(decision_id, signal_type, detail, response_plan, similar_disruptions, result)

        # Publish metrics
        _publish_metrics(response_plan, result)

        return {"statusCode": 200, "decision_id": decision_id, "result": result}

    except Exception as e:
        _publish_error_metric()
        raise


def _retrieve_similar_disruptions(current_disruption: dict) -> list[dict]:
    """
    Query OpenSearch vector store for historical disruptions similar to the current one.
    Returns top-N matches with their response playbooks and outcomes.

    In production: embeds the disruption description, performs kNN search against
    the decision-history vector collection, and returns structured playbook data.
    """
    # Placeholder — in production, query OpenSearch Serverless
    return [
        {
            "disruption_id": "hist-001",
            "date": "2025-09-15",
            "type": "supplier_failure",
            "similarity_score": 0.0,
            "description": "No similar disruptions found in vector store",
            "response_taken": None,
            "outcome": None,
        }
    ]


def _gather_system_state() -> dict:
    """
    Query current state from all other agents via Neptune knowledge graph.
    Provides the disruption response agent with full system awareness.
    """
    # In production: query Neptune for active decisions, pending transfers,
    # open POs, and current inventory positions
    return {
        "active_demand_adjustments": [],
        "pending_transfers": [],
        "open_purchase_orders": [],
        "critical_inventory_levels": [],
        "active_shipments": [],
    }


def _generate_response_plan(
    signal_type: str,
    disruption_detail: dict,
    similar_disruptions: list[dict],
    system_state: dict,
) -> dict:
    """
    Call Bedrock to generate a coordinated multi-agent response plan.
    This is the most complex reasoning task in the system.
    """
    prompt = f"""You are a disruption response coordinator for an enterprise CPG supply chain.
A material disruption has occurred. Your job is to generate a coordinated response plan
that spans multiple supply chain domains (demand, inventory, procurement, logistics).

## Current Disruption
- Type: {signal_type}
- Detail: {json.dumps(disruption_detail, indent=2, default=str)}

## Similar Historical Disruptions
{json.dumps(similar_disruptions, indent=2, default=str)}

## Current System State
{json.dumps(system_state, indent=2, default=str)}

## Your Authority
- You can coordinate responses valued below $500K total impact
- Anything affecting customer commitments must be escalated to VP
- You do not execute actions directly — you emit coordinated instructions to other agents

## Instructions
Generate a response plan. Respond with JSON:
{{
  "disruption_severity": "low|medium|high|critical",
  "estimated_revenue_at_risk_usd": <dollar amount>,
  "estimated_duration_days": <how long the disruption will affect operations>,
  "response_actions": [
    {{
      "target_agent": "demand-sensing|inventory-allocation|procurement|logistics",
      "action": "<what the agent should do>",
      "priority": 1-5,
      "deadline_hours": <hours from now>,
      "estimated_value_usd": <cost/value of this action>
    }}
  ],
  "customer_commitments_affected": true|false,
  "affected_customers": ["<customer names if known>"],
  "total_response_value_usd": <sum of all action values>,
  "confidence": <0.0 to 1.0>,
  "executive_summary": "<3-4 sentence summary suitable for VP-level communication>",
  "reasoning": "<detailed analysis of disruption impact and response rationale>",
  "monitoring_cadence_hours": <how often to re-evaluate, typically 4-24>
}}

Be thorough. This is a high-stakes coordination decision. Missing an action is worse than
recommending one that gets filtered by guardrails downstream."""

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    response_text = result["content"][0]["text"]

    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    return json.loads(response_text.strip())


def _apply_guardrails_and_route(decision_id: str, response_plan: dict) -> str:
    """Apply disruption response guardrails."""
    confidence = response_plan.get("confidence", 0)
    total_value = response_plan.get("total_response_value_usd", 0)
    customer_affected = response_plan.get("customer_commitments_affected", False)
    severity = response_plan.get("disruption_severity", "unknown")

    # Customer commitments affected — always escalate to VP
    if CUSTOMER_COMMITMENT_ALWAYS_ESCALATES and customer_affected:
        _escalate_to_vp(decision_id, response_plan, reason="customer_commitments_affected")
        return "escalated"

    # Total value exceeds VP threshold
    if total_value > VP_ESCALATION_THRESHOLD_USD:
        _escalate_to_vp(decision_id, response_plan, reason="value_exceeds_vp_threshold")
        return "escalated"

    # Confidence below threshold
    if confidence < CONFIDENCE_THRESHOLD:
        _escalate_to_vp(decision_id, response_plan, reason="confidence_below_threshold")
        return "escalated"

    # Critical severity always gets human eyes
    if severity == "critical":
        _escalate_to_vp(decision_id, response_plan, reason="critical_severity")
        return "escalated"

    # Passed guardrails — emit coordinated response events
    _emit_response_actions(decision_id, response_plan)
    return "executed"


def _emit_response_actions(decision_id: str, response_plan: dict) -> None:
    """Publish coordinated action events to EventBridge for target agents."""
    entries = []
    for action in response_plan.get("response_actions", []):
        entries.append({
            "Source": f"supply-chain.agent.{AGENT_NAME}",
            "DetailType": "CoordinatedResponseAction",
            "EventBusName": EVENT_BUS_NAME,
            "Detail": json.dumps({
                "decision_id": decision_id,
                "target_agent": action["target_agent"],
                "action": action["action"],
                "priority": action["priority"],
                "deadline_hours": action["deadline_hours"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        })

    # EventBridge supports max 10 entries per call
    for i in range(0, len(entries), 10):
        events_client.put_events(Entries=entries[i:i+10])


def _escalate_to_vp(decision_id: str, response_plan: dict, reason: str) -> None:
    """
    Escalate to VP-level leadership with full context package.
    Includes executive summary, impact assessment, and recommended actions.
    """
    escalation_package = {
        "decision_id": decision_id,
        "agent": AGENT_NAME,
        "escalation_level": "VP",
        "reason": reason,
        "executive_summary": response_plan.get("executive_summary", ""),
        "severity": response_plan.get("disruption_severity", "unknown"),
        "revenue_at_risk_usd": response_plan.get("estimated_revenue_at_risk_usd", 0),
        "recommended_actions": response_plan.get("response_actions", []),
        "confidence": response_plan.get("confidence", 0),
        "full_response_plan": response_plan,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sla_response_hours": 4,
    }

    sqs.send_message(
        QueueUrl=ESCALATION_QUEUE_URL,
        MessageBody=json.dumps(escalation_package, default=str),
    )

    # Also publish an ImpactAssessment event for dashboards
    events_client.put_events(
        Entries=[{
            "Source": f"supply-chain.agent.{AGENT_NAME}",
            "DetailType": "ImpactAssessment",
            "EventBusName": EVENT_BUS_NAME,
            "Detail": json.dumps({
                "decision_id": decision_id,
                "severity": response_plan.get("disruption_severity"),
                "revenue_at_risk_usd": response_plan.get("estimated_revenue_at_risk_usd", 0),
                "customer_impact": response_plan.get("customer_commitments_affected", False),
                "escalation_reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }]
    )


def _log_decision(
    decision_id: str, signal_type: str, detail: dict,
    response_plan: dict, similar_disruptions: list, result: str
) -> None:
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=f"{AGENT_NAME}/{date_prefix}/{decision_id}.json",
        Body=json.dumps({
            "decision_id": decision_id, "agent": AGENT_NAME,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_type": signal_type, "detail": detail,
            "similar_disruptions_retrieved": len(similar_disruptions),
            "response_plan": response_plan, "result": result,
        }, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(response_plan: dict, result: str) -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {"MetricName": "DecisionCount", "Value": 1, "Unit": "Count",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "ConfidenceScore", "Value": response_plan.get("confidence", 0),
             "Unit": "None", "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "DisruptionSeverity",
             "Value": {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(
                 response_plan.get("disruption_severity", ""), 0),
             "Unit": "None", "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "RevenueAtRiskUSD",
             "Value": response_plan.get("estimated_revenue_at_risk_usd", 0),
             "Unit": "None", "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "EscalationCount", "Value": 1 if result == "escalated" else 0,
             "Unit": "Count", "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
        ],
    )


def _publish_error_metric() -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[{"MetricName": "UnhandledError", "Value": 1, "Unit": "Count",
                     "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]}],
    )
