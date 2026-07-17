"""
Disruption Response Agent

Coordinates cross-functional response when supply chain disruptions occur.
Searches historical playbooks for similar events and recommends response sequences.
"""

from datetime import datetime


HISTORICAL_PLAYBOOKS = [
    {
        "playbook_id": "PB-WEATHER-001",
        "trigger": "weather_event",
        "description": "Hurricane/severe weather — activate backup carriers and pre-position inventory",
        "similarity_keywords": ["hurricane", "storm", "flood", "weather"],
        "actions": ["activate_backup_carriers", "pre_position_safety_stock", "notify_customers_of_delay"],
    },
    {
        "playbook_id": "PB-SUPPLIER-001",
        "trigger": "supplier_failure",
        "description": "Primary supplier capacity loss — switch to secondary supplier",
        "similarity_keywords": ["supplier", "capacity", "shutdown", "quality"],
        "actions": ["activate_secondary_supplier", "reduce_promotional_commitments", "extend_lead_time_estimates"],
    },
    {
        "playbook_id": "PB-PORT-001",
        "trigger": "port_congestion",
        "description": "Port delay — reroute inbound shipments to alternate port",
        "similarity_keywords": ["port", "congestion", "customs", "delay", "container"],
        "actions": ["reroute_to_alternate_port", "expedite_inland_transport", "adjust_inbound_etas"],
    },
]


def process_disruption(disruption: dict) -> dict:
    """
    Respond to a disruption event by matching historical playbooks.

    Decision logic:
    - Search playbooks for keyword similarity
    - If match above threshold → execute automatically
    - If no match or impact > $1M → escalate to leadership
    """
    disruption_type = disruption.get("type", "unknown")
    description = disruption.get("description", "")
    estimated_impact_usd = disruption.get("estimated_impact_usd", 0)
    affected_locations = disruption.get("affected_locations", [])

    # Search for matching playbook
    best_match = None
    best_score = 0

    search_text = f"{disruption_type} {description}".lower()
    for playbook in HISTORICAL_PLAYBOOKS:
        matches = sum(1 for kw in playbook["similarity_keywords"] if kw in search_text)
        score = matches / len(playbook["similarity_keywords"])
        if score > best_score:
            best_score = score
            best_match = playbook

    auto_threshold = 0.7
    max_auto_impact = 1_000_000

    if best_match and best_score >= auto_threshold and estimated_impact_usd < max_auto_impact:
        decision = {
            "agent": "disruption-response",
            "action": "execute_playbook",
            "playbook_id": best_match["playbook_id"],
            "playbook_description": best_match["description"],
            "similarity_score": round(best_score, 2),
            "actions_triggered": best_match["actions"],
            "estimated_impact_usd": estimated_impact_usd,
            "affected_locations": affected_locations,
            "reasoning": (
                f"Disruption '{disruption_type}' matched playbook {best_match['playbook_id']} "
                f"with {best_score*100:.0f}% similarity. Impact ${estimated_impact_usd:,.0f} is within "
                f"auto-response threshold. Executing: {', '.join(best_match['actions'])}."
            ),
            "timestamp": datetime.now().isoformat(),
            "autonomous": True,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Disruption Response → playbook matched!")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: Execute {best_match['playbook_id']} (similarity: {best_score*100:.0f}%)")
        print(f"           Actions: {', '.join(best_match['actions'])}")
        print(f"           Reasoning: {decision['reasoning']}\n")
    else:
        escalation_reason = []
        if not best_match or best_score < auto_threshold:
            escalation_reason.append(f"no playbook match above {auto_threshold*100:.0f}% threshold")
        if estimated_impact_usd >= max_auto_impact:
            escalation_reason.append(f"impact ${estimated_impact_usd:,.0f} exceeds $1M auto-response limit")

        decision = {
            "agent": "disruption-response",
            "action": "escalate",
            "disruption_type": disruption_type,
            "estimated_impact_usd": estimated_impact_usd,
            "best_playbook_match": best_match["playbook_id"] if best_match else None,
            "best_similarity_score": round(best_score, 2),
            "escalation_reason": "; ".join(escalation_reason),
            "affected_locations": affected_locations,
            "reasoning": (
                f"Disruption '{disruption_type}' requires human decision: {'; '.join(escalation_reason)}. "
                f"Escalating to supply chain leadership with full context."
            ),
            "timestamp": datetime.now().isoformat(),
            "autonomous": False,
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Disruption Response → ESCALATING TO LEADERSHIP")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Reason: {'; '.join(escalation_reason)}")
        print(f"           Impact: ${estimated_impact_usd:,.0f} | Locations: {', '.join(affected_locations)}\n")

    return decision
