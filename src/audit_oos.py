import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
END_EXCLUSIVE = pd.Timestamp("2026-09-29 00:00:00", tz="UTC")
LIMIT = 1000
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
FOUR_HOURS_MS = 4 * 60 * 60 * 1000

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def fetch_klines():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END_EXCLUSIVE.timestamp() * 1000)

    while start_ms < end_ms:
        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": LIMIT,
        }
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()

        if not batch:
            break

        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_start = last_open + FOUR_HOURS_MS
        if next_start <= start_ms:
            raise RuntimeError("Pagination did not advance.")
        start_ms = next_start
        time.sleep(0.08)

        if len(batch) < LIMIT:
            break

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_volume", "taker_quote_volume", "ignore",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        raise RuntimeError("No data returned.")

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[
        (df["open_time"] >= START)
        & (df["open_time"] < END_EXCLUSIVE)
    ].sort_values("open_time").reset_index(drop=True)

    # Exclude the currently forming candle, if the API happens to return it.
    now = pd.Timestamp.now(tz="UTC")
    df = df[df["close_time"] <= now].reset_index(drop=True)

    return df


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def audit_data(df):
    duplicate_count = int(df["open_time"].duplicated().sum())
    diffs = df["open_time"].diff().dropna()
    expected = pd.Timedelta(hours=4)
    spacing_errors = diffs[diffs != expected]

    missing_candles = int(
        sum(max(int(diff / expected) - 1, 0) for diff in spacing_errors)
    )

    bad_ohlc_mask = (
        (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["high"] < df["low"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )

    summary = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "timezone": "UTC",
        "rows": int(len(df)),
        "first_open": df["open_time"].iloc[0].isoformat(),
        "last_open": df["open_time"].iloc[-1].isoformat(),
        "duplicate_open_times": duplicate_count,
        "spacing_error_count": int(len(spacing_errors)),
        "missing_candles_estimate": missing_candles,
        "ohlc_inconsistency_rows": int(bad_ohlc_mask.sum()),
    }

    return summary, spacing_errors


def add_indicators(df):
    out = df.copy()

    middle = out["close"].rolling(20).mean()
    std = out["close"].rolling(20).std(ddof=0)

    out["bb_mid"] = middle
    out["bb_lower"] = middle - 2 * std
    out["bb_z"] = (out["close"] - middle) / std.replace(0, np.nan)
    out["rsi14"] = rsi(out["close"], 14)

    return out


def extract_events(df):
    events = []
    i = 20
    consumed_until = -1

    while i < len(df) - 1:
        previous = df.iloc[i - 1]
        current = df.iloc[i]

        candidate = (
            i > consumed_until
            and pd.notna(previous["bb_lower"])
            and pd.notna(current["bb_lower"])
            and previous["close"] < previous["bb_lower"]
            and current["close"] >= current["bb_lower"]
            and pd.notna(current["rsi14"])
            and current["rsi14"] < 40
        )

        if not candidate:
            i += 1
            continue

        event_index = i
        event_low = float(current["low"])
        running_rsi_min = float(current["rsi14"])
        confirmation_index = None
        failed = False

        # The confirmation window is the next six closed candles.
        window_end = min(i + 6, len(df) - 2)

        for j in range(i + 1, window_end + 1):
            row = df.iloc[j]

            if pd.notna(row["rsi14"]):
                running_rsi_min = min(
                    running_rsi_min, float(row["rsi14"])
                )

            new_low = float(row["low"]) < event_low
            rebreak = (
                pd.notna(row["bb_lower"])
                and float(row["close"]) < float(row["bb_lower"])
            )

            if new_low or rebreak:
                failed = True
                break

            if (
                pd.notna(row["rsi14"])
                and float(row["rsi14"]) >= running_rsi_min + 5
            ):
                confirmation_index = j
                break

        if not failed and confirmation_index is not None:
            entry_index = confirmation_index + 1
            if entry_index < len(df):
                entry = df.iloc[entry_index]
                events.append(
                    {
                        "event_id": len(events) + 1,
                        "event_time": current["open_time"].isoformat(),
                        "reentry_time": current["open_time"].isoformat(),
                        "confirmation_time": df.iloc[
                            confirmation_index
                        ]["open_time"].isoformat(),
                        "entry_time": entry["open_time"].isoformat(),
                        "entry_price": float(entry["open"]),
                        "event_low": event_low,
                        "rsi_at_reentry": float(current["rsi14"]),
                        "rsi_min_before_confirmation": running_rsi_min,
                    }
                )
                consumed_until = entry_index
                i = entry_index + 1
                continue

        # A failed candidate consumes its observation window so a single
        # drawdown cannot create several overlapping events.
        consumed_until = max(consumed_until, window_end)
        i += 1

    return pd.DataFrame(events)


def main():
    df = fetch_klines()
    audit, spacing_errors = audit_data(df)

    if audit["duplicate_open_times"] != 0:
        raise RuntimeError("Duplicate open times detected.")

    if audit["spacing_error_count"] != 0:
        print("WARNING: spacing errors detected; see spacing_errors.csv")

    if audit["ohlc_inconsistency_rows"] != 0:
        raise RuntimeError("OHLC consistency errors detected.")

    df = add_indicators(df)
    events = extract_events(df)

    with open(RESULTS / "audit_summary.json", "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    if not spacing_errors.empty:
        spacing_errors.rename("delta").to_csv(
            RESULTS / "spacing_errors.csv", index=True
        )

    events.to_csv(RESULTS / "oos_events.csv", index=False)

    year_counts = {}
    if not events.empty:
        years = pd.to_datetime(events["event_time"], utc=True).dt.year
        year_counts = years.value_counts().sort_index().astype(int).to_dict()

    print("=== OOS-AUDIT-001 ===")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(f"independent_confirmed_events={len(events)}")
    print("year_counts=" + json.dumps(year_counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
