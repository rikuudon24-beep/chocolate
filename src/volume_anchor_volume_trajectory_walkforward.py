import json
from pathlib import Path
import pandas as pd
import numpy as np
from historical_deep_audit import fetch,features,extract

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; R.mkdir(exist_ok=True)
COST=.001; H=12

def add_volume_path(x,e):
    e=e.copy()
    vals=[]
    for _,q in e.iterrows():
        ri=int(q.reentry_idx); ci=int(q.confirm_idx); ei=int(q.entry_idx)
        z=x.volz
        r=float(z.iloc[ri]); c=float(z.iloc[ci]); en=float(z.iloc[ei])
        path=z.iloc[ri:ei+1].to_numpy(float)
        vals.append({
            "reentry_vol_z":r,"confirm_vol_z":c,"entry_vol_z":en,
            "confirm_delta":c-r,"entry_delta":en-r,
            "min_path_vol_z":float(np.nanmin(path)),"max_path_vol_z":float(np.nanmax(path)),
            "entry_minus_confirm":en-c,
            "confirm_to_entry_slope":(en-c)/max(ei-ci,1),
        })
    return pd.concat([e.reset_index(drop=True),pd.DataFrame(vals)],axis=1)

def ret12(x,q):
    p=int(q.entry_idx); j=p+H-1
    if j>=len(x): return np.nan
    return float(x.iloc[j].close/q.entry_price-1)-COST

def score(a):
    a=pd.Series(a).dropna()
    if len(a)<3:return (-999,-999,-999,len(a))
    loss=-a[a<0].sum(); pf=a[a>0].sum()/loss if loss>0 else np.inf
    return float(a.mean()),float(pf),float((a>0).mean()),len(a)

# Fixed, pre-registered trajectory states. Each event receives exactly one class.
def classify(q):
    r,c,en=q.reentry_vol_z,q.confirm_vol_z,q.entry_vol_z
    if c>=r+0.5 and en>=c:
        return "keeps_increasing"
    if c<=r-0.5 and en>=c+0.5:
        return "re_increase_at_entry"
    if en<=r-1.0:
        return "sharp_decrease"
    if min(r,c,en)>=0:
        return "remains_elevated"
    return "other"

STATES=[
 ("keeps_increasing",lambda q:q.trajectory=="keeps_increasing"),
 ("remains_elevated",lambda q:q.trajectory=="remains_elevated"),
 ("sharp_decrease",lambda q:q.trajectory=="sharp_decrease"),
 ("re_increase_at_entry",lambda q:q.trajectory=="re_increase_at_entry"),
]

def main():
    x=features(fetch()); e=extract(x)
    if len(e)!=95: raise RuntimeError(f"event mismatch {len(e)}")
    e=add_volume_path(x,e)
    e["year"]=pd.to_datetime(e.event_time).dt.year
    e=e[e.reentry_vol_z>=1].copy()
    if len(e)!=34: raise RuntimeError(f"anchor mismatch {len(e)}")

    e=e.copy()
    e["trajectory"]=[classify(q) for _,q in e.iterrows()]
    e.to_csv(R/"volume_anchor_volume_trajectory_events.csv",index=False)

    # Descriptive all-sample state table.
    desc=[]
    for name,fn in STATES:
        z=e[e.apply(fn,axis=1)]
        for h in (2,3,6,12):
            vals=[ret12(x,q) if h==12 else (float(x.iloc[int(q.entry_idx)+h-1].close/q.entry_price-1)-COST if int(q.entry_idx)+h-1<len(x) else np.nan) for _,q in z.iterrows()]
            av,pf,w,n=score(vals)
            desc.append({"state":name,"horizon":h,"n":n,"net_avg":av,"pf":pf,"win":w})
    pd.DataFrame(desc).to_csv(R/"volume_anchor_volume_trajectory_descriptive.csv",index=False)

    # Walk-forward: choose one trajectory state on training years only, then evaluate next year.
    splits=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
    wf=[]
    for a,b,vy in splits:
        tr=e[e.year.between(a,b)]; va=e[e.year==vy]
        cand=[]
        for name,fn in STATES:
            z=[ret12(x,q) for _,q in tr.iterrows() if fn(q)]
            av,pf,w,n=score(z)
            cand.append((av if n>=3 else -np.inf,pf,w,n,name,av))
        cand.sort(key=lambda t:(t[0],t[1],t[2],t[3]),reverse=True)
        _,pf,w,n,name,av=cand[0]
        fn=dict(STATES)[name]
        vz=[ret12(x,q) for _,q in va.iterrows() if fn(q)]
        vav,vpf,vw,vn=score(vz)
        wf.append({"train":f"{a}-{b}","validation":vy,"selected":name,
                   "train_n":n,"train_avg":av,"train_pf":pf,"train_win":w,
                   "validation_n":vn,"validation_avg":vav,"validation_pf":vpf,"validation_win":vw})
    pd.DataFrame(wf).to_csv(R/"volume_anchor_volume_trajectory_walkforward.csv",index=False)
    report={"anchor_events":34,"cost":COST,"horizon":H,"states":[x[0] for x in STATES]+["other"],"state_counts":e.trajectory.value_counts().to_dict(),
            "walkforward":wf,"note":"Trajectory states are fixed before validation; selection uses training years only. Small validation samples remain descriptive."}
    (R/"volume_anchor_volume_trajectory_walkforward.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=="__main__": main()
