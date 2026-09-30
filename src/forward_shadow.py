import time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from audit_oos import add_indicators, extract_events

def rma(series, period=14):
    a = series.to_numpy(float)
    out = np.full(len(a), np.nan)
    if len(a) < period:
        return pd.Series(out, index=series.index)
    out[period - 1] = np.nanmean(a[:period])
    alpha = 1.0 / period
    for i in range(period, len(a)):
        out[i] = (1 - alpha) * out[i - 1] + alpha * a[i]
    return pd.Series(out, index=series.index)

RESULTS = Path(__file__).resolve().parents[1] / "results"
SYMBOL = "BTCUSDT"
INTERVAL = "4h"
FROZEN_CUT = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
LIMIT = 1000
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
INDICATOR_WARMUP_CANDLES = 100


def fetch_live_closed():
    rows = []
    # Keep pre-cutoff candles solely as indicator warm-up context.
    # Forward events are filtered back to event_time >= FROZEN_CUT below.
    start_time = FROZEN_CUT - pd.Timedelta(hours=4 * INDICATOR_WARMUP_CANDLES)
    start_ms = int(start_time.timestamp() * 1000)
    now = pd.Timestamp.now(tz="UTC")
    end_ms = int(now.timestamp() * 1000)

    while start_ms < end_ms:
        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": LIMIT,
        }
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        rows.extend(batch)
        last_open = int(batch[-1][0])
        nxt = last_open + FOUR_HOURS_MS
        if nxt <= start_ms:
            raise RuntimeError("Pagination did not advance.")
        start_ms = nxt
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
        return df

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Only fully closed candles.
    df = (
        df[df["close_time"] <= pd.Timestamp.now(tz="UTC")]
        .sort_values("open_time")
        .drop_duplicates("open_time")
        .reset_index(drop=True)
    )
    return df


