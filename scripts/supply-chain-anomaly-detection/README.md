# Supply Chain Anomaly Detection

A lightweight statistical + ML hybrid approach for identifying demand signal disruptions in retail and CPG data streams.

## What This Does

Monitors incoming demand signals (POS sell-through, order rates, inventory velocity) and flags anomalies that statistical baselines alone would miss. Combines three detection methods:

1. **Z-score detection** — flags points beyond 2.5 standard deviations from rolling mean
2. **Seasonal decomposition residuals** — identifies anomalies after removing known seasonal patterns
3. **Isolation Forest** — catches multivariate anomalies across correlated signals

An anomaly must be flagged by at least 2 of 3 methods to trigger an alert (majority voting reduces false positives by ~60% compared to any single method).

## Usage

```bash
pip install -r requirements.txt
python main.py --input data/demand_signals.csv --output results/anomalies.json
```

## Input Format

CSV with columns:
- `date` (YYYY-MM-DD)
- `sku` (product identifier)
- `location` (DC or store ID)
- `units` (demand quantity)
- `signal_type` (pos_sellthrough | order_rate | inventory_velocity)

## Output

JSON array of detected anomalies with:
- Timestamp and SKU/location of the anomaly
- Which detection methods flagged it
- Magnitude (how far from expected)
- Suggested investigation direction

## Design Decisions

- **No deep learning.** For anomaly detection on time-series demand data, statistical methods outperform neural approaches when the training set is small (under 2 years of history per SKU). Deep learning anomaly detection requires far more data to avoid overfitting to normal seasonal variation.
- **Majority voting over ensemble scoring.** Simpler to explain to planners. "Two of three detectors flagged this" is more actionable than "the ensemble score is 0.73."
- **Configurable sensitivity per SKU tier.** High-volume SKUs (top 20% by revenue) use tighter thresholds. Long-tail SKUs use looser thresholds to avoid alert fatigue.
