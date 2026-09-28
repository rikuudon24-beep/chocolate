import numpy as np
import pandas as pd
from pathlib import Path
from exit_research import fetch_klines, first_index_at_or_after, stop_reason

RESULTS = Path(__file__).resolve().parents[1] / "results"
EXIT_TYPES = ["rsi48", "rsi50", "rsi52", "bb_mid", "time2", "time3", "time6", "time12"]

def evaluate(df, event, exit_type, use_structural_stop=True):
    entry_idx = first_index_at_or_after(df, pd.Timestamp(event["entry_time"]))
    if entry_idx is None:
        return None
    entry_price = float(event["entry_price"])
    event_low = float(event["event_low"])
    rows = df.iloc[entry_idx:entry_idx + 13]
    threshold = float(exit_type[3:]) if exit_type.startswith("rsi") else None
    time_candles = int(exit_type[4:]) if exit_type.startswith("time") else None
    for offset, (_, row) in enumerate(rows.iterrows()):
        if time_candles is not None and offset == time_candles - 1:
            return float(row["close"]) / entry_price - 1, False, "time"
        stop = stop_reason(row, event_low) if use_structural_stop else None
        if exit_type.startswith("rsi"):
            exit_hit = pd.notna(row["rsi14"]) and float(row["rsi14"]) >= threshold
        elif exit_type == "bb_mid":
            exit_hit = pd.notna(row["bb_mid"]) and float(row["close"]) >= float(row["bb_mid"])
        else:
            exit_hit = False
        if stop and exit_hit:
            return np.nan, True, "ambiguous"
        if stop:
            price = float(row["close"]) if stop == "bb_rebreak" else float(row["low"])
            return price / entry_price - 1, False, "structural_stop"
        if exit_hit:
            return float(row["close"]) / entry_price - 1, False, "signal_exit"
    return float(rows.iloc[-1]["close"]) / entry_price - 1, False, "no_exit_48h"

def main():
    events = pd.read_csv(RESULTS / "oos_events.csv")
    market = fetch_klines()
    rows = []
    for exit_type in EXIT_TYPES:
        for _, event in events.iterrows():
            a = evaluate(market, event, exit_type, True)
            b = evaluate(market, event, exit_type, False)
            rows.append({
                "event_id": int(event["event_id"]),
                "exit_type": exit_type,
                "return_with_stop": a[0],
                "return_without_stop": b[0],
                "ambiguous_with_stop": a[1],
                "with_stop_reason": a[2],
            })
    detail = pd.DataFrame(rows)
    detail.to_csv(RESULTS / "oos_structural_failure_events.csv", index=False)
    out = []
    for exit_type, g in detail.groupby("exit_type", sort=False):
        valid = g[~g["ambiguous_with_stop"]].copy()
        delta = valid["return_with_stop"] - valid["return_without_stop"]
        out.append({
            "exit_type": exit_type,
            "n": len(valid),
            "structural_stop_count": int((valid["with_stop_reason"] == "structural_stop").sum()),
            "ambiguous_count": int(g["ambiguous_with_stop"].sum()),
            "avg_return_with_stop": valid["return_with_stop"].mean(),
            "avg_return_without_stop": valid["return_without_stop"].mean(),
            "avg_stop_effect": delta.mean(),
            "median_stop_effect": delta.median(),
            "stop_effect_positive_rate": (delta > 0).mean(),
        })
    summary = pd.DataFrame(out)
    summary.to_csv(RESULTS / "oos_structural_failure_summary.csv", index=False)
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
