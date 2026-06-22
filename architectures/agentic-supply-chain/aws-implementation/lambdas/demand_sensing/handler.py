"""
Demand Sensing Agent — Lambda Handler

Receives market signal events from EventBridge, reasons about demand impact
using Bedrock, and publishes adjustment decisions or escalations.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

# Clients
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
events_client = boto3.client("events")
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

# Configuration from environment
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
MODEL_ID = os.environ.get("MODEL_ID", "anthropic.claude-sonnet-4-20250514")
ESCALATION_QUEUE_URL = os.environ["ESCALATION_QUEUE_URL"]
ERP_QUEUE_URL = os.environ["ERP_QUEUE_URL"]
DECISION_LOG_BUCKET = os.environ["DECISION_LOG_BUCKET"]
AGENT_NAME = "demand-sensing"

# Guardrails (loaded from config in production, hardcoded here for clarity)
CONFIDENCE_THRESHOLD = 0.70
MAX_AUTONOMOUS_ADJUSTMENT_PCT = 15
MAX_DAILY_ADJUSTMENTS = 500
REQUIRE_CORROBORATING_SIGNALS = 2


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Receives an EventBridge event containing a market signal,
    reasons about demand impact, and takes action.
    """
    decision_id = f"d-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    try:
        # Parse the incoming signal
        detail = event.get("detail", {})
        signal_type = event.get("detail-type", "Unknown")

        # Gather context from knowledge graph and vector store
        context_data = _gather_context(detail)

        # Reason about demand impact using Bedrock
        adjustment = _reason_about_demand(signal_type, detail, context_data)

        # Apply guardrails and route decision
        result = _apply_guardrails_and_route(decision_id, adjustment, detail)

        # Log the decision
        _log_decision(decision_id, signal_type, detail, adjustment, result)

        # Publish metrics
        _publish_metrics(adjustment, result)

        return {"statusCode": 200, "decision_id": decision_id, "result": result}

    except Exception as e:
        _publish_error_metric()
        raise


def _gather_context(signal_detail: dict) -> dict:
    """
    Query Neptune knowledge graph and OpenSearch vector store for relevant context.
    In production, this retrieves:
    - Historical demand patterns for the affected SKU/location
    - Similar past signals and their actual demand impact
    - Active promotions and known events in the affected region
    """
    # Placeholder — in production, query Neptune and OpenSearch
    return {
        "historical_baseline": None,
        "similar_events": [],
        "active_promotions": [],
    }


def _reason_about_demand(signal_type: str, signal_detail: dict, context: dict) -> dict:
    """
    Call Bedrock to reason about the demand impact of this signal.
    Returns structured adjustment recommendation.
    """
    prompt = f"""You are a demand sensing agent for a CPG supply chain. Analyze this market signal
and recommend whether a demand forecast adjustment is warranted.

## Incoming Signal
- Type: {signal_type}
- Detail: {json.dumps(signal_detail, indent=2, default=str)}

## Context
- Historical baseline: {context.get('historical_baseline', 'Not available')}
- Similar past events: {json.dumps(context.get('similar_events', []), default=str)}
- Active promotions: {json.dumps(context.get('active_promotions', []), default=str)}

## Instructions
Analyze the signal and respond with a JSON object:
{{
  "adjustment_pct": <number between -30 and +30, or 0 if no adjustment warranted>,
  "confidence": <number between 0.0 and 1.0>,
  "affected_skus": [<list of SKU identifiers if determinable, otherwise ["ALL_CATEGORY"]>],
  "affected_locations": [<list of location IDs if determinable, otherwise ["ALL"]>],
  "valid_days": <number of days this adjustment should apply>,
  "reasoning": "<2-3 sentences explaining your analysis>",
  "corroborating_signals_needed": <list of additional signals that would increase confidence>
}}

Be conservative. Only recommend non-zero adjustments when the signal is clear and material.
A +5% adjustment on a high-volume SKU is a significant business decision."""

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

    # Parse JSON from response (handle markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    return json.loads(response_text.strip())


