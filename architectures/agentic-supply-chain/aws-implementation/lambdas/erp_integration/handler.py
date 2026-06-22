"""
ERP Integration Lambda — Translation Layer

Consumes decisions from the ERP FIFO queue, translates agent decision format
into ERP-native transactions (SAP BAPI, Oracle REST, IDoc), and handles
confirmation/rejection loops.

This Lambda sits between the agent network and the enterprise ERP. It:
1. Receives a decision from SQS FIFO
2. Retrieves ERP credentials from Secrets Manager
3. Translates the agent decision schema to ERP-native format
4. Calls the ERP API
5. Publishes confirmation or rejection event back to EventBridge
6. On failure, routes to DLQ after configured retries
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3

events_client = boto3.client("events")
secrets_client = boto3.client("secretsmanager")
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")

EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
DLQ_URL = os.environ["DLQ_URL"]
ERP_SECRET_NAME = os.environ.get("ERP_SECRET_NAME", "erp/api-credentials")
DECISION_LOG_BUCKET = os.environ.get("DECISION_LOG_BUCKET", "supply-chain-decisions")

# ERP connection config (populated from Secrets Manager at cold start)
_erp_credentials = None


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point. Triggered by SQS FIFO queue (batch_size=1).
    Each record contains one agent decision to execute against ERP.
    """
    results = []

    for record in event.get("Records", []):
        body = json.loads(record["body"])
        decision_id = body.get("decision_id", "unknown")
        agent = body.get("agent", "unknown")
        action_type = body.get("action_type", "unknown")

        try:
            # Translate and execute
            erp_response = _translate_and_execute(body)

            # Publish confirmation event
            _publish_confirmation(decision_id, agent, action_type, erp_response)

            # Log
            _log_execution(decision_id, body, erp_response, status="success")

            results.append({"decision_id": decision_id, "status": "success"})

        except ERPValidationError as e:
            # ERP rejected the transaction — publish rejection event
            _publish_rejection(decision_id, agent, action_type, str(e))
            _log_execution(decision_id, body, {"error": str(e)}, status="rejected")
            results.append({"decision_id": decision_id, "status": "rejected", "reason": str(e)})

        except ERPConnectionError as e:
            # ERP unreachable — let SQS retry (will eventually hit DLQ)
            _publish_metrics_error("connection_error")
            raise  # Re-raise to trigger SQS retry

        except Exception as e:
            # Unexpected error — route to DLQ
            _send_to_dlq(body, str(e))
            _log_execution(decision_id, body, {"error": str(e)}, status="failed")
            results.append({"decision_id": decision_id, "status": "failed", "error": str(e)})

    _publish_metrics(results)
    return {"statusCode": 200, "results": results}


def _translate_and_execute(decision: dict) -> dict:
    """
    Translate agent decision schema into ERP-native format and execute.
    This is the only component that changes when the ERP platform changes.
    """
    credentials = _get_erp_credentials()
    action_type = decision.get("action_type", "")

    if action_type == "transfer_order":
        return _execute_transfer_order(decision, credentials)
    elif action_type == "purchase_order":
        return _execute_purchase_order(decision, credentials)
    elif action_type == "carrier_assignment":
        return _execute_carrier_assignment(decision, credentials)
    else:
        raise ERPValidationError(f"Unknown action_type: {action_type}")


def _execute_transfer_order(decision: dict, credentials: dict) -> dict:
    """
    Translate transfer order to ERP format.
    SAP: BAPI_WHSE_TO_CREATE_STOCK_TRANSFER
    Oracle: REST API /fscmRestApi/resources/latest/inventoryTransferOrders
    """
    transfer = decision.get("transfer", decision.get("recommendation", {}))

    # Build ERP-native payload (SAP example)
    erp_payload = {
        "transaction_type": "STOCK_TRANSFER",
        "source_plant": _map_location_to_plant(transfer.get("from_location", "")),
        "dest_plant": _map_location_to_plant(transfer.get("to_location", "")),
        "material_number": _map_sku_to_material(transfer.get("sku", "")),
        "quantity": transfer.get("quantity", 0),
        "unit_of_measure": "EA",
        "requested_delivery_date": transfer.get("requested_date", ""),
        "reference_document": decision.get("decision_id", ""),
    }

    # In production: call ERP API here
    # response = requests.post(
    #     f"{credentials['erp_base_url']}/api/transfer-orders",
    #     headers={"Authorization": f"Bearer {credentials['api_token']}"},
    #     json=erp_payload,
    #     timeout=30,
    # )

    # Simulated ERP response
    return {
        "erp_document_id": f"TO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-SIM001",
        "status": "created",
        "erp_payload_sent": erp_payload,
    }


def _execute_purchase_order(decision: dict, credentials: dict) -> dict:
    """Translate purchase order to ERP format."""
    recommendation = decision.get("recommendation", {})

    erp_payload = {
        "transaction_type": "PURCHASE_ORDER",
        "vendor_number": _map_supplier_to_vendor(recommendation.get("supplier_name", "")),
        "material_number": _map_sku_to_material(recommendation.get("sku", "")),
        "quantity": recommendation.get("quantity", 0),
        "net_price": recommendation.get("po_value_usd", 0),
        "delivery_date": "",
        "reference_document": decision.get("decision_id", ""),
    }

    return {
        "erp_document_id": f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-SIM001",
        "status": "created",
        "erp_payload_sent": erp_payload,
    }


