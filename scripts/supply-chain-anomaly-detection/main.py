"""
Supply Chain Anomaly Detection
Hybrid statistical + ML approach for demand signal disruption identification.

Usage:
    python main.py --input data/demand_signals.csv --output results/anomalies.json
"""

import argparse
import json
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def load_data(filepath: str) -> pd.DataFrame:
    """Load and validate demand signal data."""
    df = pd.read_csv(filepath, parse_dates=["date"])
    required_cols = {"date", "sku", "location", "units", "signal_type"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df.sort_values(["sku", "location", "date"]).reset_index(drop=True)


def detect_zscore(series: pd.Series, window: int = 28, threshold: float = 2.5) -> pd.Series:
    """Flag anomalies using rolling Z-score."""
    rolling_mean = series.rolling(window=window, min_periods=7).mean()
    rolling_std = series.rolling(window=window, min_periods=7).std()
    z_scores = (series - rolling_mean) / rolling_std.replace(0, np.nan)
    return z_scores.abs() > threshold


def detect_seasonal_residual(
    series: pd.Series, period: int = 7, threshold: float = 2.5
) -> pd.Series:
    """Flag anomalies in seasonal decomposition residuals."""
    # Simple seasonal decomposition: subtract rolling period mean
    seasonal = series.rolling(window=period, min_periods=period, center=True).mean()
    residual = series - seasonal.fillna(series.mean())
    residual_std = residual.rolling(window=28, min_periods=7).std()
    residual_z = residual.abs() / residual_std.replace(0, np.nan)
    return residual_z > threshold


def detect_isolation_forest(
    df_group: pd.DataFrame, contamination: float = 0.05
) -> pd.Series:
    """Flag anomalies using Isolation Forest on multivariate signals."""
    if len(df_group) < 20:
        return pd.Series(False, index=df_group.index)

    features = df_group[["units"]].copy()
    features["units_diff"] = features["units"].diff().fillna(0)
    features["units_rolling_mean"] = features["units"].rolling(7, min_periods=1).mean()
    features["units_ratio"] = features["units"] / features["units_rolling_mean"].replace(0, 1)

    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
    predictions = model.fit_predict(features.fillna(0))
    return pd.Series(predictions == -1, index=df_group.index)


def detect_anomalies(
    df: pd.DataFrame,
    zscore_threshold: float = 2.5,
    min_votes: int = 2,
    high_volume_percentile: float = 0.80,
) -> list[dict]:
    """
    Run all three detection methods and return majority-voted anomalies.

    Parameters:
        df: Input dataframe with demand signals
        zscore_threshold: Z-score threshold for statistical methods
        min_votes: Minimum detectors that must agree (default: 2 of 3)
        high_volume_percentile: Threshold for tighter sensitivity on top SKUs

    Returns:
        List of anomaly dictionaries
    """
    anomalies = []

    # Determine high-volume SKUs (tighter thresholds)
    sku_volumes = df.groupby("sku")["units"].sum()
    high_volume_threshold = sku_volumes.quantile(high_volume_percentile)
    high_volume_skus = set(sku_volumes[sku_volumes >= high_volume_threshold].index)

    # Process each SKU-location combination
    for (sku, location), group in df.groupby(["sku", "location"]):
        if len(group) < 14:
            continue  # Need minimum history for meaningful detection

        is_high_volume = sku in high_volume_skus
        threshold = zscore_threshold * 0.8 if is_high_volume else zscore_threshold

        # Run three detection methods
        zscore_flags = detect_zscore(group["units"], threshold=threshold)
        seasonal_flags = detect_seasonal_residual(group["units"], threshold=threshold)
        iforest_flags = detect_isolation_forest(group)

        # Majority voting
        vote_count = zscore_flags.astype(int) + seasonal_flags.astype(int) + iforest_flags.astype(int)
        anomaly_mask = vote_count >= min_votes

        # Build anomaly records
        for idx in group[anomaly_mask].index:
            row = df.loc[idx]
            rolling_mean = group["units"].rolling(28, min_periods=7).mean()
            expected = rolling_mean.loc[idx] if idx in rolling_mean.index else group["units"].mean()
            magnitude = abs(row["units"] - expected) / max(expected, 1)

            methods_flagged = []
            if zscore_flags.loc[idx]:
                methods_flagged.append("zscore")
            if seasonal_flags.loc[idx]:
                methods_flagged.append("seasonal_residual")
            if iforest_flags.loc[idx]:
                methods_flagged.append("isolation_forest")

            anomalies.append({
                "date": row["date"].isoformat(),
                "sku": sku,
                "location": location,
                "actual_units": int(row["units"]),
                "expected_units": round(float(expected), 1),
                "magnitude_pct": round(magnitude * 100, 1),
                "direction": "spike" if row["units"] > expected else "drop",
                "methods_flagged": methods_flagged,
                "vote_count": int(vote_count.loc[idx]),
                "sku_tier": "high_volume" if is_high_volume else "standard",
                "investigation_hint": _suggest_investigation(
                    row["units"], expected, methods_flagged, row.get("signal_type", "")
                ),
            })

    return sorted(anomalies, key=lambda x: x["magnitude_pct"], reverse=True)


def _suggest_investigation(actual: float, expected: float, methods: list, signal_type: str) -> str:
    """Generate a human-readable investigation suggestion."""
    if actual > expected * 1.5:
        return "Large spike — check for promotional event, viral social activity, or competitor stockout driving substitution."
    elif actual < expected * 0.5:
        return "Large drop — check for data feed interruption, store closure, or product availability issue."
    elif "isolation_forest" in methods and "zscore" not in methods:
        return "Multivariate anomaly — pattern unusual relative to correlated signals even if magnitude is modest."
    else:
        return "Moderate deviation — review recent events in market context before acting."


def generate_synthetic_data(n_skus: int = 5, n_days: int = 90) -> pd.DataFrame:
    """Generate synthetic demand data for demonstration."""
    np.random.seed(42)
    records = []

    for i in range(n_skus):
        sku = f"SKU-{1000 + i}"
        base = np.random.randint(100, 500)
        for day in range(n_days):
            date = pd.Timestamp("2026-03-01") + pd.Timedelta(days=day)
            seasonal = np.sin(2 * np.pi * day / 7) * base * 0.1
            noise = np.random.normal(0, base * 0.08)
            units = base + seasonal + noise

            # Inject anomalies
            if i == 0 and day == 45:
                units *= 2.2  # Demand spike
            if i == 2 and day == 60:
                units *= 0.3  # Demand drop

            records.append({
                "date": date,
                "sku": sku,
                "location": "DC-CHI-01",
                "units": max(int(units), 0),
                "signal_type": "pos_sellthrough",
            })

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description="Supply Chain Anomaly Detection")
    parser.add_argument("--input", type=str, help="Path to input CSV")
    parser.add_argument("--output", type=str, default="anomalies.json", help="Output JSON path")
    parser.add_argument("--threshold", type=float, default=2.5, help="Z-score threshold")
    parser.add_argument("--min-votes", type=int, default=2, help="Minimum detector votes")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic data")
    args = parser.parse_args()

    if args.demo:
        print("Generating synthetic demand data (5 SKUs, 90 days)...")
        df = generate_synthetic_data()
    elif args.input:
        print(f"Loading data from {args.input}...")
        df = load_data(args.input)
    else:
        parser.error("Provide --input or --demo")

    print(f"Processing {len(df)} records across {df['sku'].nunique()} SKUs...")
    anomalies = detect_anomalies(df, zscore_threshold=args.threshold, min_votes=args.min_votes)
    print(f"Detected {len(anomalies)} anomalies.")

    with open(args.output, "w") as f:
        json.dump(anomalies, f, indent=2)
    print(f"Results written to {args.output}")

    # Print top anomalies
    if anomalies:
        print(f"\nTop anomalies by magnitude:")
        for a in anomalies[:5]:
            print(f"  {a['date']} | {a['sku']} | {a['direction']} "
                  f"{a['magnitude_pct']}% | votes: {a['vote_count']}/3")


if __name__ == "__main__":
    main()