def _apply_guardrails_and_route(decision_id: str, adjustment: dict, signal_detail: dict) -> str:
    """
    Apply guardrails and route the decision to execution or escalation.
    Returns: "executed", "escalated", or "suppressed"
    """
    confidence = adjustment.get("confidence", 0)
    adjustment_pct = adjustment.get("adjustment_pct", 0)

    # Guardrail 1: No adjustment recommended
    if adjustment_pct == 0:
        return "suppressed"

    # Guardrail 2: Confidence below threshold
    if confidence < CONFIDENCE_THRESHOLD:
        _escalate(decision_id, adjustment, reason="confidence_below_threshold")
        return "escalated"

    # Guardrail 3: Adjustment exceeds autonomous limit
    if abs(adjustment_pct) > MAX_AUTONOMOUS_ADJUSTMENT_PCT:
        _escalate(decision_id, adjustment, reason="adjustment_exceeds_guardrail")
        return "escalated"

    # Passed all guardrails — publish the adjustment event
    _publish_adjustment_event(decision_id, adjustment, signal_detail)
    return "executed"


def _publish_adjustment_event(decision_id: str, adjustment: dict, signal_detail: dict) -> None:
    """Publish a DemandAdjustment event to EventBridge for downstream agents."""
    events_client.put_events(
        Entries=[
            {
                "Source": f"supply-chain.agent.{AGENT_NAME}",
                "DetailType": "DemandAdjustment",
                "EventBusName": EVENT_BUS_NAME,
                "Detail": json.dumps({
                    "agent_id": f"{AGENT_NAME}-prod-01",
                    "decision_id": decision_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "confidence": adjustment["confidence"],
                    "payload": {
                        "adjustment_pct": adjustment["adjustment_pct"],
                        "affected_skus": adjustment.get("affected_skus", []),
                        "affected_locations": adjustment.get("affected_locations", []),
                        "valid_days": adjustment.get("valid_days", 7),
                    },
                    "reasoning_trace": adjustment.get("reasoning", ""),
                    "escalation_required": False,
                }),
            }
        ]
    )


def _escalate(decision_id: str, adjustment: dict, reason: str) -> None:
    """Send decision to escalation queue for human review."""
    sqs.send_message(
        QueueUrl=ESCALATION_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "reason": reason,
            "adjustment": adjustment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )


def _log_decision(
    decision_id: str, signal_type: str, signal_detail: dict, adjustment: dict, result: str
) -> None:
    """Log the full decision to S3 for audit trail."""
    log_entry = {
        "decision_id": decision_id,
        "agent": AGENT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_type": signal_type,
        "signal_detail": signal_detail,
        "adjustment": adjustment,
        "result": result,
        "guardrails_applied": {
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "max_adjustment_pct": MAX_AUTONOMOUS_ADJUSTMENT_PCT,
        },
    }

    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key = f"{AGENT_NAME}/{date_prefix}/{decision_id}.json"

    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=key,
        Body=json.dumps(log_entry, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(adjustment: dict, result: str) -> None:
    """Publish custom CloudWatch metrics."""
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {
                "MetricName": "DecisionCount",
                "Value": 1,
                "Unit": "Count",
                "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}],
            },
            {
                "MetricName": "ConfidenceScore",
                "Value": adjustment.get("confidence", 0),
                "Unit": "None",
                "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}],
            },
            {
                "MetricName": "EscalationCount",
                "Value": 1 if result == "escalated" else 0,
                "Unit": "Count",
                "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}],
            },
        ],
    )


def _publish_error_metric() -> None:
    """Publish error metric on unhandled exceptions."""
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {
                "MetricName": "UnhandledError",
                "Value": 1,
                "Unit": "Count",
                "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}],
            },
        ],
    )