def main():
    df = fetch_live_closed()
    if df.empty:
        raise RuntimeError("No forward-shadow candles returned.")

    enriched = add_indicators(df)
    enriched["volume_z20"] = (
        (enriched["volume"] - enriched["volume"].rolling(20).mean())
        / enriched["volume"].rolling(20).std(ddof=0)
    )

    # Fixed historical rule, carried forward without any threshold changes.
    delta = enriched["close"].diff()
    avg_gain = rma(delta.clip(lower=0), 14)
    avg_loss = rma(-delta.clip(upper=0), 14)
    enriched["rsi_canonical"] = 100 - 100 / (
        1 + avg_gain / avg_loss.replace(0, np.nan)
    )
    enriched["bb_width"] = (
        4 * enriched["close"].rolling(20).std(ddof=0)
        / enriched["close"].rolling(20).mean()
    )
    enriched["atr_pct"] = (
        (enriched["high"] - enriched["low"]).rolling(14).mean()
        / enriched["close"]
    )

    events = extract_events(enriched)

    if events.empty:
        forward = events.copy()
    else:
        events["event_time"] = pd.to_datetime(events["event_time"], utc=True)
        forward = events[events["event_time"] >= FROZEN_CUT].copy()

    # Historical warm-up candles never enter the forward event denominator.
    # Attach the re-entry volume state so the pre-registered vol_z20>=1 candidate
    # can be evaluated forward without changing the base-event definition.
    if not forward.empty:
        reentry_map = enriched[
            ["open_time", "volume_z20", "rsi_canonical", "bb_width", "atr_pct"]
        ].copy()
        reentry_map = reentry_map.rename(
            columns={
                "open_time": "event_time",
                "volume_z20": "reentry_volume_z20",
                "rsi_canonical": "reentry_rsi",
                "bb_width": "reentry_bb_width",
                "atr_pct": "reentry_atr_pct",
            }
        )
        forward = forward.merge(reentry_map, on="event_time", how="left")

        entry_map = enriched[
            ["open_time", "volume_z20"]
        ].copy().rename(
            columns={
                "open_time": "entry_time",
                "volume_z20": "entry_volume_z20",
            }
        )
        forward = forward.merge(entry_map, on="entry_time", how="left")
    forward.to_csv(RESULTS / "forward_shadow_events.csv", index=False)
    volume_forward = (
        forward[forward["reentry_volume_z20"] >= 1.0].copy()
        if not forward.empty else forward.copy()
    )
    volume_forward.to_csv(RESULTS / "forward_shadow_volume_events.csv", index=False)

    fixed_rule_mask = (
        (forward["reentry_volume_z20"] >= 1.0)
        & (forward["reentry_rsi"] >= 30.0)
        & (forward["reentry_bb_width"] <= 0.12)
        & (forward["reentry_atr_pct"] < 0.02)
        & (forward["entry_volume_z20"] >= 0.0)
    ) if not forward.empty else pd.Series(dtype=bool)
    fixed_forward = forward[fixed_rule_mask].copy() if not forward.empty else forward.copy()
    fixed_forward.to_csv(
        RESULTS / "forward_shadow_fixed_rule_events.csv", index=False
    )

    rows = []
    volume_rows = []
    fixed_rows = []
    for _, e in forward.iterrows():
        entry_time = pd.to_datetime(e["entry_time"], utc=True)
        candidates = df.index[df["open_time"] >= entry_time]
        if len(candidates) == 0:
            continue

        pos = candidates[0]
        for h in [2, 3, 6, 12]:
            target = df.index.get_loc(pos) + h - 1
            if target >= len(df):
                continue

            ret = float(df.iloc[target]["close"]) / float(e["entry_price"]) - 1
            rows.append({
                "event_id": int(e["event_id"]),
                "event_time": e["event_time"].isoformat(),
                "horizon": h,
                "return": ret,
                "status": "matured",
            })
            if float(e["reentry_volume_z20"]) >= 1.0:
                volume_rows.append({
                    "event_id": int(e["event_id"]),
                    "event_time": e["event_time"].isoformat(),
                    "horizon": h,
                    "return": ret,
                    "status": "matured",
                })

            if bool(fixed_rule_mask.loc[e.name]) if not fixed_rule_mask.empty else False:
                fixed_rows.append({
                    "event_id": int(e["event_id"]),
                    "event_time": e["event_time"].isoformat(),
                    "horizon": h,
                    "return": ret,
                    "net_return_0_10pct_cost": ret - 0.001,
                    "status": "matured",
                })

    detail = pd.DataFrame(
        rows,
        columns=["event_id", "event_time", "horizon", "return", "status"],
    )
    detail.to_csv(RESULTS / "forward_shadow_returns.csv", index=False)
    volume_detail = pd.DataFrame(volume_rows, columns=["event_id", "event_time", "horizon", "return", "status"])
    volume_detail.to_csv(RESULTS / "forward_shadow_volume_returns.csv", index=False)

    fixed_detail = pd.DataFrame(
        fixed_rows,
        columns=[
            "event_id", "event_time", "horizon", "return",
            "net_return_0_10pct_cost", "status",
        ],
    )
    fixed_detail.to_csv(
        RESULTS / "forward_shadow_fixed_rule_returns.csv", index=False
    )

    print("fixed_rule_events", len(fixed_forward))
    print("matured_fixed_rule_returns", len(fixed_detail))
    if not fixed_detail.empty:
        print(
            fixed_detail.groupby("horizon")["net_return_0_10pct_cost"]
            .agg(["count", "mean", "median"])
            .to_string()
        )

    print("warmup_candles", INDICATOR_WARMUP_CANDLES)
    print("forward_volume_events", len(volume_forward))
    print("matured_volume_returns", len(volume_detail))
    print("forward_candles_including_warmup", len(df))
    print("forward_events", len(forward))
    print("matured_returns", len(detail))
    if not detail.empty:
        print(
            detail.groupby("horizon")["return"]
            .agg(["count", "mean", "median"])
            .to_string()
        )


if __name__ == "__main__":
    main()
