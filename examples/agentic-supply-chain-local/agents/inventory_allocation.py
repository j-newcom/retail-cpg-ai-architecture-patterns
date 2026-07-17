"""
Inventory Allocation Agent

Responds to demand adjustments by rebalancing stock across the DC network.
"""

import json
from datetime import datetime
from pathlib import Path


def load_inventory():
    data_dir = Path(__file__).parent.parent / "seed-data"
    with open(data_dir / "inventory.json") as f:
        return {item["sku_location"]: item for item in json.load(f)}


def process_demand_adjustment(adjustment: dict) -> dict:
    """
    Respond to a demand forecast adjustment by evaluating inventory positions.

    Decision logic:
    - If target location is below min days cover → find a donor DC and transfer
    - If no donor available → flag for reorder
    """
    sku = adjustment["sku"]
    location = adjustment["location"]
    adj_pct = adjustment["adjustment_pct"]

    inventory = load_inventory()
    target_key = f"{sku}|{location}"
    target = inventory.get(target_key)

    if not target:
        return {"agent": "inventory-allocation", "action": "none", "reasoning": "SKU/location not found"}

    # Recalculate days cover with adjusted demand
    new_velocity = target["daily_velocity"] * (1 + adj_pct / 100)
    effective_days_cover = target["units_on_hand"] / new_velocity

    min_days_cover = 2.5
    target_days_cover = 4.0

    if effective_days_cover >= min_days_cover:
        decision = {
            "agent": "inventory-allocation",
            "action": "none",
            "sku": sku,
            "location": location,
            "days_cover": round(effective_days_cover, 1),
            "reasoning": f"Days cover {effective_days_cover:.1f} is above minimum ({min_days_cover}). No action needed.",
            "timestamp": datetime.now().isoformat(),
        }
        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Inventory Allocation → evaluating positions...")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: No rebalancing needed (days cover: {effective_days_cover:.1f})\n")
        return decision

    # Find best donor DC (highest days cover for same SKU)
    donors = []
    for key, item in inventory.items():
        if item["sku"] == sku and item["location"] != location and item["days_cover"] > target_days_cover:
            donors.append(item)

    donors.sort(key=lambda x: x["days_cover"], reverse=True)

    if donors:
        donor = donors[0]
        # Calculate transfer quantity to bring target to 4 days cover
        units_needed = int((target_days_cover * new_velocity) - target["units_on_hand"])
        # Don't take more than brings donor below target
        max_from_donor = int(donor["units_on_hand"] - (target_days_cover * donor["daily_velocity"]))
        transfer_qty = min(units_needed, max_from_donor)

        decision = {
            "agent": "inventory-allocation",
            "action": "transfer",
            "sku": sku,
            "from_location": donor["location"],
            "to_location": location,
            "quantity": transfer_qty,
            "days_cover_before": round(effective_days_cover, 1),
            "days_cover_after": round((target["units_on_hand"] + transfer_qty) / new_velocity, 1),
            "reasoning": (
                f"{location} at {effective_days_cover:.1f} days cover (target {target_days_cover}). "
                f"{donor['location']} has excess at {donor['days_cover']:.1f} days. "
                f"Transferring {transfer_qty:,} units."
            ),
            "reorder_needed": False,
            "timestamp": datetime.now().isoformat(),
            "autonomous": transfer_qty * 5 < 50000,  # Assume ~$5/unit for autonomous check
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Inventory Allocation → rebalancing...")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: Transfer {transfer_qty:,} units from {donor['location']} to {location}")
        print(f"           Reasoning: {decision['reasoning']}")
        print(f"           EVENT: inventory.transfer.requested → EventBridge\n")
    else:
        decision = {
            "agent": "inventory-allocation",
            "action": "reorder",
            "sku": sku,
            "location": location,
            "days_cover_current": round(effective_days_cover, 1),
            "units_needed": int((target_days_cover * new_velocity) - target["units_on_hand"]),
            "reasoning": f"No donor DC has excess stock for {sku}. Triggering procurement reorder.",
            "reorder_needed": True,
            "timestamp": datetime.now().isoformat(),
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Inventory Allocation → no donor available")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: Trigger procurement reorder ({decision['units_needed']:,} units needed)")
        print(f"           EVENT: inventory.reorder.needed → EventBridge\n")

    return decision
