"""
Logistics Agent

Routes shipments based on transfer requests from the Inventory Allocation Agent.
"""

from datetime import datetime, timedelta


CARRIER_RATES = {
    "FEDEX-FREIGHT": {"cost_per_mile": 2.80, "avg_speed_mph": 45, "reliability": 0.96},
    "UPS-LTL": {"cost_per_mile": 3.10, "avg_speed_mph": 40, "reliability": 0.94},
    "XPO-LOGISTICS": {"cost_per_mile": 2.50, "avg_speed_mph": 38, "reliability": 0.91},
}

LANE_DISTANCES = {
    ("DC-ATLANTA", "DC-DALLAS"): 780,
    ("DC-DALLAS", "DC-ATLANTA"): 780,
    ("DC-CHICAGO", "DC-DALLAS"): 920,
    ("DC-DALLAS", "DC-CHICAGO"): 920,
    ("DC-ATLANTA", "DC-CHICAGO"): 720,
    ("DC-CHICAGO", "DC-ATLANTA"): 720,
}


def process_transfer_request(transfer: dict) -> dict:
    """
    Select carrier and route for an inventory transfer.

    Decision logic:
    - Calculate cost and ETA for each carrier
    - Select lowest cost within SLA (3 days max)
    - If no carrier meets SLA, escalate
    """
    origin = transfer["from_location"]
    destination = transfer["to_location"]
    quantity = transfer["quantity"]

    lane_key = (origin, destination)
    distance = LANE_DISTANCES.get(lane_key, 800)  # default 800mi if unknown

    options = []
    for carrier, specs in CARRIER_RATES.items():
        transit_hours = distance / specs["avg_speed_mph"]
        transit_days = round(transit_hours / 24, 1)
        cost = round(distance * specs["cost_per_mile"], 2)
        options.append({
            "carrier": carrier,
            "transit_days": transit_days,
            "cost_usd": cost,
            "reliability": specs["reliability"],
        })

    # Sort by cost (lowest first), filter to within SLA
    sla_max_days = 3.0
    viable = [o for o in options if o["transit_days"] <= sla_max_days]
    viable.sort(key=lambda x: x["cost_usd"])

    if viable:
        selected = viable[0]
        eta = datetime.now() + timedelta(days=selected["transit_days"])

        decision = {
            "agent": "logistics",
            "action": "route_shipment",
            "carrier": selected["carrier"],
            "origin": origin,
            "destination": destination,
            "distance_miles": distance,
            "transit_days": selected["transit_days"],
            "cost_usd": selected["cost_usd"],
            "eta": eta.strftime("%Y-%m-%d %H:%M"),
            "quantity": quantity,
            "reasoning": (
                f"Selected {selected['carrier']} for {origin}→{destination} ({distance}mi). "
                f"Cost ${selected['cost_usd']:,.0f}, ETA {selected['transit_days']} days. "
                f"Lowest cost option within {sla_max_days}-day SLA. "
                f"Reliability: {selected['reliability']*100:.0f}%."
            ),
            "alternatives_considered": len(options),
            "timestamp": datetime.now().isoformat(),
            "autonomous": selected["cost_usd"] < 5000,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Logistics → routing shipment...")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: Carrier {selected['carrier']}, route {origin}→{destination}, ETA {selected['transit_days']} days")
        print(f"           Reasoning: {decision['reasoning']}\n")
    else:
        decision = {
            "agent": "logistics",
            "action": "escalate",
            "origin": origin,
            "destination": destination,
            "reasoning": f"No carrier can deliver within {sla_max_days}-day SLA. Escalating to logistics manager.",
            "timestamp": datetime.now().isoformat(),
            "autonomous": False,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Logistics → ESCALATING")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No carrier meets SLA. Routing to logistics manager.\n")

    return decision
