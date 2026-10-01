import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_deep_audit import fetch, features, extract

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; R.mkdir(exist_ok=True)
COST=.001
# Fixed, pre-registered risk structures. Selection is training-only.
STRUCTURES=[(.01,.03,12),(.02,.03,12),(.03,.03,12),(.05,.03,12),
            (.01,.05,12),(.02,.05,12),(.03,.05,12),(.05,.05,12)]

def simulate(x,p,tp,sl,h):
    ep=float(x.iloc[p].open); end=min(p+h-1,len(x)-1)
    mae=0.0
    for j in range(p,end+1):
        up=float(x.iloc[j].high/ep-1); dn=float(x.iloc[j].low/ep-1)
        mae=min(mae,dn)
        ht=up>=tp; hs=dn<=-sl
        if ht and hs:return np.nan,mae,"ambiguous"
        if ht:return tp-COST,mae,"tp"
        if hs:return -sl-COST,mae,"sl"
    return float(x.iloc[end].close/ep-1)-COST,mae,"time"

def score(v):
    a=pd.Series([z[0] for z in v]).dropna()
    if len(a)<5:return (-999,-999,-999,len(a))
    loss=-a[a<0].sum(); pf=a[a>0].sum()/loss if loss>0 else np.inf
    return float(a.mean()),float(pf),float((a>0).mean()),len(a)

def main():
    x=features(fetch()); e=extract(x)
    if len(e)!=95:raise RuntimeError(f"canonical event mismatch {len(e)}")
    e=e[e.reentry_volz>=1].copy()
    if len(e)!=34:raise RuntimeError(f"anchor mismatch {len(e)}")
    e["year"]=pd.to_datetime(e.event_time).dt.year
    splits=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
    rows=[]; path=[]
    for a,b,vy in splits:
        tr=e[e.year.between(a,b)]; va=e[e.year==vy]; cand=[]
        for tp,sl,h in STRUCTURES:
            z=[simulate(x,int(q.entry_idx),tp,sl,h) for _,q in tr.iterrows()]
            av,pf,w,n=score(z); cand.append((av,pf,w,tp,sl,h,n))
        cand.sort(key=lambda z:(z[0],z[1],z[2],-z[6]),reverse=True)
        av,pf,w,tp,sl,h,n=cand[0]
        vz=[simulate(x,int(q.entry_idx),tp,sl,h) for _,q in va.iterrows()]
        vav,vpf,vw,vn=score(vz)
        rows.append({"train":f"{a}-{b}","validation":vy,"train_n":n,"tp":tp,"sl":sl,"horizon":h,
                     "train_avg":av,"train_pf":pf,"train_win":w,"validation_n":vn,
                     "validation_avg":vav,"validation_pf":vpf,"validation_win":vw})
        for _,q in va.iterrows():
            ret,mae,out=simulate(x,int(q.entry_idx),tp,sl,h)
            path.append({"validation":vy,"event_id":int(q.event_id),"mae":mae,"outcome":out,"return":ret})
    pd.DataFrame(rows).to_csv(R/"volume_anchor_adverse_walkforward.csv",index=False)
    pd.DataFrame(path).to_csv(R/"volume_anchor_adverse_paths.csv",index=False)
    report={"anchor_events":34,"cost":COST,"splits":rows,
            "selection":"Training years only; validation untouched.",
            "warning":"Small validation samples; MAE is descriptive and cannot establish a causal stop level."}
    (R/"volume_anchor_adverse_walkforward.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
