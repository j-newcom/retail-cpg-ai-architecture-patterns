"""
Procurement Agent — Lambda Handler

Manages supplier ordering, negotiation positioning, and supply disruption response.
External communications always route through human review before sending.
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
AGENT_NAME = "procurement"

# Guardrails
CONFIDENCE_THRESHOLD = 0.80
MAX_AUTONOMOUS_PO_VALUE_USD = 200000
NEW_SUPPLIER_ALWAYS_ESCALATES = True
OFF_CONTRACT_ALWAYS_ESCALATES = True
EXTERNAL_COMMS_REQUIRE_HUMAN_REVIEW = True
MAX_DAILY_PO_COUNT = 50


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Receives depletion forecasts or supplier alerts,
    recommends purchase orders or supplier communications.
    """
    decision_id = f"d-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    try:
        detail = event.get("detail", {})
        signal_type = event.get("detail-type", "Unknown")

        procurement_context = _gather_procurement_context(detail)
        recommendation = _reason_about_procurement(signal_type, detail, procurement_context)
        result = _apply_guardrails_and_route(decision_id, recommendation)

        _log_decision(decision_id, signal_type, detail, recommendation, result)
        _publish_metrics(recommendation, result)

        return {"statusCode": 200, "decision_id": decision_id, "result": result}

    except Exception as e:
        _publish_error_metric()
        raise


def _gather_procurement_context(signal_detail: dict) -> dict:
    """
    Retrieve supplier data, contract terms, quality history, and alternative sources.
    In production: queries SRM portal API, Neptune for supplier relationships,
    and OpenSearch for historical PO patterns.
    """
    return {
        "supplier_contracts": {},
        "approved_supplier_list": [],
        "quality_incidents": [],
        "alternative_suppliers": [],
        "current_open_pos": [],
    }


def _reason_about_procurement(signal_type: str, signal_detail: dict, context: dict) -> dict:
    """
    Call Bedrock to determine optimal procurement action.
    """
    prompt = f"""You are a procurement agent for a CPG company. Based on the incoming signal
and supplier context, recommend the appropriate procurement action.

## Incoming Signal
- Type: {signal_type}
- Detail: {json.dumps(signal_detail, indent=2, default=str)}

## Procurement Context
{json.dumps(context, indent=2, default=str)}

## Action Types Available
1. **purchase_order** — Place a PO with an existing contracted supplier
2. **expedite_request** — Ask supplier to accelerate an existing order (generates communication draft)
3. **alternative_source** — Recommend switching to a backup supplier
4. **quantity_change** — Modify an existing PO quantity up or down

## Constraints
- Only recommend suppliers from the approved supplier list
- All external communications (to suppliers) must be flagged for human review
- Off-contract pricing is never autonomous
- PO values above $200K require procurement manager approval

## Instructions
Respond with a JSON object:
{{
  "action_type": "purchase_order|expedite_request|alternative_source|quantity_change",
  "supplier_name": "<name>",
  "supplier_is_approved": true|false,
  "is_on_contract": true|false,
  "po_value_usd": <estimated value>,
  "sku": "<affected SKU>",
  "quantity": <units>,
  "urgency": "standard|expedited|critical",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<2-3 sentences>",
  "communication_draft": "<if action requires supplier communication, draft it here, otherwise null>",
  "risk_assessment": "<what could go wrong with this action>"
}}"""

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
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


def _apply_guardrails_and_route(decision_id: str, recommendation: dict) -> str:
    """Apply procurement-specific guardrails."""
    confidence = recommendation.get("confidence", 0)
    po_value = recommendation.get("po_value_usd", 0)
    is_approved = recommendation.get("supplier_is_approved", False)
    is_on_contract = recommendation.get("is_on_contract", False)
    has_communication = recommendation.get("communication_draft") is not None

    # New supplier always escalates
    if NEW_SUPPLIER_ALWAYS_ESCALATES and not is_approved:
        _escalate(decision_id, recommendation, reason="new_supplier_not_approved")
        return "escalated"

    # Off-contract pricing always escalates
    if OFF_CONTRACT_ALWAYS_ESCALATES and not is_on_contract:
        _escalate(decision_id, recommendation, reason="off_contract_pricing")
        return "escalated"

    # External communications always require human review
    if EXTERNAL_COMMS_REQUIRE_HUMAN_REVIEW and has_communication:
        _escalate(decision_id, recommendation, reason="external_communication_review")
        return "escalated"

    # Confidence below threshold
    if confidence < CONFIDENCE_THRESHOLD:
        _escalate(decision_id, recommendation, reason="confidence_below_threshold")
        return "escalated"

    # PO value exceeds autonomous limit
    if po_value > MAX_AUTONOMOUS_PO_VALUE_USD:
        _escalate(decision_id, recommendation, reason="po_value_exceeds_limit")
        return "escalated"

    # Passed all guardrails — send PO to ERP
    _send_purchase_order(decision_id, recommendation)
    return "executed"


def _send_purchase_order(decision_id: str, recommendation: dict) -> None:
    """Send PO to ERP decision queue."""
    sqs.send_message(
        QueueUrl=ERP_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "action_type": "purchase_order",
            "recommendation": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
        MessageGroupId=f"{recommendation.get('supplier_name', 'unknown')}-{recommendation.get('sku', 'unknown')}",
    )


def _escalate(decision_id: str, recommendation: dict, reason: str) -> None:
    sqs.send_message(
        QueueUrl=ESCALATION_QUEUE_URL,
        MessageBody=json.dumps({
            "decision_id": decision_id,
            "agent": AGENT_NAME,
            "reason": reason,
            "recommendation": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )


def _log_decision(decision_id: str, signal_type: str, detail: dict, recommendation: dict, result: str) -> None:
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=f"{AGENT_NAME}/{date_prefix}/{decision_id}.json",
        Body=json.dumps({"decision_id": decision_id, "agent": AGENT_NAME,
                         "timestamp": datetime.now(timezone.utc).isoformat(),
                         "signal_type": signal_type, "detail": detail,
                         "recommendation": recommendation, "result": result}, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(recommendation: dict, result: str) -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {"MetricName": "DecisionCount", "Value": 1, "Unit": "Count",
             "Dimensions": [{"Name": "Agent", "Value": AGENT_NAME}]},
            {"MetricName": "ConfidenceScore", "Value": recommendation.get("confidence", 0),
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
