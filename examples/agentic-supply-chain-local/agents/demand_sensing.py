"""
Demand Sensing Agent

Analyzes incoming signals and produces demand forecast adjustments.
In production, this uses Bedrock for reasoning about unstructured signals.
In this demo, it uses deterministic rules to demonstrate the decision pattern.
"""

from datetime import datetime


def process_demand_signal(signal: dict) -> dict:
    """
    Process a demand signal and produce a forecast adjustment.

    Decision logic:
    - POS velocity increase + active promo → adjust up (high confidence)
    - POS velocity increase without promo → adjust up (medium confidence)
    - POS velocity decrease → adjust down (medium confidence)
    """
    magnitude = signal["magnitude_pct"]
    has_promo = bool(signal.get("active_promo"))

    # Determine adjustment
    if magnitude > 10 and has_promo:
        adjustment_pct = round(magnitude * 0.65, 1)  # Dampen slightly (promo effect is temporary)
        confidence = 0.84
        reasoning = (
            f"POS velocity +{magnitude}% over 7-day baseline with active promo "
            f"'{signal['active_promo']}'. Adjusting forecast up by {adjustment_pct}% "
            f"(dampened from raw signal — promo lifts are typically temporary)."
        )
    elif magnitude > 10:
        adjustment_pct = round(magnitude * 0.5, 1)
        confidence = 0.68
        reasoning = (
            f"POS velocity +{magnitude}% without identified promo. Could be organic trend "
            f"or competitor stockout. Applying conservative +{adjustment_pct}% adjustment "
            f"pending next data refresh."
        )
    elif magnitude < -10:
        adjustment_pct = round(magnitude * 0.4, 1)
        confidence = 0.61
        reasoning = (
            f"POS velocity {magnitude}% below baseline. Reducing forecast to avoid "
            f"overstock. Monitoring for recovery signal."
        )
    else:
        adjustment_pct = 0
        confidence = 0.90
        reasoning = f"Signal magnitude {magnitude}% is within normal variance. No adjustment needed."

    decision = {
        "agent": "demand-sensing",
        "decision_type": "forecast_adjustment",
        "sku": signal["sku"],
        "location": signal["location"],
        "adjustment_pct": adjustment_pct,
        "confidence": confidence,
        "reasoning": reasoning,
        "source_signal_id": signal["signal_id"],
        "timestamp": datetime.now().isoformat(),
        "autonomous": abs(adjustment_pct) <= 15,  # Within autonomous boundary
    }

    status = "acting autonomously" if decision["autonomous"] else "ESCALATING (exceeds 15% threshold)"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] AGENT: Demand Sensing → analyzing signal...")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] DECISION: Adjust forecast {'+' if adjustment_pct > 0 else ''}{adjustment_pct}% (confidence: {confidence})")
    print(f"           Reasoning: {reasoning}")
    print(f"           Status: {status}")
    print(f"           EVENT: demand.adjustment.published → EventBridge\n")

    return decision
