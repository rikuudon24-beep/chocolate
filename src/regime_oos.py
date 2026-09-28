import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
END_EXCLUSIVE = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
LIMIT = 1000
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
FOUR_HOURS_MS = 4 * 60 * 60 * 1000

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def fetch_4h():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END_EXCLUSIVE.timestamp() * 1000)
    while start_ms < end_ms:
        params = {"symbol": SYMBOL, "interval": INTERVAL,
                  "startTime": start_ms, "endTime": end_ms, "limit": LIMIT}
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
    cols = ["open_time","open","high","low","close","volume","close_time",
            "quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    now = pd.Timestamp.now(tz="UTC")
    return df[(df["open_time"] >= START) & (df["open_time"] < END_EXCLUSIVE) &
              (df["close_time"] <= now)].sort_values("open_time").reset_index(drop=True)


def rsi(s, period=14):
    d = s.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    ag = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    al = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def load_events():
    return pd.read_csv(RESULTS / "oos_events.csv", parse_dates=["event_time","entry_time"])


def main():
    df = fetch_4h()
    # UTC daily candles: close is the last closed 4H candle of each UTC day.
    daily = (df.set_index("open_time")
               .resample("1D", label="left", closed="left")
               .agg({"open":"first","high":"max","low":"min","close":"last"}).dropna())
    daily["sma200"] = daily["close"].rolling(200, min_periods=200).mean()
    daily["rsi14"] = rsi(daily["close"], 14)

    # Frozen, pre-result regime definition:
    # BULL: close > SMA200 and RSI14 >= 50
    # BEAR: close < SMA200 and RSI14 < 50
    # NEUTRAL: everything else.
    daily["regime"] = np.select(
        [(daily["close"] > daily["sma200"]) & (daily["rsi14"] >= 50),
         (daily["close"] < daily["sma200"]) & (daily["rsi14"] < 50)],
        ["bull","bear"], default="neutral"
    )

    events = load_events()
    events["entry_day"] = events["entry_time"].dt.floor("D")
    merged = events.merge(
        daily[["close","sma200","rsi14","regime"]].rename(columns={
            "close":"daily_close","sma200":"daily_sma200","rsi14":"daily_rsi14"}),
        left_on="entry_day", right_index=True, how="left"
    )

    # Market-reaction metrics on the audited 95-event set.
    # Uses existing OOS exit returns to avoid redefining P&L.
    exit_events = pd.read_csv(RESULTS / "oos_exit_events.csv")
    exit_events["entry_time"] = pd.to_datetime(exit_events["entry_time"], utc=True)
    keep = exit_events[["event_id","exit_type","return","year"]]
    merged = merged.merge(keep, on="event_id", how="left")

    rows = []
    for regime, g in merged.groupby("regime", dropna=False):
        for exit_type, e in g.groupby("exit_type"):
            rs = e["return"].dropna()
            wins = rs[rs > 0]
            losses = rs[rs < 0]
            pf = wins.sum() / abs(losses.sum()) if len(losses) else np.nan
            rows.append({
                "regime": regime, "exit_type": exit_type, "n": len(rs),
                "avg_return": rs.mean(), "median_return": rs.median(),
                "win_rate": (rs > 0).mean(), "profit_factor": pf
            })
    summary = pd.DataFrame(rows).sort_values(["regime","exit_type"])
    merged.to_csv(RESULTS / "oos_1d_regime_events.csv", index=False)
    summary.to_csv(RESULTS / "oos_1d_regime_summary.csv", index=False)
    pd.DataFrame([{
        "regime_definition": "BULL=Daily close>SMA200 and Daily RSI14>=50; BEAR=Daily close<SMA200 and Daily RSI14<50; otherwise NEUTRAL",
        "assignment_time": "UTC daily state at event entry day",
        "event_count": len(merged),
        "bull_events": int((merged.regime=="bull").sum()),
        "neutral_events": int((merged.regime=="neutral").sum()),
        "bear_events": int((merged.regime=="bear").sum())
    }]).to_csv(RESULTS / "oos_1d_regime_definition.csv", index=False)


if __name__ == "__main__":
    main()
