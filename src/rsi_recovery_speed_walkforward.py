import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

HORIZONS = [2, 3, 6, 12]
COST = 0.001
SPLITS = [(2020, 2022, 2023), (2020, 2023, 2024),
          (2020, 2024, 2025), (2020, 2025, 2026)]

def build_events(df):
    events = extract_events(df)
    x = df.set_index("open_time")
    rows = []
    for _, e in events.iterrows():
        rt, ct = pd.Timestamp(e["reentry_time"]), pd.Timestamp(e["confirmation_time"])
        rr, cc = x.loc[rt], x.loc[ct]
        delay = int(round((ct - rt) / pd.Timedelta(hours=4)))
        if delay < 1:
            continue
        rsi_re = float(rr["rsi14"])
        rsi_conf = float(cc["rsi14"])
        delta = rsi_conf - rsi_re
        rows.append({
            "event_id": int(e["event_id"]),
            "year": int(pd.Timestamp(e["event_time"]).year),
            "reentry_time": e["reentry_time"],
            "confirmation_time": e["confirmation_time"],
            "entry_time": e["entry_time"],
            "rsi_reentry": rsi_re,
            "rsi_confirmation": rsi_conf,
            "rsi_delta": delta,
            "confirmation_delay_bars": delay,
            "rsi_recovery_speed": delta / delay,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    def classify(s):
        if s >= 3.0:
            return "fast"
        if s >= 1.0:
            return "moderate"
        if s >= 0.0:
            return "slow_positive"
        return "negative"

    out["category"] = out["rsi_recovery_speed"].map(classify)
    return out

def attach_returns(df, events):
    rows = []
    opens = df["open"].to_numpy()
    times = df["open_time"].to_numpy()
    index = {pd.Timestamp(t): i for i, t in enumerate(times)}
    for _, e in events.iterrows():
        entry_idx = index[pd.Timestamp(e["entry_time"])]
        for h in HORIZONS:
            exit_idx = entry_idx + h
            if exit_idx >= len(df):
                continue
            gross = float(opens[exit_idx] / opens[entry_idx] - 1)
            rows.append({**e.to_dict(), "horizon": h,
                         "gross_return": gross, "net_return": gross - COST})
    return pd.DataFrame(rows)

def summarize(rows):
    out = []
    for (cat, h), g in rows.groupby(["category", "horizon"]):
        vals = g["net_return"]
        gains, losses = vals[vals > 0].sum(), -vals[vals < 0].sum()
        out.append({
            "category": cat, "horizon": int(h), "n": int(len(vals)),
            "avg_net": float(vals.mean()), "median_net": float(vals.median()),
            "win": float((vals > 0).mean()),
            "pf": float(gains / losses) if losses > 0 else np.inf,
        })
    return pd.DataFrame(out).sort_values(["category", "horizon"])

def walkforward(rows):
    results = []
    for train_start, train_end, valid_year in SPLITS:
        train = rows[(rows["year"] >= train_start) & (rows["year"] <= train_end)]
        valid = rows[rows["year"] == valid_year]
        candidates = []
        for cat, g in train.groupby("category"):
            n = g["event_id"].nunique()
            if n >= 3:
                candidates.append((cat, n, g[g["horizon"] == 12]["net_return"].mean()))
        selected = sorted(candidates, key=lambda z: (-z[2], z[0]))[0][0] if candidates else None
        train_n = next((n for c, n, _ in candidates if c == selected), 0)
        for h in HORIZONS:
            v = valid[(valid["category"] == selected) & (valid["horizon"] == h)] if selected else valid.iloc[0:0]
            results.append({
                "train": f"{train_start}-{train_end}", "validation": str(valid_year),
                "selected_category": selected, "train_n": train_n, "horizon": h,
                "validation_n": int(v["event_id"].nunique()),
                "validation_avg_net": float(v["net_return"].mean()) if not v.empty else None,
                "validation_median_net": float(v["net_return"].median()) if not v.empty else None,
                "validation_win": float((v["net_return"] > 0).mean()) if not v.empty else None,
            })
    return pd.DataFrame(results)

def main():
    df = add_indicators(fetch_klines())
    events = build_events(df)
    if len(events) != 95:
        raise RuntimeError(f"Frozen event count changed: {len(events)} != 95")
    rows = attach_returns(df, events)
    rows.to_csv(RESULTS / "rsi_recovery_speed_events.csv", index=False)
    summarize(rows).to_csv(RESULTS / "rsi_recovery_speed_summary.csv", index=False)
    walkforward(rows).to_csv(RESULTS / "rsi_recovery_speed_walkforward.csv", index=False)
    audit = {
        "events": int(events["event_id"].nunique()),
        "cost_round_trip": COST,
        "horizons": HORIZONS,
        "category_definition": {
            "fast": "RSI confirmation minus RSI re-entry >= 3.0 points per 4H bar",
            "moderate": ">= 1.0 and < 3.0 points per bar",
            "slow_positive": ">= 0.0 and < 1.0 points per bar",
            "negative": "< 0.0 points per bar",
        },
        "information_boundary": "Only closed re-entry and confirmation candles are used.",
        "walkforward": "Highest training mean 12H net return among categories with >=3 events; fixed in validation.",
        "status": "research_only",
    }
    with open(RESULTS / "rsi_recovery_speed_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(summarize(rows).to_string(index=False))
    print(walkforward(rows).to_string(index=False))

if __name__ == "__main__":
    main()
