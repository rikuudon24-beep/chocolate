import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

def atr_wilder(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def main():
    df = fetch_klines()
    df = add_indicators(df)
    df["atr14"] = atr_wilder(df)
    events = extract_events(df)
    rows = []
    for _, e in events.iterrows():
        entry_time = pd.Timestamp(e["entry_time"])
        idx = df.index[df["open_time"] == entry_time]
        if len(idx) == 0:
            continue
        i = int(idx[0])
        entry = float(e["entry_price"])
        confirmation = pd.Timestamp(e["confirmation_time"])
        reentry = pd.Timestamp(e["reentry_time"])
        delay_h = (confirmation - reentry).total_seconds()/3600
        atr = float(df.iloc[i]["atr14"])
        for h in [2,3,6,12]:
            end = min(i+h, len(df)-1)
            path = df.iloc[i:end+1]
            mfe = float(path["high"].max()/entry - 1)
            mae = float(path["low"].min()/entry - 1)
            close_ret = float(df.iloc[end]["close"]/entry - 1)
            rows.append({
                "event_id": int(e["event_id"]),
                "year": int(entry_time.year),
                "confirmation_delay_h": delay_h,
                "entry_atr_pct": atr/entry if atr and np.isfinite(atr) else np.nan,
                "horizon": h,
                "mfe": mfe, "mae": mae, "close_ret": close_ret,
                "mfe_atr": mfe/(atr/entry) if atr and np.isfinite(atr) and atr>0 else np.nan,
                "mae_atr": mae/(atr/entry) if atr and np.isfinite(atr) and atr>0 else np.nan,
            })
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS/"historical_normalized_paths.csv", index=False)
    bins = []
    delay_bins = [(0,4),(4,8),(8,25)]
    for lo,hi in delay_bins:
        sub=out[(out.confirmation_delay_h>=lo)&(out.confirmation_delay_h<hi)]
        for h in [2,3,6,12]:
            x=sub[sub.horizon==h]
            if len(x): bins.append({"dimension":"delay_h","bin":f"{lo}~<{hi}","horizon":h,"n":len(x),"avg_ret":x.close_ret.mean(),"win":(x.close_ret>0).mean(),"median_mfe_atr":x.mfe_atr.median(),"median_mae_atr":x.mae_atr.median()})
    for lo,hi,label in [(0,0.01,"ATR<1%"),(0.01,0.02,"ATR1~2%"),(0.02,0.04,"ATR2~4%"),(0.04,99,"ATR>=4%")]:
        sub=out[(out.entry_atr_pct>=lo)&(out.entry_atr_pct<hi)]
        for h in [2,3,6,12]:
            x=sub[sub.horizon==h]
            if len(x): bins.append({"dimension":"entry_atr_pct","bin":label,"horizon":h,"n":len(x),"avg_ret":x.close_ret.mean(),"win":(x.close_ret>0).mean(),"median_mfe_atr":x.mfe_atr.median(),"median_mae_atr":x.mae_atr.median()})
    pd.DataFrame(bins).to_csv(RESULTS/"historical_normalized_bins.csv", index=False)
    dist=[]
    for h in [2,3,6,12]:
        x=out[out.horizon==h].close_ret.dropna()
        q=x.quantile([0.05,0.10,0.25,0.5,0.75,0.90,0.95])
        dist.append({"horizon":h,"n":len(x),"mean":x.mean(),"median":x.median(),"std":x.std(ddof=1),"q05":q.loc[.05],"q10":q.loc[.10],"q25":q.loc[.25],"q75":q.loc[.75],"q90":q.loc[.90],"q95":q.loc[.95],"skew":x.skew()})
    pd.DataFrame(dist).to_csv(RESULTS/"historical_return_distribution.csv", index=False)
    summary={"events":int(len(events)),"purpose":"Historical-only descriptive audit of confirmation delay and ATR-normalized path structure; fixed bins only; no parameter promotion.","lookahead":"All normalization inputs are known at or before entry; path statistics start at entry open."}
    (RESULTS/"historical_normalized_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("=== NORMALIZED SUMMARY ===")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print("=== BINS ===")
    print(pd.DataFrame(bins).to_csv(index=False))
    print("=== DISTRIBUTION ===")
    print(pd.DataFrame(dist).to_csv(index=False))

if __name__=="__main__":
    main()
