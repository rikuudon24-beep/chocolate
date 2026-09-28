import json
import urllib.request
from pathlib import Path

import pandas as pd

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = "2020-01-01"
END = "2026-09-29"
BASE = "https://data-api.binance.vision/api/v3/klines"
LIMIT = 1000

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def fetch_klines():
    rows = []
    start_ms = int(pd.Timestamp(START, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(END, tz="UTC").timestamp() * 1000)

    while start_ms < end_ms:
        url = (
            f"{BASE}?symbol={SYMBOL}&interval={INTERVAL}"
            f"&startTime={start_ms}&endTime={end_ms}&limit={LIMIT}"
        )
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.loads(r.read().decode())

        if not batch:
            break

        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_start = last_open + 4 * 60 * 60 * 1000
        if next_start <= start_ms:
            raise RuntimeError("Pagination did not advance.")
        start_ms = next_start

        if len(batch) < LIMIT:
            break

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbav", "tbqav", "ignore",
    ]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        raise RuntimeError("No data returned.")

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)

    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    now = pd.Timestamp.now(tz="UTC")
    df = df[
        (df["open_time"] >= pd.Timestamp(START, tz="UTC"))
        & (df["open_time"] < pd.Timestamp(END, tz="UTC"))
        & (df["close_time"] <= now)
    ]

    return (
        df.drop_duplicates("open_time")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


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

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(df):
    out = df.copy()
    middle = out["close"].rolling(20).mean()
    std = out["close"].rolling(20).std(ddof=0)

    out["bb_lower"] = middle - 2 * std
    out["rsi14"] = rsi(out["close"], 14)
    return out


def build_events(df, recovery_delta):
    """
    Event extraction is intentionally kept structurally identical to the
    frozen OOS-AUDIT-001 logic. The only research variable is the required
    RSI recovery delta (+3 through +8 points).
    """
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

        event_low = float(current["low"])
        running_rsi_min = float(current["rsi14"])
        confirmation_index = None
        failed = False

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
                and float(row["rsi14"]) >= running_rsi_min + recovery_delta
            ):
                confirmation_index = j
                break

        if not failed and confirmation_index is not None:
            entry_index = confirmation_index + 1
            if entry_index < len(df):
                entry = df.iloc[entry_index]
                events.append(
                    {
                        "event_time": current["open_time"],
                        "confirmation_time": df.iloc[
                            confirmation_index
                        ]["open_time"],
                        "entry_time": entry["open_time"],
                        "entry_idx": entry_index,
                        "entry_price": float(entry["open"]),
                        "event_low": event_low,
                    }
                )
                consumed_until = entry_index
                i = entry_index + 1
                continue

        consumed_until = max(consumed_until, window_end)
        i += 1

    return pd.DataFrame(events)


def horizon_metrics(df, events, horizon):
    rows = []

    for _, event in events.iterrows():
        k = int(event["entry_idx"])
        end = min(k + horizon, len(df) - 1)

        entry = float(event["entry_price"])
        exit_close = float(df.iloc[end]["close"])

        path = df.iloc[k:end + 1]
        ret = exit_close / entry - 1.0
        mfe = float(path["high"].max()) / entry - 1.0
        mae = float(path["low"].min()) / entry - 1.0

        rows.append({
            "ret": ret,
            "mfe": mfe,
            "mae": mae,
        })

    x = pd.DataFrame(rows)
    if x.empty:
        return {
            "n": 0,
            "avg_return": None,
            "median_return": None,
            "win_rate": None,
            "profit_factor": None,
            "avg_mfe": None,
            "avg_mae": None,
        }

    gains = x.loc[x["ret"] > 0, "ret"].sum()
    losses = -x.loc[x["ret"] < 0, "ret"].sum()

    return {
        "n": int(len(x)),
        "avg_return": float(x["ret"].mean()),
        "median_return": float(x["ret"].median()),
        "win_rate": float((x["ret"] > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "avg_mfe": float(x["mfe"].mean()),
        "avg_mae": float(x["mae"].mean()),
    }


def main():
    df = add_indicators(fetch_klines())

    rows = []

    for delta in [3, 4, 5, 6, 7, 8]:
        events = build_events(df, delta)

        for horizon in [2, 3, 6, 12]:
            metrics = horizon_metrics(df, events, horizon)
            rows.append({
                "recovery_delta": delta,
                "horizon_candles": horizon,
                **metrics,
            })

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "oos_robustness.csv", index=False)

    # Also save the event counts separately so changes in the signal set
    # cannot be confused with pure exit-horizon effects.
    event_counts = (
        out[["recovery_delta", "n"]]
        .drop_duplicates()
        .rename(columns={"n": "event_count"})
    )
    event_counts.to_csv(RESULTS / "oos_robustness_event_counts.csv", index=False)

    print("=== OOS-004 corrected robustness ===")
    print(out.to_string(index=False))
    print("\n=== event counts by recovery delta ===")
    print(event_counts.to_string(index=False))


if __name__ == "__main__":
    main()
