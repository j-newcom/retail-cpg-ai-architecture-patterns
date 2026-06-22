"""
Inventory Allocation Agent — Lambda Handler

Receives demand adjustment signals and inventory level changes from EventBridge.
Determines optimal stock positioning across the distribution network.
Executes transfers within guardrails or escalates to planners.
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
AGENT_NAME = "inventory-allocation"

# Guardrails
CONFIDENCE_THRESHOLD = 0.75
MAX_AUTONOMOUS_TRANSFER_VALUE_USD = 50000
MAX_DAILY_TRANSFER_VALUE_USD = 500000
SERVICE_LEVEL_BREACH_ALWAYS_ESCALATES = True


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Receives inventory signals or demand adjustments,
    determines optimal allocation, and routes transfer orders.
    """
    decision_id = f"d-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    try:
        detail = event.get("detail", {})
        signal_type = event.get("detail-type", "Unknown")

        # Gather current inventory state and constraints
        inventory_context = _gather_inventory_context(detail)

        # Reason about optimal allocation
        allocation = _reason_about_allocation(signal_type, detail, inventory_context)

        # Apply guardrails and route
        result = _apply_guardrails_and_route(decision_id, allocation, detail)

        # Log and publish metrics
        _log_decision(decision_id, signal_type, detail, allocation, result)
        _publish_metrics(allocation, result)

        return {"statusCode": 200, "decision_id": decision_id, "result": result}

    except Exception as e:
        _publish_error_metric()
        raise


def _gather_inventory_context(signal_detail: dict) -> dict:
    """
    Query current inventory levels, inbound shipments, shelf-life constraints,
    and service level targets from Neptune and operational systems.
    """
    # In production: query WMS API for real-time levels, Neptune for relationships
    return {
        "dc_levels": {},
        "inbound_shipments": [],
        "shelf_life_constraints": {},
        "service_level_targets": {},
    }


def _reason_about_allocation(signal_type: str, signal_detail: dict, context: dict) -> dict:
    """
    Call Bedrock to determine optimal stock positioning given current signals.
    """
    prompt = f"""You are an inventory allocation agent for a CPG distribution network.
Given the incoming signal and current inventory state, recommend transfer orders
to optimize stock positioning.

## Incoming Signal
- Type: {signal_type}
- Detail: {json.dumps(signal_detail, indent=2, default=str)}

## Current Inventory Context
{json.dumps(context, indent=2, default=str)}

## Constraints
- Transfer orders between DCs take 2-3 days to fulfill
- Shelf-life products must have minimum 60% remaining life at destination
- Service level targets must not be breached by any transfer (no robbing Peter to pay Paul)
- Minimize total transportation cost across all recommended transfers

## Instructions
Respond with a JSON object:
{{
  "transfers": [
    {{
      "from_location": "<DC ID>",
      "to_location": "<DC ID>",
      "sku": "<SKU>",
      "quantity": <units>,
      "estimated_value_usd": <dollar value>,
      "urgency": "standard|expedited",
      "reasoning": "<why this transfer>"
    }}
  ],
  "total_transfer_value_usd": <sum of all transfer values>,
  "confidence": <0.0 to 1.0>,
  "service_level_impact": "none|positive|negative",
  "reasoning": "<overall allocation strategy explanation>"
}}

If no transfers are warranted, return an empty transfers array with reasoning explaining why."""

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1200,
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


def _apply_guardrails_and_route(decision_id: str, allocation: dict, signal_detail: dict) -> str:
    """Apply guardrails and route transfers to execution or escalation."""
    confidence = allocation.get("confidence", 0)
    total_value = allocation.get("total_transfer_value_usd", 0)
    transfers = allocation.get("transfers", [])
    service_impact = allocation.get("service_level_impact", "none")

    # No transfers recommended
    if not transfers:
        return "suppressed"

    # Service level breach always escalates
    if SERVICE_LEVEL_BREACH_ALWAYS_ESCALATES and service_impact == "negative":
        _escalate(decision_id, allocation, reason="service_level_breach_risk")
        return "escalated"

    # Confidence below threshold
    if confidence < CONFIDENCE_THRESHOLD:
        _escalate(decision_id, allocation, reason="confidence_below_threshold")
        return "escalated"

    # Total value exceeds autonomous limit
    if total_value > MAX_AUTONOMOUS_TRANSFER_VALUE_USD:
        _escalate(decision_id, allocation, reason="value_exceeds_autonomous_limit")
        return "escalated"

    # Check for cross-region transfers (always escalate)
    for transfer in transfers:
        if _is_cross_region(transfer.get("from_location", ""), transfer.get("to_location", "")):
            _escalate(decision_id, allocation, reason="cross_region_transfer")
            return "escalated"

    # Passed all guardrails — send to ERP queue for execution
    for transfer in transfers:
        _send_transfer_order(decision_id, transfer)

    return "executed"


def _is_cross_region(from_loc: str, to_loc: str) -> bool:
    """Determine if a transfer crosses regional boundaries."""
    # Simplified: extract region prefix from DC ID (e.g., DC-CHI vs DC-LAX)
    from_region = from_loc.split("-")[1] if "-" in from_loc else from_loc
    to_region = to_loc.split("-")[1] if "-" in to_loc else to_loc
    return from_region != to_region


def _send_transfer_order(decision_id: str, transfer: dict) -> None:
    """Send a transfer order to the ERP decision queue."""
    sqs.send_message(
        QueueUrl=ERP_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "action_type": "transfer_order",
            "transfer": transfer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
        MessageGroupId=f"{transfer.get('from_location', 'unknown')}-{transfer.get('sku', 'unknown')}",
    )


def _escalate(decision_id: str, allocation: dict, reason: str) -> None:
    """Send allocation decision to escalation queue."""
    sqs.send_message(
        QueueUrl=ESCALATION_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "reason": reason,
            "allocation": allocation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )


def _log_decision(decision_id: str, signal_type: str, detail: dict, allocation: dict, result: str) -> None:
    """Log full decision to S3."""
    log_entry = {
        "decision_id": decision_id,
        "agent": AGENT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal_type": signal_type,
        "signal_detail": detail,
        "allocation": allocation,
        "result": result,
    }
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=f"{AGENT_NAME}/{date_prefix}/{decision_id}.json",
        Body=json.dumps(log_entry, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(allocation: dict, result: str) -> None:
    """Publish CloudWatch metrics."""
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {"MetricName": "DecisionCount", "Value": 1, "Unit": "Count",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "ConfidenceScore", "Value": allocation.get("confidence", 0), "Unit": "None",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "AutonomousSpendUSD", "Value": allocation.get("total_transfer_value_usd", 0) if result == "executed" else 0,
             "Unit": "None", "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "EscalationCount", "Value": 1 if result == "escalated" else 0, "Unit": "Count",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
        ],
    )


def _publish_error_metric() -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[{"MetricName": "UnhandledError", "Value": 1, "Unit": "Count",
                     "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]}],
    )
