import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = pd.Timestamp("2020-01-01", tz="UTC")
END_EXCLUSIVE = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
LIMIT = 1000
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
COST = 0.001

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def fetch_klines():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END_EXCLUSIVE.timestamp() * 1000)
    while start_ms < end_ms:
        r = requests.get(BASE_URL, params={"symbol": SYMBOL, "interval": INTERVAL,
                                           "startTime": start_ms, "endTime": end_ms,
                                           "limit": LIMIT}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        start_ms = last_open + FOUR_HOURS_MS
        time.sleep(0.08)
        if len(batch) < LIMIT:
            break

    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base_volume",
            "taker_quote_volume", "ignore"]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[(df.open_time >= START) & (df.open_time < END_EXCLUSIVE)]
    now = pd.Timestamp.now(tz="UTC")
    return df[df.close_time <= now].sort_values("open_time").reset_index(drop=True)


def rsi(series, period=14):
    d = series.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    ag = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    al = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def enrich(df):
    x = df.copy()
    mid = x.close.rolling(20).mean()
    std = x.close.rolling(20).std(ddof=0)
    x["bb_mid"] = mid
    x["bb_lower"] = mid - 2 * std
    x["bb_width"] = (4 * std / mid).replace([np.inf, -np.inf], np.nan)
    x["rsi14"] = rsi(x.close, 14)

    prev_close = x.close.shift(1)
    tr = pd.concat([x.high - x.low, (x.high - prev_close).abs(),
                    (x.low - prev_close).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    x["atr_pct"] = x.atr14 / x.close

    mean20 = x.volume.rolling(20).mean()
    std20 = x.volume.rolling(20).std(ddof=0)
    x["vol_z20"] = (x.volume - mean20) / std20.replace(0, np.nan)
    return x


def extract_events(x):
    events = []
    i = 20
    consumed_until = -1
    while i < len(x) - 1:
        prev = x.iloc[i - 1]
        cur = x.iloc[i]
        candidate = (
            i > consumed_until
            and pd.notna(prev.bb_lower) and pd.notna(cur.bb_lower)
            and prev.close < prev.bb_lower
            and cur.close >= cur.bb_lower
            and pd.notna(cur.rsi14) and cur.rsi14 < 40
        )
        if not candidate:
            i += 1
            continue

        event_low = float(cur.low)
        rmin = float(cur.rsi14)
        confirm = None
        failed = False
        window_end = min(i + 6, len(x) - 2)

        for j in range(i + 1, window_end + 1):
            row = x.iloc[j]
            if pd.notna(row.rsi14):
                rmin = min(rmin, float(row.rsi14))
            if float(row.low) < event_low:
                failed = True
                break
            if pd.notna(row.bb_lower) and float(row.close) < float(row.bb_lower):
                failed = True
                break
            if pd.notna(row.rsi14) and float(row.rsi14) >= rmin + 5:
                confirm = j
                break

        if not failed and confirm is not None and confirm + 1 < len(x):
            e = x.iloc[confirm + 1]
            events.append({
                "event_id": len(events) + 1,
                "event_time": cur.open_time.isoformat(),
                "entry_time": e.open_time.isoformat(),
                "entry_index": confirm + 1,
                "reentry_rsi": float(cur.rsi14),
                "reentry_atr_pct": float(cur.atr_pct),
                "reentry_bb_width": float(cur.bb_width),
                "reentry_vol_z": float(cur.vol_z20),
                "year": int(cur.open_time.year),
            })
            consumed_until = confirm + 1
            i = confirm + 2
            continue

        consumed_until = max(consumed_until, window_end)
        i += 1
    return pd.DataFrame(events)


def add_returns(x, events):
    rows = []
    for _, e in events.iterrows():
        idx = int(e.entry_index)
        row = e.to_dict()
        entry = float(x.iloc[idx].open)
        row["entry_price"] = entry
        for h in [2, 3, 6, 12]:
            j = idx + h
            row[f"net_{h}h"] = float(x.iloc[j].close / entry - 1 - COST) if j < len(x) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def stratify(df):
    out = df.copy()
    out["rsi_bin"] = pd.cut(out.reentry_rsi, [-np.inf, 20, 30, 40, np.inf],
                            labels=["<20", "20-30", "30-40", ">=40"], right=False)
    out["atr_bin"] = pd.cut(out.reentry_atr_pct, [-np.inf, .01, .02, .04, np.inf],
                            labels=["<1%", "1-2%", "2-4%", ">=4%"], right=False)
    out["bb_bin"] = pd.cut(out.reentry_bb_width, [-np.inf, .05, .12, np.inf],
                           labels=["<0.05", "0.05-0.12", ">=0.12"], right=False)
    out["anchor"] = out.reentry_vol_z >= 1.0
    return out


def weighted_stratified_difference(df, strata):
    pieces = []
    for keys, g in df.groupby(strata, observed=True):
        a, c = g[g.anchor], g[~g.anchor]
        if len(a) == 0 or len(c) == 0:
            continue
        vals = keys if isinstance(keys, tuple) else (keys,)
        row = {k: v for k, v in zip(strata, vals)}
        row["anchor_n"], row["control_n"] = len(a), len(c)
        for h in [2, 3, 6, 12]:
            av, cv = a[f"net_{h}h"].dropna(), c[f"net_{h}h"].dropna()
            row[f"anchor_avg_{h}h"] = av.mean() if len(av) else np.nan
            row[f"control_avg_{h}h"] = cv.mean() if len(cv) else np.nan
            row[f"diff_{h}h"] = row[f"anchor_avg_{h}h"] - row[f"control_avg_{h}h"]                 if pd.notna(row[f"anchor_avg_{h}h"]) and pd.notna(row[f"control_avg_{h}h"]) else np.nan
        pieces.append(row)

    detail = pd.DataFrame(pieces)
    summary = []
    for h in [2, 3, 6, 12]:
        valid = detail.dropna(subset=[f"diff_{h}h"])
        if valid.empty:
            summary.append({"horizon": h, "strata_n": 0, "anchor_weighted_diff": np.nan})
            continue
        w = valid.anchor_n.to_numpy(float)
        d = valid[f"diff_{h}h"].to_numpy(float)
        summary.append({
            "horizon": h,
            "strata_n": int(len(valid)),
            "anchor_weighted_diff": float(np.average(d, weights=w)),
            "total_anchor_n_in_matched_strata": int(w.sum()),
        })
    return detail, pd.DataFrame(summary)


def main():
    x = enrich(fetch_klines())
    events = add_returns(x, extract_events(x))
    if len(events) != 95:
        raise RuntimeError(f"Frozen event count mismatch: {len(events)} != 95")

    events = stratify(events)
    outputs = {}
    for name, strata in {
        "year_rsi": ["year", "rsi_bin"],
        "year_atr": ["year", "atr_bin"],
        "year_bb": ["year", "bb_bin"],
    }.items():
        detail, summary = weighted_stratified_difference(events, strata)
        detail.to_csv(RESULTS / f"volume_anchor_stratified_{name}.csv", index=False)
        outputs[name] = summary.to_dict(orient="records")

    events.to_csv(RESULTS / "volume_anchor_stratified_events.csv", index=False)
    report = {
        "event_count": int(len(events)),
        "volume_anchor_count": int(events.anchor.sum()),
        "cost": COST,
        "definition": "reentry volume z20 >= 1.0",
        "stratifications": outputs,
        "warning": "Observational stratified control audit; not independent OOS and not a model-selection result.",
    }
    (RESULTS / "volume_anchor_stratified_control.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("=== VOLUME-ANCHOR-STRATIFIED-CONTROL ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
