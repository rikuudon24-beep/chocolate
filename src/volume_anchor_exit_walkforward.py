import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/"results"; RESULTS.mkdir(exist_ok=True)
DATA=RESULTS/"historical_volume_context_events.csv"
# Fixed candidate: canonical 95-event entry, volume shock at re-entry >= 1.0.
# Exit candidates are pre-registered and selected only on the training years.
# Returns are close-to-close from entry open; target/stop path uses entry-open OHLC.
COST=0.001
HORIZONS=[2,3,6,12]
TPS=[0.005,0.01,0.02,0.03,0.05]
SLS=[0.005,0.01,0.02,0.03,0.05]

def load_events():
    p=DATA
    if not p.exists(): raise FileNotFoundError(p)
    df=pd.read_csv(p)
    # This file may contain path fields; require the canonical anchor and entry fields.
    needed={"year","entry_price"}
    if not needed.issubset(df.columns):
        raise RuntimeError(f"Missing columns: {sorted(needed-set(df.columns))}")
    return df

def path_return(row,tp,sl,h):
    # Prefer precomputed OHLC path columns when present.
    entry=float(row.entry_price)
    for k in range(1,h+1):
        hi=row.get(f"high_{k}h",np.nan); lo=row.get(f"low_{k}h",np.nan)
        if pd.isna(hi) or pd.isna(lo):
            return np.nan
        up=(float(hi)/entry-1)>=tp
        dn=(float(lo)/entry-1)<=-sl
        if up and dn:
            return np.nan # ambiguous intrabar ordering
        if up: return tp-COST
        if dn: return -sl-COST
    c=row.get(f"close_{h}h",np.nan)
    if pd.isna(c): return np.nan
    return float(c)/entry-1-COST

def score(v):
    v=pd.Series(v).dropna()
    if len(v)<5:return (-999,-999,-999)
    avg=float(v.mean()); wins=(v>0).sum(); loss=(-v[v<0]).sum()
    pf=float(v[v>0].sum()/loss) if loss>0 else 999
    return (avg,pf,wins/len(v))

def main():
    df=load_events()
    if "reentry_vol_z" not in df:
        raise RuntimeError("reentry_vol_z missing")
    anchor=df[df.reentry_vol_z>=1.0].copy()
    if len(anchor)<10: raise RuntimeError("too few anchor events")
    # Require path columns; this prevents silently substituting lookahead-unsafe data.
    req=[f"{p}_{k}h" for p in ["high","low","close"] for k in HORIZONS]
    if not set(req).issubset(anchor.columns):
        raise RuntimeError("Path columns absent; refusing unsafe fallback")

    splits=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
    rows=[]; picks=[]
    for a,b,vyear in splits:
        train=anchor[(anchor.year>=a)&(anchor.year<=b)]
        valid=anchor[anchor.year==vyear]
        candidates=[]
        for tp in TPS:
            for sl in SLS:
                for h in HORIZONS:
                    vals=[path_return(r,tp,sl,h) for _,r in train.iterrows()]
                    avg,pf,win=score(vals)
                    candidates.append((avg,pf,win,tp,sl,h,len(pd.Series(vals).dropna())))
        # deterministic training-only ranking: avg first, PF second, win third; no validation peeking.
        candidates.sort(reverse=True)
        best=candidates[0]
        avg,pf,win,tp,sl,h,n=best
        vv=[path_return(r,tp,sl,h) for _,r in valid.iterrows()]
        va,vpf,vwin=score(vv)
        rows.append({"train":f"{a}-{b}","validation":vyear,"train_n":n,"tp":tp,"sl":sl,"horizon":h,
                     "train_avg":avg,"train_pf":pf,"train_win":win,"validation_n":len(pd.Series(vv).dropna()),
                     "validation_avg":va,"validation_pf":vpf,"validation_win":vwin})
        picks.append(rows[-1])
    out=pd.DataFrame(rows); out.to_csv(RESULTS/"volume_anchor_exit_walkforward.csv",index=False)
    report={"anchor_events":int(len(anchor)),"cost":COST,"splits":picks,
            "warning":"Exit selected using training years only; validation is untouched for each split. Tiny validation samples remain a limitation."}
    (RESULTS/"volume_anchor_exit_walkforward.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__": main()
