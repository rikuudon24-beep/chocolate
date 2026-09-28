import json
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
END_EXCLUSIVE = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
LIMIT = 1000
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

TRAIN_END = pd.Timestamp("2025-01-01 00:00:00", tz="UTC")
VALID_END = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
COST = 0.001  # 0.10% round-trip stress case
MIN_TRAIN_N = 20
MIN_VALID_N = 8


def fetch_klines():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END_EXCLUSIVE.timestamp() * 1000)
    while start_ms < end_ms:
        params = {
            "symbol": SYMBOL, "interval": INTERVAL,
            "startTime": start_ms, "endTime": end_ms, "limit": LIMIT,
        }
        r = requests.get(BASE_URL, params=params, timeout=30)
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

    cols = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_base_volume",
        "taker_quote_volume", "ignore",
    ]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        raise RuntimeError("No market data returned.")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    now = pd.Timestamp.now(tz="UTC")
    return df[
        (df["open_time"] >= START)
        & (df["open_time"] < END_EXCLUSIVE)
        & (df["close_time"] <= now)
    ].sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    al = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def add_indicators(df):
    out = df.copy()
    mid = out["close"].rolling(20).mean()
    std = out["close"].rolling(20).std(ddof=0)
    out["bb_mid"] = mid
    out["bb_lower"] = mid - 2 * std
    out["bb_z"] = (out["close"] - mid) / std.replace(0, np.nan)
    out["bb_width"] = (4 * std) / mid.replace(0, np.nan)
    out["rsi14"] = rsi(out["close"], 14)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - out["close"].shift()).abs(),
        (out["low"] - out["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["atr_pct"] = out["atr14"] / out["close"]
    out["ret4"] = out["close"].pct_change(1)
    out["ret12"] = out["close"].pct_change(3)
    out["ret24"] = out["close"].pct_change(6)
    out["vol_z20"] = (
        (out["volume"] - out["volume"].rolling(20).mean())
        / out["volume"].rolling(20).std(ddof=0).replace(0, np.nan)
    )
    return out


def extract_base_events(df):
    events = []
    i = 20
    consumed_until = -1
    while i < len(df) - 1:
        prev, cur = df.iloc[i - 1], df.iloc[i]
        candidate = (
            i > consumed_until
            and pd.notna(prev["bb_lower"])
            and pd.notna(cur["bb_lower"])
            and prev["close"] < prev["bb_lower"]
            and cur["close"] >= cur["bb_lower"]
            and pd.notna(cur["rsi14"])
            and cur["rsi14"] < 40
        )
        if not candidate:
            i += 1
            continue

        event_low = float(cur["low"])
        running_min = float(cur["rsi14"])
        confirmation_index = None
        failed = False
        window_end = min(i + 6, len(df) - 2)

        for j in range(i + 1, window_end + 1):
            row = df.iloc[j]
            if pd.notna(row["rsi14"]):
                running_min = min(running_min, float(row["rsi14"]))
            if float(row["low"]) < event_low:
                failed = True
                break
            if pd.notna(row["bb_lower"]) and float(row["close"]) < float(row["bb_lower"]):
                failed = True
                break
            if pd.notna(row["rsi14"]) and float(row["rsi14"]) >= running_min + 5:
                confirmation_index = j
                break

        if not failed and confirmation_index is not None:
            entry_idx = confirmation_index + 1
            if entry_idx < len(df):
                entry = df.iloc[entry_idx]
                events.append({
                    "event_id": len(events) + 1,
                    "event_time": cur["open_time"],
                    "confirmation_time": df.iloc[confirmation_index]["open_time"],
                    "entry_time": entry["open_time"],
                    "entry_price": float(entry["open"]),
                    "event_low": event_low,
                    "rsi_reentry": float(cur["rsi14"]),
                    "rsi_min": running_min,
                    "rsi_confirm": float(df.iloc[confirmation_index]["rsi14"]),
                    "bb_z_reentry": float(cur["bb_z"]),
                    "bb_width_reentry": float(cur["bb_width"]),
                    "atr_pct_reentry": float(cur["atr_pct"]),
                    "ret4_reentry": float(cur["ret4"]),
                    "ret12_reentry": float(cur["ret12"]),
                    "ret24_reentry": float(cur["ret24"]),
                    "vol_z20_reentry": float(cur["vol_z20"]),
                    "bb_z_entry": float(entry["bb_z"]),
                    "bb_width_entry": float(entry["bb_width"]),
                    "atr_pct_entry": float(entry["atr_pct"]),
                    "ret4_entry": float(entry["ret4"]),
                    "ret12_entry": float(entry["ret12"]),
                    "ret24_entry": float(entry["ret24"]),
                    "vol_z20_entry": float(entry["vol_z20"]),
                })
                consumed_until = entry_idx
                i = entry_idx + 1
                continue

        consumed_until = max(consumed_until, window_end)
        i += 1

    return pd.DataFrame(events)


def build_returns(market, events):
    rows = []
    times = market["open_time"].tolist()
    index = {t: i for i, t in enumerate(times)}
    for _, e in events.iterrows():
        pos = index.get(pd.Timestamp(e["entry_time"]))
        if pos is None:
            continue
        for h in (2, 3, 6, 12):
            target = pos + h - 1
            if target >= len(market):
                continue
            ret = float(market.iloc[target]["close"]) / float(e["entry_price"]) - 1
            rows.append({
                "event_id": int(e["event_id"]),
                "event_time": pd.Timestamp(e["event_time"]),
                "horizon": h,
                "return": ret,
            })
    return pd.DataFrame(rows)


def metrics(returns):
    if len(returns) == 0:
        return {"n": 0, "avg": np.nan, "win": np.nan, "pf": np.nan, "dd": np.nan, "net_avg": np.nan}
    x = pd.Series(returns, dtype=float)
    wins, losses = x[x > 0], x[x < 0]
    pf = wins.sum() / (-losses.sum()) if len(losses) else np.inf
    eq = (1 + x).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    return {
        "n": int(len(x)),
        "avg": float(x.mean()),
        "win": float((x > 0).mean()),
        "pf": float(pf),
        "dd": float(dd),
        "net_avg": float(x.mean() - COST),
    }


def apply_condition(events, feature, op, threshold):
    s = pd.to_numeric(events[feature], errors="coerce")
    if op == ">=":
        return s >= threshold
    if op == "<=":
        return s <= threshold
    raise ValueError(op)


def main():
    market = add_indicators(fetch_klines())
    events = extract_base_events(market)
    if events.empty:
        raise RuntimeError("No base events.")

    # Use only information available by entry time.
    events["year"] = pd.to_datetime(events["event_time"], utc=True).dt.year
    ret = build_returns(market, events)
    ret["year"] = pd.to_datetime(ret["event_time"], utc=True).dt.year

    features = [
        "rsi_reentry", "rsi_min", "rsi_confirm",
        "bb_z_reentry", "bb_width_reentry", "atr_pct_reentry",
        "ret4_reentry", "ret12_reentry", "ret24_reentry", "vol_z20_reentry",
        "bb_z_entry", "bb_width_entry", "atr_pct_entry",
        "ret4_entry", "ret12_entry", "ret24_entry", "vol_z20_entry",
    ]
    grid = {
        "rsi_reentry": [15, 20, 25, 30, 35, 38],
        "rsi_min": [15, 20, 25, 30, 35],
        "rsi_confirm": [25, 30, 35, 40, 45],
        "bb_z_reentry": [-3.0, -2.5, -2.2, -2.0, -1.8],
        "bb_width_reentry": [0.02, 0.03, 0.05, 0.08, 0.12],
        "atr_pct_reentry": [0.01, 0.02, 0.03, 0.05, 0.08],
        "ret4_reentry": [-0.08, -0.05, -0.03, -0.01, 0.0],
        "ret12_reentry": [-0.12, -0.08, -0.05, -0.02, 0.0],
        "ret24_reentry": [-0.20, -0.12, -0.08, -0.04, 0.0],
        "vol_z20_reentry": [-1.0, 0.0, 1.0, 2.0, 3.0],
        "bb_z_entry": [-2.5, -2.2, -2.0, -1.8, -1.5],
        "bb_width_entry": [0.02, 0.03, 0.05, 0.08, 0.12],
        "atr_pct_entry": [0.01, 0.02, 0.03, 0.05, 0.08],
        "ret4_entry": [-0.08, -0.05, -0.03, -0.01, 0.0],
        "ret12_entry": [-0.12, -0.08, -0.05, -0.02, 0.0],
        "ret24_entry": [-0.20, -0.12, -0.08, -0.04, 0.0],
        "vol_z20_entry": [-1.0, 0.0, 1.0, 2.0, 3.0],
    }

    directions = {}
    for f in features:
        directions[f] = "<=" if f.startswith(("rsi_", "bb_z_", "ret")) else ">="

    # Discovery uses 2020-2024 only. For each feature, evaluate every threshold
    # and keep the best few by a composite that rewards net expectancy and
    # win-rate while penalizing low sample size and drawdown.
    train_events = events[events["event_time"] < TRAIN_END].copy()
    valid_events = events[(events["event_time"] >= TRAIN_END) & (events["event_time"] < VALID_END)].copy()
    test_events = events[events["event_time"] >= VALID_END].copy()

    def score_row(m):
        if m["n"] < MIN_TRAIN_N:
            return -999
        return float(m["net_avg"] + 0.0015 * (m["win"] - 0.5) - 0.0005 * abs(min(m["dd"], 0)))

    candidates = []
    for f in features:
        for th in grid[f]:
            mask = apply_condition(train_events, f, directions[f], th)
            selected = train_events[mask]
            sub = ret[ret["event_id"].isin(selected["event_id"]) & (ret["horizon"] == 2)]
            m = metrics(sub["return"])
            candidates.append({
                "kind": "single", "feature": f, "op": directions[f],
                "threshold": th, "horizon": 2, **m, "score": score_row(m),
            })

    singles = pd.DataFrame(candidates).sort_values("score", ascending=False)
    top_single = singles.head(12)

    pair_candidates = []
    top_features = list(dict.fromkeys(top_single["feature"].tolist()))
    # Pair only the strongest univariate features; thresholds are still selected
    # exclusively on the training period.
    for f1, f2 in combinations(top_features, 2):
        for th1 in grid[f1]:
            for th2 in grid[f2]:
                mask = apply_condition(train_events, f1, directions[f1], th1) & apply_condition(
                    train_events, f2, directions[f2], th2
                )
                selected = train_events[mask]
                sub = ret[ret["event_id"].isin(selected["event_id"]) & (ret["horizon"] == 2)]
                m = metrics(sub["return"])
                if m["n"] < MIN_TRAIN_N:
                    continue
                pair_candidates.append({
                    "kind": "pair", "feature": f"{f1}&{f2}",
                    "op": f"{directions[f1]} & {directions[f2]}",
                    "threshold": f"{th1} & {th2}", "horizon": 2,
                    "f1": f1, "op1": directions[f1], "th1": th1,
                    "f2": f2, "op2": directions[f2], "th2": th2,
                    **m, "score": score_row(m),
                })

    pairs = pd.DataFrame(pair_candidates)
    if not pairs.empty:
        pairs = pairs.sort_values("score", ascending=False)

    shortlist = pd.concat([singles.head(10), pairs.head(20) if not pairs.empty else pd.DataFrame()], ignore_index=True)

    def select_mask(df, row):
        if row["kind"] == "single":
            return apply_condition(df, row["feature"], row["op"], float(row["threshold"]))
        return (
            apply_condition(df, row["f1"], row["op1"], float(row["th1"]))
            & apply_condition(df, row["f2"], row["op2"], float(row["th2"]))
        )

    results = []
    for rank, (_, cand) in enumerate(shortlist.iterrows(), start=1):
        for name, subset_events in [
            ("train", train_events), ("validation", valid_events), ("test", test_events)
        ]:
            mask = select_mask(subset_events, cand)
            selected = subset_events[mask]
            for h in (2, 3, 6, 12):
                sub = ret[ret["event_id"].isin(selected["event_id"]) & (ret["horizon"] == h)]
                m = metrics(sub["return"])
                results.append({
                    "rank": rank, "kind": cand["kind"], "feature": cand["feature"],
                    "threshold": cand["threshold"], "period": name, "horizon": h, **m,
                })

    out = pd.DataFrame(results)
    shortlist.to_csv(RESULTS / "condition_search_shortlist.csv", index=False)
    out.to_csv(RESULTS / "condition_search_results.csv", index=False)
    events.to_csv(RESULTS / "condition_search_events.csv", index=False)

    summary = {
        "base_events": int(len(events)),
        "train_events": int(len(train_events)),
        "validation_events": int(len(valid_events)),
        "test_events": int(len(test_events)),
        "cost": COST,
        "selection_rule": "train-only; single features then pairwise combinations of top univariate features; no test-period selection",
        "top_candidates": shortlist.head(10).to_dict("records"),
    }
    (RESULTS / "condition_search_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print("=== CONDITION SEARCH ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("=== OUT-OF-SAMPLE VALIDATION (top candidates, horizon 2) ===")
    print(
        out[(out["period"] == "validation") & (out["horizon"] == 2)]
        .sort_values(["net_avg", "win"], ascending=False)
        .head(15)
        .to_string(index=False)
    )
    print("=== FINAL TEST (2026, horizon 2) ===")
    print(
        out[(out["period"] == "test") & (out["horizon"] == 2)]
        .sort_values(["net_avg", "win"], ascending=False)
        .head(15)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
