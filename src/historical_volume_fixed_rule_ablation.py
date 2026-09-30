import numpy as np
import pandas as pd
from pathlib import Path
from historical_volume_path_timing import fetch, events, rma

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
COST = 0.001

RULES = {
    "reentry_volume_z>=1": lambda x, i, p: x.iloc[i].vol_z20 >= 1.0,
    "reentry_rsi>=30": lambda x, i, p: x.iloc[i].rsi >= 30.0,
    "reentry_bb_width<=0.12": lambda x, i, p: x.iloc[i].bb_width <= 0.12,
    "reentry_atr_pct<0.02": lambda x, i, p: x.iloc[i].atr_pct < 0.02,
    "entry_volume_z>=0": lambda x, i, p: x.iloc[p].vol_z20 >= 0.0,
}

def build():
    x = fetch()
    e = events(x)
    if len(e) != 95:
        raise RuntimeError(f"expected95 got {len(e)}")

    x["vol_z20"] = (
        (x.volume - x.volume.rolling(20).mean())
        / x.volume.rolling(20).std(ddof=0)
    )
    d = x.close.diff()
    ag = rma(d.clip(lower=0), 14)
    al = rma(-d.clip(upper=0), 14)
    x["rsi"] = 100 - 100 / (1 + ag / al.replace(0, np.nan))
    x["bb_width"] = 4 * x.close.rolling(20).std(ddof=0) / x.close.rolling(20).mean()
    x["atr_pct"] = (x.high - x.low).rolling(14).mean() / x.close

    idx = dict(zip(x.open_time.astype(str), range(len(x))))
    rows = []
    for _, q in e.iterrows():
        i = idx[str(q.event_time)]
        p = int(q.entry)
        if p + 11 >= len(x):
            continue
        vals = {name: bool(fn(x, i, p)) for name, fn in RULES.items()}
        ret = float(x.iloc[p + 11].close / x.iloc[p].open - 1)
        rows.append({
            "event_id": int(q.event_id),
            "year": int(q.year),
            "ret12": ret,
            "net12": ret - COST,
            **vals,
        })
    return pd.DataFrame(rows)

def summarize(z):
    if len(z) == 0:
        return {"n": 0, "avg_net": np.nan, "win_rate": np.nan, "profit_factor": np.nan}
    gains = z.loc[z.net12 > 0, "net12"].sum()
    losses = -z.loc[z.net12 < 0, "net12"].sum()
    return {
        "n": len(z),
        "avg_net": z.net12.mean(),
        "win_rate": (z.net12 > 0).mean(),
        "profit_factor": gains / losses if losses > 0 else np.nan,
    }

def main():
    d = build()
    names = list(RULES)
    full = d[names].all(axis=1)

    # Exact fixed rule baseline.
    baseline = summarize(d[full])
    baseline["sample"] = "all_conditions"
    baseline["excluded_condition"] = ""
    rows = [baseline]

    # One-condition-at-a-time ablation. Diagnostic only; no selection/promotion.
    for name in names:
        mask = d[[n for n in names if n != name]].all(axis=1)
        s = summarize(d[mask])
        s["sample"] = "one_condition_removed"
        s["excluded_condition"] = name
        rows.append(s)

    # Leave-one-year-out audit of the exact fixed rule.
    years = sorted(d.year.unique())
    for y in years:
        mask = full & (d.year != y)
        s = summarize(d[mask])
        s["sample"] = "fixed_rule_leave_one_year_out"
        s["excluded_condition"] = f"year_{y}"
        s["excluded_year"] = y
        rows.append(s)

    out = pd.DataFrame(rows)
    out.to_csv(R / "historical_volume_fixed_rule_ablation.csv", index=False)

    # Event-level truth table for reproducibility.
    d["fixed_rule_selected"] = full
    d.to_csv(R / "historical_volume_fixed_rule_ablation_events.csv", index=False)

    print("=== FIXED RULE ABLATION ===")
    print(out.to_string(index=False))
    print("=== BASELINE ===")
    print(pd.Series(baseline).to_string())

if __name__ == "__main__":
    main()
