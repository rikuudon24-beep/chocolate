import json
from pathlib import Path
import pandas as pd
import numpy as np
from historical_deep_audit import fetch,features,extract

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; R.mkdir(exist_ok=True)
COST=.001; H=12
# Fixed pre-registered filters. Direction is defined before entry and selected only on training data.
FILTERS=[
 ("none",lambda q:True),
 ("rsi_ge30",lambda q:q.rsi_reentry>=30),
 ("bb_le012",lambda q:q.bb_width_reentry<=.12),
 ("atr_lt002",lambda q:q.atr_pct_reentry<.02),
 ("entry_vol_ge0",lambda q:q.entry_vol_z>=0),
 ("rsi_ge30_bb_le012",lambda q:q.rsi_reentry>=30 and q.bb_width_reentry<=.12),
 ("rsi_ge30_entry_vol_ge0",lambda q:q.rsi_reentry>=30 and q.entry_vol_z>=0),
 ("bb_le012_entry_vol_ge0",lambda q:q.bb_width_reentry<=.12 and q.entry_vol_z>=0),
 ("rsi_ge30_bb_le012_atr_lt002_entry_vol_ge0",lambda q:q.rsi_reentry>=30 and q.bb_width_reentry<=.12 and q.atr_pct_reentry<.02 and q.entry_vol_z>=0),
]

def add_features(x,e):
    c=x.close; v=x.volume
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    x["bbwidth"]=4*sd/mid
    tr=pd.concat([(x.high-x.low),(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1)
    x["atrpct"]=tr.ewm(alpha=1/14,adjust=False).mean()/c
    x["volz"]=(v-v.rolling(20).mean())/v.rolling(20).std(ddof=0)
    e=e.copy()
    e["rsi_reentry"]=x.iloc[e.reentry_idx].rsi.to_numpy()
    e["bb_width_reentry"]=x.iloc[e.reentry_idx].bbwidth.to_numpy()
    e["atr_pct_reentry"]=x.iloc[e.reentry_idx].atrpct.to_numpy()
    e["entry_vol_z"]=x.iloc[e.entry_idx].volz.to_numpy()
    return e

def ret12(x,q):
    p=int(q.entry_idx); j=p+H-1
    if j>=len(x):return np.nan
    return float(x.iloc[j].close/q.entry_price-1)-COST

def score(a):
    a=pd.Series(a).dropna()
    if len(a)<3:return (-999,-999,-999,len(a))
    loss=-a[a<0].sum(); pf=a[a>0].sum()/loss if loss>0 else np.inf
    return float(a.mean()),float(pf),float((a>0).mean()),len(a)

def main():
    x=features(fetch()); e=extract(x)
    if len(e)!=95:raise RuntimeError(f"event mismatch {len(e)}")
    e=add_features(x,e); e["year"]=pd.to_datetime(e.event_time).dt.year
    e=e[e.reentry_volz>=1].copy()
    if len(e)!=34:raise RuntimeError(f"anchor mismatch {len(e)}")
    splits=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
    rows=[]
    for a,b,vy in splits:
        tr=e[e.year.between(a,b)]; va=e[e.year==vy]
        cand=[]
        for name,fn in FILTERS:
            z=[ret12(x,q) for _,q in tr.iterrows() if fn(q)]
            av,pf,w,n=score(z); cand.append((av,pf,w,n,name))
        cand.sort(key=lambda z:(z[0],z[1],z[2],z[3]),reverse=True)
        av,pf,w,n,name=cand[0]
        vz=[ret12(x,q) for _,q in va.iterrows() if fn(q)] if False else [ret12(x,q) for _,q in va.iterrows() if dict(FILTERS)[name](q)]
        vav,vpf,vw,vn=score(vz)
        rows.append({"train":f"{a}-{b}","validation":vy,"selected":name,"train_n":n,"train_avg":av,"train_pf":pf,"train_win":w,
                     "validation_n":vn,"validation_avg":vav,"validation_pf":vpf,"validation_win":vw})
    pd.DataFrame(rows).to_csv(R/"volume_anchor_failure_filter_walkforward.csv",index=False)
    report={"anchor_events":34,"cost":COST,"horizon":H,"splits":rows,
            "selection":"Filter chosen using training years only.","warning":"Small validation samples; descriptive validation only."}
    (R/"volume_anchor_failure_filter_walkforward.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
