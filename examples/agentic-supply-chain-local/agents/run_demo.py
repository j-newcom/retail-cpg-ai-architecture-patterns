"""
Agentic Supply Chain Demo — Local Runner

Orchestrates the 5-agent supply chain system against a local Floci instance.
No LLM calls. No AWS credentials. Just the decision logic and event patterns.

Usage:
    docker compose up -d
    python agents/run_demo.py
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

import boto3

# Local Floci endpoint
ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"
EVENT_BUS = "supply-chain-bus"

# Fake credentials for Floci
session = boto3.Session(
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name=REGION,
)

dynamodb = session.resource("dynamodb", endpoint_url=ENDPOINT)
events_client = session.client("events", endpoint_url=ENDPOINT)
s3_client = session.client("s3", endpoint_url=ENDPOINT)


def log(agent: str, msg: str, event_type: str = None):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{ts}]"
    if event_type:
        print(f"{prefix} EVENT: {event_type}")
    print(f"{prefix} AGENT: {agent} → {msg}")
    print()


def seed_data():
    """Load seed data into DynamoDB."""
    print("=" * 60)
    print("  SEEDING DATA")
    print("=" * 60)

    inventory_table = dynamodb.Table("inventory")
    data_dir = Path(__file__).parent.parent / "seed-data"

    with open(data_dir / "inventory.json") as f:
        items = json.load(f)
    for item in items:
        inventory_table.put_item(Item=item)
    print(f"  Loaded {len(items)} inventory positions")

    print("  Seed complete.\n")


def publish_event(source: str, detail_type: str, detail: dict):
    """Publish an event to the local EventBridge bus."""
    events_client.put_events(
        Entries=[
            {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(detail),
                "EventBusName": EVENT_BUS,
            }
        ]
    )


def archive_decision(agent: str, decision: dict):
    """Archive a decision to S3 for audit trail."""
    decision_id = str(uuid.uuid4())[:8]
    key = f"decisions/{agent}/{decision_id}.json"
    s3_client.put_object(
        Bucket="supply-chain-decisions",
        Key=key,
        Body=json.dumps(decision, indent=2),
        ContentType="application/json",
    )


# Import agent modules
from demand_sensing import process_demand_signal
from inventory_allocation import process_demand_adjustment
from procurement import process_reorder_signal
from logistics import process_transfer_request
from disruption_response import process_disruption


def run_scenario_demand_spike():
    """Scenario: BBQ chips demand spike in Dallas due to summer promo."""
    print("\n" + "=" * 60)
    print("  SCENARIO: Summer Demand Spike — CHIPS-BBQ-12OZ @ DC-DALLAS")
    print("=" * 60 + "\n")

    # 1. Incoming demand signal
    signal = {
        "signal_id": str(uuid.uuid4())[:8],
        "sku": "CHIPS-BBQ-12OZ",
        "location": "DC-DALLAS",
        "signal_type": "pos_velocity_increase",
        "magnitude_pct": 18.3,
        "baseline_daily": 600,
        "observed_daily": 710,
        "active_promo": "summer-grilling-2026",
        "timestamp": datetime.now().isoformat(),
    }

    log("System", "Demand signal received", "demand.signal.received")
    print(f"           SKU: {signal['sku']}, Location: {signal['location']}")
    print(f"           POS velocity: +{signal['magnitude_pct']}% over baseline")
    print(f"           Active promo: {signal['active_promo']}\n")

    time.sleep(1)

    # 2. Demand Sensing Agent processes
    adjustment = process_demand_signal(signal)
    archive_decision("demand-sensing", adjustment)
    publish_event("supply-chain.demand-sensing", "demand.adjustment.published", adjustment)

    time.sleep(1)

    # 3. Inventory Allocation Agent responds
    allocation = process_demand_adjustment(adjustment)
    archive_decision("inventory-allocation", allocation)

    if allocation.get("action") == "transfer":
        publish_event("supply-chain.inventory-allocation", "inventory.transfer.requested", allocation)
        time.sleep(1)

        # 4. Logistics Agent routes the transfer
        routing = process_transfer_request(allocation)
        archive_decision("logistics", routing)

    if allocation.get("reorder_needed"):
        publish_event("supply-chain.inventory-allocation", "inventory.reorder.needed", allocation)
        time.sleep(1)

        # 5. Procurement Agent handles reorder
        po = process_reorder_signal(allocation)
        archive_decision("procurement", po)

    print("\n" + "=" * 60)
    print("  SCENARIO COMPLETE — All agents processed successfully")
    print("=" * 60)
    print(f"\n  Decisions archived to S3: supply-chain-decisions/decisions/")
    print(f"  Total processing time: ~{4}s (simulated agent delays)\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AGENTIC SUPPLY CHAIN — LOCAL DEMO")
    print("  Powered by Floci (local AWS emulator)")
    print("=" * 60 + "\n")

    seed_data()
    time.sleep(1)
    run_scenario_demand_spike()
