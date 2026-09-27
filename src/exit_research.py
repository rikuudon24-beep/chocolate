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
FOUR_HOURS = pd.Timedelta(hours=4)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


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
        start_ms = last_open + 4 * 60 * 60 * 1000
        time.sleep(0.08)

        if len(batch) < LIMIT:
            break

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_volume", "taker_quote_volume", "ignore",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    now = pd.Timestamp.now(tz="UTC")
    df = df[
        (df["open_time"] >= START)
        & (df["open_time"] < END_EXCLUSIVE)
        & (df["close_time"] <= now)
    ].sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)

    middle = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std(ddof=0)
    df["bb_mid"] = middle
    df["bb_lower"] = middle - 2 * std

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))

    return df


def first_index_at_or_after(df, ts):
    values = df["open_time"].searchsorted(ts)
    if values >= len(df):
        return None
    if df.iloc[values]["open_time"] != ts:
        return None
    return int(values)


def stop_reason(row, event_low):
    new_low = float(row["low"]) < float(event_low)
    rebreak = pd.notna(row["bb_lower"]) and float(row["close"]) < float(row["bb_lower"])

    if new_low and rebreak:
        return "new_low+bb_rebreak"
    if new_low:
        return "new_low"
    if rebreak:
        return "bb_rebreak"
    return None


def evaluate_event(df, event, exit_type):
    entry_time = pd.Timestamp(event["entry_time"])
    entry_price = float(event["entry_price"])
    event_low = float(event["event_low"])

    entry_idx = first_index_at_or_after(df, entry_time)
    if entry_idx is None:
        return None

    max_candles = 12  # 48H
    rows = df.iloc[entry_idx: entry_idx + max_candles + 1].copy()
    if rows.empty:
        return None

    threshold = None
    time_candles = None
    if exit_type.startswith("rsi"):
        threshold = float(exit_type.replace("rsi", ""))
    elif exit_type == "bb_mid":
        pass
    elif exit_type.startswith("time"):
        time_candles = int(exit_type.replace("time", ""))

    for offset, (_, row) in enumerate(rows.iterrows(), start=0):
        # A time exit is evaluated at the close of the Nth elapsed 4H candle.
        if time_candles is not None and offset == time_candles - 1:
            price = float(row["close"])
            return {
                "exit_reason": exit_type,
                "exit_time": row["open_time"].isoformat(),
                "exit_price": price,
                "return": price / entry_price - 1,
                "hold_candles": offset + 1,
                "ambiguous": False,
            }

        stop = stop_reason(row, event_low)

        if exit_type.startswith("rsi"):
            exit_hit = pd.notna(row["rsi14"]) and float(row["rsi14"]) >= threshold
        elif exit_type == "bb_mid":
            exit_hit = pd.notna(row["bb_mid"]) and float(row["close"]) >= float(row["bb_mid"])
        else:
            exit_hit = False

        if stop and exit_hit:
            # OHLC cannot establish which happened first.
            # Neutral excludes this event; conservative uses the candle low.
            conservative_price = float(row["low"])
            return {
                "exit_reason": "ambiguous:" + stop + "+" + exit_type,
                "exit_time": row["open_time"].isoformat(),
                "exit_price": float(row["close"]),
                "conservative_price": conservative_price,
                "return": float(row["close"]) / entry_price - 1,
                "conservative_return": conservative_price / entry_price - 1,
                "hold_candles": offset + 1,
                "ambiguous": True,
            }

        if stop:
            if stop == "bb_rebreak":
                price = float(row["close"])
            else:
                price = float(row["low"])
            return {
                "exit_reason": "stop:" + stop,
                "exit_time": row["open_time"].isoformat(),
                "exit_price": price,
                "return": price / entry_price - 1,
                "hold_candles": offset + 1,
                "ambiguous": False,
            }

        if exit_hit:
            price = float(row["close"])
            return {
                "exit_reason": exit_type,
                "exit_time": row["open_time"].isoformat(),
                "exit_price": price,
                "return": price / entry_price - 1,
                "hold_candles": offset + 1,
                "ambiguous": False,
            }

    # No exit/stop within the 48H window.
    last = rows.iloc[-1]
    price = float(last["close"])
    return {
        "exit_reason": "no_exit_48h",
        "exit_time": last["open_time"].isoformat(),
        "exit_price": price,
        "return": price / entry_price - 1,
        "hold_candles": len(rows),
        "ambiguous": False,
    }


def summarize(df, exit_type):
    numeric = df["return"].dropna()
    if numeric.empty:
        return {
            "exit": exit_type,
            "n": 0,
            "avg_return": None,
            "median_return": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown": None,
            "ambiguous": 0,
        }

    wins = numeric[numeric > 0]
    losses = numeric[numeric < 0]
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else np.inf

    equity = (1 + numeric.reset_index(drop=True)).cumprod()
    drawdown = equity / equity.cummax() - 1

    return {
        "exit": exit_type,
        "n": int(len(numeric)),
        "avg_return": float(numeric.mean()),
        "median_return": float(numeric.median()),
        "win_rate": float((numeric > 0).mean()),
        "profit_factor": float(pf),
        "max_drawdown": float(drawdown.min()),
        "avg_hold_candles": float(
            df["hold_candles"].dropna().mean()
        ),
        "ambiguous": int(df["ambiguous"].sum()),
    }


def main():
    events = pd.read_csv(RESULTS / "oos_events.csv")
    market = fetch_klines()

    exit_types = [
        "rsi48", "rsi50", "rsi52",
        "bb_mid",
        "time2", "time3", "time6", "time12",
    ]

    all_rows = []
    summary_rows = []

    for exit_type in exit_types:
        rows = []
        for _, event in events.iterrows():
            result = evaluate_event(market, event, exit_type)
            if result is None:
                continue

            row = event.to_dict()
            row.update(result)
            row["exit_type"] = exit_type
            rows.append(row)

        result_df = pd.DataFrame(rows)
        if not result_df.empty:
            result_df["return"] = pd.to_numeric(result_df["return"])
            result_df["year"] = pd.to_datetime(
                result_df["entry_time"], utc=True
            ).dt.year
            all_rows.append(result_df)

        summary_rows.append(summarize(result_df, exit_type))

    detail = pd.concat(all_rows, ignore_index=True)
    detail.to_csv(RESULTS / "oos_exit_events.csv", index=False)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(RESULTS / "oos_exit_summary.csv", index=False)

    yearly = (
        detail.groupby(["exit_type", "year"])
        .agg(
            n=("return", "size"),
            avg_return=("return", "mean"),
            median_return=("return", "median"),
            win_rate=("return", lambda x: float((x > 0).mean())),
        )
        .reset_index()
    )
    yearly.to_csv(RESULTS / "oos_exit_yearly.csv", index=False)

    print("=== OOS-003 EXIT RESEARCH ===")
    print(summary.to_string(index=False))
    print("=== YEARLY ===")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    main()
