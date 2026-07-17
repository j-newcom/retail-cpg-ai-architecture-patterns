"""
Procurement Agent

Manages supplier ordering when inventory reorder points are triggered.
"""

import json
from datetime import datetime
from pathlib import Path


def load_suppliers():
    data_dir = Path(__file__).parent.parent / "seed-data"
    with open(data_dir / "suppliers.json") as f:
        return json.load(f)


def process_reorder_signal(allocation: dict) -> dict:
    """
    Generate a purchase order recommendation based on reorder signal.

    Decision logic:
    - Find contracted supplier for the SKU
    - Check capacity and reliability
    - Generate PO within autonomous boundary ($200K)
    """
    sku = allocation["sku"]
    units_needed = allocation.get("units_needed", 1000)
    location = allocation.get("location", "UNKNOWN")

    suppliers = load_suppliers()
    eligible = [s for s in suppliers if sku in s["contracted_skus"]]

    if not eligible:
        decision = {
            "agent": "procurement",
            "action": "escalate",
            "sku": sku,
            "reasoning": f"No contracted supplier found for {sku}. Escalating to procurement manager.",
            "timestamp": datetime.now().isoformat(),
            "autonomous": False,
        }
        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Procurement → ESCALATING")
        print(f"           No contracted supplier for {sku}\n")
        return decision

    # Select best supplier (highest reliability with available capacity)
    eligible.sort(key=lambda s: (s["reliability_score"], -s["current_utilization_pct"]), reverse=True)
    supplier = eligible[0]

    # Calculate order quantity (round up to min order qty)
    order_qty = max(units_needed, supplier["min_order_qty"])
    estimated_cost = order_qty * 4.50  # Assume ~$4.50/unit average

    decision = {
        "agent": "procurement",
        "action": "create_po",
        "supplier_id": supplier["supplier_id"],
        "supplier_name": supplier["name"],
        "sku": sku,
        "quantity": order_qty,
        "estimated_cost_usd": round(estimated_cost, 2),
        "lead_time_days": supplier["lead_time_days"],
        "delivery_location": location,
        "reasoning": (
            f"Reorder triggered for {sku} at {location}. "
            f"Selected {supplier['name']} (reliability: {supplier['reliability_score']}, "
            f"utilization: {supplier['current_utilization_pct']}%). "
            f"PO: {order_qty:,} units, est. ${estimated_cost:,.0f}, "
            f"delivery in {supplier['lead_time_days']} days."
        ),
        "timestamp": datetime.now().isoformat(),
        "autonomous": estimated_cost < 200000,
    }

    status = "auto-approved (within $200K boundary)" if decision["autonomous"] else "PENDING APPROVAL"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Procurement → generating PO...")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: PO to {supplier['name']} — {order_qty:,} units, ${estimated_cost:,.0f}")
    print(f"           Lead time: {supplier['lead_time_days']} days | Status: {status}")
    print(f"           Reasoning: {decision['reasoning']}\n")

    return decision
