import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_deep_audit import fetch, features, extract

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; R.mkdir(exist_ok=True)
COST=0.001; HORIZONS=[2,3,6,12]
TPS=[.005,.01,.02,.03,.05]; SLS=[.005,.01,.02,.03,.05]

def outcome(x,p,tp,sl,h):
    ep=float(x.iloc[p].open); end=min(p+h-1,len(x)-1)
    for j in range(p,end+1):
        up=float(x.iloc[j].high/ep-1); dn=float(x.iloc[j].low/ep-1)
        ht=up>=tp; hs=dn<=-sl
        if ht and hs: return np.nan
        if ht: return tp-COST
        if hs: return -sl-COST
    return float(x.iloc[end].close/ep-1)-COST

def score(vals):
    a=pd.Series(vals).dropna()
    if len(a)<5:return (-999,-999,-999,len(a))
    loss=-a[a<0].sum(); pf=a[a>0].sum()/loss if loss>0 else np.inf
    return float(a.mean()),float(pf),float((a>0).mean()),len(a)

def main():
    x=features(fetch()); e=extract(x)
    if len(e)!=95: raise RuntimeError(f"canonical event mismatch: {len(e)}")
    e=e[e.reentry_volz>=1.0].copy()
    if len(e)!=34: raise RuntimeError(f"volume anchor mismatch: {len(e)}")
    e["year"]=pd.to_datetime(e.event_time).dt.year
    splits=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
    rows=[]
    for a,b,vy in splits:
        train=e[e.year.between(a,b)]; valid=e[e.year==vy]; cand=[]
        for tp in TPS:
            for sl in SLS:
                for h in HORIZONS:
                    vals=[outcome(x,int(q.entry_idx),tp,sl,h) for _,q in train.iterrows()]
                    av,pf,w,n=score(vals); cand.append((av,pf,w,tp,sl,h,n))
        cand.sort(key=lambda z:(z[0],z[1],z[2],-z[6]),reverse=True)
        av,pf,w,tp,sl,h,n=cand[0]
        vv=[outcome(x,int(q.entry_idx),tp,sl,h) for _,q in valid.iterrows()]
        va,vpf,vw,vn=score(vv)
        rows.append({"train":f"{a}-{b}","validation":vy,"train_n":n,"tp":tp,"sl":sl,"horizon":h,
                     "train_avg":av,"train_pf":pf,"train_win":w,"validation_n":vn,
                     "validation_avg":va,"validation_pf":vpf,"validation_win":vw})
    out=pd.DataFrame(rows); out.to_csv(R/"volume_anchor_exit_walkforward.csv",index=False)
    report={"anchor_events":34,"cost":COST,"splits":rows,
            "selection":"Training years only; validation year never used for selection.",
            "warning":"Small validation samples; not proof of future profitability."}
    (R/"volume_anchor_exit_walkforward.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
