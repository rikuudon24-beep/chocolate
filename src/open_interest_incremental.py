"""Leakage-free incremental validation for BTC open-interest states.

Uses only OI state fields known at the entry boundary. Outcome-derived
oi_price_context is intentionally excluded.
"""
import pandas as pd
import numpy as np

A = pd.read_csv("results/open_interest_events.csv", parse_dates=["event_time"])
A = A[A["anchor"] == True].copy()
A["event_time"] = pd.to_datetime(A["event_time"], utc=True)
A["sample"] = np.where(
    A["event_time"] < pd.Timestamp("2025-01-01", tz="UTC"),
    "development",
    "OOS_2025_plus",
)

rows = []
for sample, g in A.groupby("sample", sort=True):
    for state_col in ["oi_state_4h", "oi_state_12h"]:
        for state, h in g.groupby(state_col):
            for n in [2, 3, 6, 12]:
                x = pd.to_numeric(h[f"net_{n}h"], errors="coerce").dropna()
                if len(x):
                    gains = x[x > 0].sum()
                    losses = -x[x < 0].sum()
                    rows.append({
                        "sample": sample,
                        "feature": state_col,
                        "state": state,
                        "horizon_h": n,
                        "n": len(x),
                        "avg_net": x.mean(),
                        "median_net": x.median(),
                        "win_rate": (x > 0).mean(),
                        "profit_factor": gains / losses if losses > 0 else np.inf,
                    })

out = pd.DataFrame(rows)
out.to_csv("results/open_interest_incremental.csv", index=False)

cand = out[
    (out["sample"] == "OOS_2025_plus")
    & (out["feature"] == "oi_state_4h")
    & (out["state"] == "falling")
].copy()
cand.to_csv("results/open_interest_oos_candidate.csv", index=False)

print(out.to_string(index=False))
print("\nOOS candidate: oi_state_4h=falling")
print(cand.to_string(index=False))
