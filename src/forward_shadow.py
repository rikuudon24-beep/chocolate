import pandas as pd
from pathlib import Path
from audit_oos import fetch_klines, add_indicators, extract_events

RESULTS = Path(__file__).resolve().parents[1] / "results"
FROZEN_CUT = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")

def main():
    df = fetch_klines()
    df = add_indicators(df)
    events = extract_events(df)
    events["event_time"] = pd.to_datetime(events["event_time"], utc=True)
    forward = events[events["event_time"] >= FROZEN_CUT].copy()
    forward.to_csv(RESULTS / "forward_shadow_events.csv", index=False)

    rows = []
    for _, e in forward.iterrows():
        entry_time = pd.Timestamp(e["entry_time"], tz="UTC")
        entry_candidates = df.index[df["open_time"] >= entry_time]
        if len(entry_candidates) == 0:
            continue
        pos = df.index.get_loc(entry_candidates[0])
        for h in [2, 3, 6, 12]:
            target = pos + h - 1
            if target >= len(df):
                continue
            ret = float(df.iloc[target].close) / float(e.entry_price) - 1
            rows.append({
                "event_id": int(e.event_id),
                "event_time": e.event_time.isoformat(),
                "horizon": h,
                "return": ret,
                "status": "matured"
            })
    detail = pd.DataFrame(rows)
    if detail.empty:
        detail = pd.DataFrame(columns=["event_id","event_time","horizon","return","status"])
    detail.to_csv(RESULTS / "forward_shadow_returns.csv", index=False)

    print("forward_events", len(forward))
    print("matured_returns", len(detail))
    if not detail.empty:
        print(detail.groupby("horizon")["return"].agg(["count","mean","median"]).to_string())

if __name__ == "__main__":
    main()