def _execute_carrier_assignment(decision: dict, credentials: dict) -> dict:
    """Translate carrier assignment to TMS format."""
    routing = decision.get("routing", {})

    tms_payload = {
        "transaction_type": "SHIPMENT",
        "carrier_scac": _map_carrier_name_to_scac(routing.get("carrier_recommendation", "")),
        "mode": routing.get("mode", ""),
        "origin": routing.get("route", "").split("→")[0].strip() if "→" in routing.get("route", "") else "",
        "destination": routing.get("route", "").split("→")[1].strip() if "→" in routing.get("route", "") else "",
        "requested_pickup_date": "",
        "reference_document": decision.get("decision_id", ""),
    }

    return {
        "erp_document_id": f"SH-{datetime.now(timezone.utc).strftime('%Y%m%d')}-SIM001",
        "status": "created",
        "erp_payload_sent": tms_payload,
    }


# --- Mapping Functions ---
# These translate between the agent's domain language and ERP-specific codes.
# In production, these mappings live in a DynamoDB table or config service.

def _map_location_to_plant(location_id: str) -> str:
    """Map agent location ID (e.g., DC-CHI-01) to ERP plant code."""
    mapping = {"DC-CHI-01": "1000", "DC-LAX-01": "2000", "DC-ATL-01": "3000"}
    return mapping.get(location_id, location_id)


def _map_sku_to_material(sku: str) -> str:
    """Map product SKU to ERP material number."""
    # In production: lookup in master data service
    return sku.replace("-", "")


def _map_supplier_to_vendor(supplier_name: str) -> str:
    """Map supplier name to ERP vendor number."""
    # In production: lookup in vendor master
    return f"V-{hash(supplier_name) % 100000:05d}"


def _map_carrier_name_to_scac(carrier_name: str) -> str:
    """Map carrier name to SCAC code."""
    mapping = {"FedEx": "FEDX", "UPS": "UPSS", "XPO": "XPOL", "Schneider": "SNDR"}
    return mapping.get(carrier_name, "UNKN")


# --- Infrastructure Functions ---

def _get_erp_credentials() -> dict:
    """Retrieve ERP credentials from Secrets Manager (cached for Lambda lifecycle)."""
    global _erp_credentials
    if _erp_credentials is None:
        secret = secrets_client.get_secret_value(SecretId=ERP_SECRET_NAME)
        _erp_credentials = json.loads(secret["SecretString"])
    return _erp_credentials


def _publish_confirmation(decision_id: str, agent: str, action_type: str, erp_response: dict) -> None:
    """Publish confirmation event back to EventBridge."""
    events_client.put_events(
        Entries=[{
            "Source": "supply-chain.integration.erp",
            "DetailType": "ERPConfirmation",
            "EventBusName": EVENT_BUS_NAME,
            "Detail": json.dumps({
                "decision_id": decision_id,
                "originating_agent": agent,
                "action_type": action_type,
                "erp_document_id": erp_response.get("erp_document_id"),
                "status": "confirmed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }]
    )


def _publish_rejection(decision_id: str, agent: str, action_type: str, reason: str) -> None:
    """Publish rejection event — originating agent will need to replan."""
    events_client.put_events(
        Entries=[{
            "Source": "supply-chain.integration.erp",
            "DetailType": "ERPRejection",
            "EventBusName": EVENT_BUS_NAME,
            "Detail": json.dumps({
                "decision_id": decision_id,
                "originating_agent": agent,
                "action_type": action_type,
                "reason": reason,
                "status": "rejected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }]
    )


def _send_to_dlq(decision: dict, error: str) -> None:
    """Route unrecoverable failures to dead letter queue."""
    sqs.send_message(
        QueueUrl=DLQ_URL,
        MessageBody=json.dumps({
            "original_decision": decision,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }),
        MessageGroupId="erp-failures",
    )


def _log_execution(decision_id: str, decision: dict, response: dict, status: str) -> None:
    """Log ERP execution to S3."""
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    s3.put_object(
        Bucket=DECISION_LOG_BUCKET,
        Key=f"erp-integration/{date_prefix}/{decision_id}.json",
        Body=json.dumps({
            "decision_id": decision_id, "status": status,
            "decision": decision, "erp_response": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2, default=str),
        ContentType="application/json",
    )


def _publish_metrics(results: list) -> None:
    success_count = sum(1 for r in results if r["status"] == "success")
    rejected_count = sum(1 for r in results if r["status"] == "rejected")
    failed_count = sum(1 for r in results if r["status"] == "failed")

    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[
            {"MetricName": "ERPExecutionSuccess", "Value": success_count, "Unit": "Count"},
            {"MetricName": "ERPExecutionRejected", "Value": rejected_count, "Unit": "Count"},
            {"MetricName": "ERPExecutionFailed", "Value": failed_count, "Unit": "Count"},
        ],
    )


def _publish_metrics_error(error_type: str) -> None:
    cloudwatch.put_metric_data(
        Namespace="SupplyChainAgents",
        MetricData=[{"MetricName": "ERPConnectionError", "Value": 1, "Unit": "Count"}],
    )


# Custom exceptions
class ERPValidationError(Exception):
    """ERP rejected the transaction due to validation failure."""
    pass


class ERPConnectionError(Exception):
    """ERP is unreachable."""
    pass
