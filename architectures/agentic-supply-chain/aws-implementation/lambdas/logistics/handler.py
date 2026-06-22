"""
Logistics Agent — Lambda Handler

Optimizes transportation routing, carrier selection, and delivery scheduling.
Reacts to transfer orders from the Allocation Agent and disruption signals
affecting the transportation network.
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
ESCALATION_QUEUE_URL = os.environ["ESCALATION_QUEUE_URL"]
ERP_QUEUE_URL = os.environ["ERP_QUEUE_URL"]
DECISION_LOG_BUCKET = os.environ["DECISION_LOG_BUCKET"]
AGENT_NAME = "logistics"

# Guardrails
CONFIDENCE_THRESHOLD = 0.75
MAX_COST_OVERRUN_PCT = 20
MODE_CHANGE_ALWAYS_ESCALATES = True
MAX_DAILY_SHIPMENTS = 200


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Receives transfer orders or disruption signals,
    determines optimal routing and carrier selection.
    """
    decision_id = f"d-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    try:
        detail = event.get("detail", {})
        signal_type = event.get("detail-type", "Unknown")

        logistics_context = _gather_logistics_context(detail)
        routing = _reason_about_routing(signal_type, detail, logistics_context)
        result = _apply_guardrails_and_route(decision_id, routing, detail)

        _log_decision(decision_id, signal_type, detail, routing, result)
        _publish_metrics(routing, result)

        # Publish ETA update for downstream agents
        if result == "executed" and routing.get("estimated_delivery"):
            _publish_eta_update(decision_id, routing)

        return {"statusCode": 200, "decision_id": decision_id, "result": result}

    except Exception as e:
        _publish_error_metric()
        raise


def _gather_logistics_context(signal_detail: dict) -> dict:
    """
    Retrieve carrier rate cards, capacity, real-time conditions, and delivery windows.
    In production: queries TMS API, traffic/weather services, carrier portals.
    """
    return {
        "carrier_rates": {},
        "carrier_capacity": {},
        "traffic_conditions": {},
        "delivery_windows": {},
        "port_congestion": {},
    }


def _reason_about_routing(signal_type: str, signal_detail: dict, context: dict) -> dict:
    """
    Call Bedrock to determine optimal transportation routing.
    """
    prompt = f"""You are a logistics optimization agent for a CPG distribution network.
Given the incoming signal (transfer order or disruption), recommend optimal
carrier selection and routing.

## Incoming Signal
- Type: {signal_type}
- Detail: {json.dumps(signal_detail, indent=2, default=str)}

## Logistics Context
{json.dumps(context, indent=2, default=str)}

## Decision Factors (prioritized)
1. Meet delivery window requirements
2. Minimize cost within service commitment
3. Consolidate shipments where possible
4. Minimize carbon footprint (tiebreaker when cost is equivalent)

## Mode Options
- Ground (LTL/FTL): 2-5 days, lowest cost
- Intermodal (rail + truck): 4-7 days, moderate cost
- Air: 1-2 days, highest cost (expedited only)
- Ocean: 14-30 days, lowest cost (international only)

## Instructions
Respond with a JSON object:
{{
  "carrier_recommendation": "<carrier name>",
  "mode": "ground_ltl|ground_ftl|intermodal|air|ocean",
  "route": "<origin> → <destination>",
  "estimated_cost_usd": <dollar amount>,
  "budgeted_lane_rate_usd": <what the lane normally costs>,
  "cost_overrun_pct": <percentage over budget, 0 if within budget>,
  "estimated_delivery": "<ISO date>",
  "delivery_window_met": true|false,
  "consolidation_opportunity": "<description or null>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<2-3 sentences>",
  "mode_change_from_standard": true|false
}}"""

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 800,
            "temperature": 0.2,
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


def _apply_guardrails_and_route(decision_id: str, routing: dict, signal_detail: dict) -> str:
    """Apply logistics guardrails."""
    confidence = routing.get("confidence", 0)
    cost_overrun = routing.get("cost_overrun_pct", 0)
    mode_change = routing.get("mode_change_from_standard", False)

    # Mode change always escalates (e.g., switching from ocean to air)
    if MODE_CHANGE_ALWAYS_ESCALATES and mode_change:
        _escalate(decision_id, routing, reason="mode_change_requires_approval")
        return "escalated"

    # Confidence below threshold
    if confidence < CONFIDENCE_THRESHOLD:
        _escalate(decision_id, routing, reason="confidence_below_threshold")
        return "escalated"

    # Cost overrun exceeds limit
    if cost_overrun > MAX_COST_OVERRUN_PCT:
        _escalate(decision_id, routing, reason=f"cost_overrun_{cost_overrun}pct_exceeds_{MAX_COST_OVERRUN_PCT}pct")
        return "escalated"

    # Passed guardrails — send carrier assignment to TMS
    _send_carrier_assignment(decision_id, routing)
    return "executed"


def _send_carrier_assignment(decision_id: str, routing: dict) -> None:
    """Send carrier assignment to ERP/TMS queue."""
    sqs.send_message(
        QueueUrl=ERP_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "action_type": "carrier_assignment",
            "routing": routing,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
        MessageGroupId=f"logistics-{decision_id}",
    )


def _publish_eta_update(decision_id: str, routing: dict) -> None:
    """Publish ETA update event for downstream agents (especially Allocation)."""
    events_client.put_events(
        Entries=[{
            "Source": f"supply-chain.agent.{AGENT_NAME}",
            "DetailType": "ShipmentETAUpdate",
            "EventBusName": EVENT_BUS_NAME,
            "Detail": json.dumps({
                "agent_id": f"{AGENT_NAME}-prod-01",
                "decision_id": decision_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "estimated_delivery": routing.get("estimated_delivery"),
                    "carrier": routing.get("carrier_recommendation"),
                    "mode": routing.get("mode"),
                    "route": routing.get("route"),
                },
            }),
        }]
    )


def _escalate(decision_id: str, routing: dict, reason: str) -> None:
    sqs.send_message(
        QueueUrl=ESCALATION_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id, "agent": AGENT_NAME,
            "reason": reason, "routing": routing,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )


def _log_decision(decision_id: str, signal_type: str, detail: dict, routing: dict, result: str) -> None:
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=f"{AGENT_NAME}/{date_prefix}/{decision_id}.json",
        Body=json.dumps({"decision_id": decision_id, "agent": AGENT_NAME,
                         "timestamp": datetime.now(timezone.utc).isoformat(),
                         "signal_type": signal_type, "detail": detail,
                         "routing": routing, "result": result}, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(routing: dict, result: str) -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {"MetricName": "DecisionCount", "Value": 1, "Unit": "Count",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "ConfidenceScore", "Value": routing.get("confidence", 0),
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
