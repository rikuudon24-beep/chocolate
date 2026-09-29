import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import time

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
START = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
END = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
COST = 0.001
H = (2, 3, 6, 12)
N = 10000
SEED = 20260929
BASE_URL = "https://data-api.binance.vision/api/v3/klines"

def fetch():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    step = 4 * 60 * 60 * 1000
    while start_ms < end_ms:
        params = {"symbol":"BTCUSDT","interval":"4h","startTime":start_ms,"endTime":end_ms,"limit":1000}
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_start = int(batch[-1][0]) + step
        if next_start <= start_ms:
            raise RuntimeError("Pagination did not advance.")
        start_ms = next_start
        time.sleep(0.08)
        if len(batch) < 1000:
            break
    cols = ["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
    d = pd.DataFrame(rows, columns=cols)
    if d.empty:
        raise RuntimeError("No data returned.")
    d["open_time"] = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d[(d.open_time >= START) & (d.open_time < END)].sort_values("open_time").reset_index(drop=True)

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def extract_events(df):
    middle = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std(ddof=0)
    bb_lower = middle - 2 * std
    rsi14 = rsi(df["close"], 14)
    events = []
    i = 20
    consumed_until = -1
    while i < len(df) - 1:
        previous = df.iloc[i - 1]
        current = df.iloc[i]
        candidate = (
            i > consumed_until
            and pd.notna(bb_lower.iloc[i - 1])
            and pd.notna(bb_lower.iloc[i])
            and previous["close"] < bb_lower.iloc[i - 1]
            and current["close"] >= bb_lower.iloc[i]
            and pd.notna(rsi14.iloc[i])
            and rsi14.iloc[i] < 40
        )
        if not candidate:
            i += 1
            continue
        event_index = i
        event_low = float(current["low"])
        running_rsi_min = float(rsi14.iloc[i])
        confirmation_index = None
        failed = False
        window_end = min(i + 6, len(df) - 2)
        for j in range(i + 1, window_end + 1):
            row = df.iloc[j]
            if pd.notna(rsi14.iloc[j]):
                running_rsi_min = min(running_rsi_min, float(rsi14.iloc[j]))
            if float(row["low"]) < event_low or (
                pd.notna(bb_lower.iloc[j]) and float(row["close"]) < float(bb_lower.iloc[j])
            ):
                failed = True
                break
            if pd.notna(rsi14.iloc[j]) and float(rsi14.iloc[j]) >= running_rsi_min + 5:
                confirmation_index = j
                break
        if not failed and confirmation_index is not None:
            entry_index = confirmation_index + 1
            if entry_index < len(df):
                events.append({"event_id": len(events)+1, "year": current["open_time"].year, "ri": event_index, "entry": entry_index})
                consumed_until = entry_index
                i = entry_index + 1
                continue
        consumed_until = max(consumed_until, window_end)
        i += 1
    return pd.DataFrame(events)

def main():
    x = fetch()
    v = (x["volume"] - x["volume"].rolling(20).mean()) / x["volume"].rolling(20).std(ddof=0)
    ev = extract_events(x)
    if len(ev) != 95:
        raise RuntimeError(f"expected 95 frozen events, got {len(ev)}")
    def returns(mask, h):
        z = ev.loc[mask]
        vals = [x["close"].iloc[int(e)+h-1] / x["open"].iloc[int(e)] - 1 for e in z["entry"] if int(e)+h-1 < len(x)]
        return np.asarray(vals, dtype=float)
    obs = {h: returns(v.iloc[ev["ri"]].to_numpy() >= 1.0, h) for h in H}
    observed = {h: float(a.mean()) - COST for h, a in obs.items()}
    rng = np.random.default_rng(SEED)
    null = {h: np.empty(N) for h in H}
    for k in range(N):
        selected = []
        for _, g in ev.groupby("year"):
            shuffled = rng.permutation(v.iloc[g["ri"]].to_numpy(float))
            selected.extend(g.index[shuffled >= 1.0].tolist())
        mask = ev.index.isin(selected)
        for h in H:
            a = returns(mask, h)
            null[h][k] = a.mean() - COST if len(a) else np.nan
    rows = []
    for h in H:
        a = null[h]
        o = observed[h]
        rows.append({
            "horizon": h,
            "observed_net_avg": o,
            "null_mean": float(np.nanmean(a)),
            "null_p_one_sided": float((a >= o).mean()),
            "n_obs": int(len(obs[h])),
        })
    out = pd.DataFrame(rows)
    out.to_csv(R / "volume_state_permutation.csv", index=False)
    summary = {
        "purpose": "Descriptive permutation audit of fixed volume-z>=1 association; not an inferential p-value because threshold was previously explored on the same sample.",
        "events": 95, "permutations": N, "seed": SEED, "within_year_shuffle": True,
        "results": out.to_dict("records")
    }
    (R / "volume_state_permutation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(out.to_string(index=False))

if __name__ == "__main__":
    main()
