"""Audit BTCUSDT futures open-interest state at the frozen spot-BTC re-entry events.

Information boundary:
- event timestamps come from the frozen 95-event spot dataset.
- re-entry candle is treated as closed at reentry_time + 4h.
- use only futures metrics with timestamp <= that close.
- no threshold tuning is performed in this script.
"""
import io, zipfile, urllib.request
from pathlib import Path
import pandas as pd
import numpy as np

EVENTS = "results/bb_decomposition_redundancy_events.csv"
OUT_EVENTS = "results/open_interest_events.csv"
OUT_SUMMARY = "results/open_interest_summary.csv"
COST = 0.001
BASE = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{date}.zip"

def fetch_day(day):
    url = BASE.format(date=day)
    try:
        raw = urllib.request.urlopen(url, timeout=30).read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = z.namelist()[0]
            return pd.read_csv(z.open(name))
    except Exception:
        return pd.DataFrame()

def main():
    ev = pd.read_csv(EVENTS, parse_dates=["reentry_time","entry_time"])
    frames = []
    days = set()
    for t in ev["reentry_time"]:
        close = t + pd.Timedelta(hours=4)
        days.add(close.strftime("%Y-%m-%d"))
        days.add((close - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    for d in sorted(days):
        x = fetch_day(d)
        if not x.empty:
            frames.append(x)
    if not frames:
        raise RuntimeError("No Binance metrics files downloaded")
    m = pd.concat(frames, ignore_index=True)
    cols = {c.lower(): c for c in m.columns}
    ts_col = cols.get("timestamp") or cols.get("create_time")
    oi_col = cols.get("sum_open_interest_value") or cols.get("sum_open_interest")
    if not ts_col or not oi_col:
        raise RuntimeError(f"Unexpected metrics columns: {list(m.columns)}")
    m["ts"] = pd.to_datetime(m[ts_col], utc=True)
    m["oi"] = pd.to_numeric(m[oi_col], errors="coerce")
    m = m.dropna(subset=["ts","oi"]).sort_values("ts").drop_duplicates("ts")
    m["oi_chg_4h"] = m["oi"].pct_change(48)       # native 5m cadence
    m["oi_chg_12h"] = m["oi"].pct_change(144)
    m["oi_chg_24h"] = m["oi"].pct_change(288)
    m["oi_value_z288"] = (m["oi"] - m["oi"].rolling(288).mean()) / m["oi"].rolling(288).std()

    rows = []
    for _, e in ev.iterrows():
        close = e.reentry_time + pd.Timedelta(hours=4)
        q = m[m["ts"] <= close]
        if q.empty:
            continue
        r = q.iloc[-1]
        row = e.to_dict()
        row.update({
            "metrics_ts": r["ts"],
            "oi": r["oi"],
            "oi_chg_4h": r["oi_chg_4h"],
            "oi_chg_12h": r["oi_chg_12h"],
            "oi_chg_24h": r["oi_chg_24h"],
            "oi_value_z288": r["oi_value_z288"],
            "data_available": True,
        })
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("No event could be matched to OI metrics")

    # Fixed descriptive states; thresholds are deliberately coarse and pre-declared.
    out["oi_state_4h"] = np.select(
        [out.oi_chg_4h <= -0.02, out.oi_chg_4h >= 0.02],
        ["falling","rising"], default="flat"
    )
    out["oi_state_12h"] = np.select(
        [out.oi_chg_12h <= -0.05, out.oi_chg_12h >= 0.05],
        ["falling","rising"], default="flat"
    )
    out["oi_price_context"] = np.select(
        [
            (out.oi_chg_12h > 0.02) & (out.net_12h > 0),
            (out.oi_chg_12h > 0.02) & (out.net_12h <= 0),
            (out.oi_chg_12h <= 0.02) & (out.oi_chg_12h > -0.02),
            out.oi_chg_12h <= -0.02,
        ],
        ["oi_up_rebound","oi_up_failed_rebound","oi_flat","oi_down"],
        default="unknown"
    )

    summaries = []
    for key in ["oi_state_4h","oi_state_12h","oi_price_context"]:
        for state, g in out.groupby(key, dropna=False):
            for h in [2,3,6,12]:
                col = f"net_{h}h"
                x = g[col].dropna()
                if len(x):
                    gains = x[x > 0].sum()
                    losses = -x[x < 0].sum()
                    pf = gains / losses if losses > 0 else np.inf
                    summaries.append({
                        "feature": key, "state": state, "n": len(x),
                        "avg_net": x.mean(), "median_net": x.median(),
                        "win_rate": (x > 0).mean(), "profit_factor": pf,
                        "horizon": h,
                    })
    out.to_csv(OUT_EVENTS, index=False)
    pd.DataFrame(summaries).to_csv(OUT_SUMMARY, index=False)
    print(f"matched={len(out)}/{len(ev)}")
    print(pd.DataFrame(summaries).to_string(index=False))

if __name__ == "__main__":
    main()
