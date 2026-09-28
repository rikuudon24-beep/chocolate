import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/"results"
COST=0.001
MIN_TRAIN=15
HORIZONS=(2,3,6,12)

events=pd.read_csv(R/"condition_search_events.csv",parse_dates=["event_time","confirmation_time","entry_time"])
ret=pd.read_csv(R/"condition_search_results.csv") if False else None

# Reconstruct event returns from the frozen audit return files where available.
# Use the existing audited event set and market-independent return table.
audit= pd.read_csv(R/"oos_events.csv",parse_dates=["event_time","entry_time"])
# condition_search_events has the same event_id ordering as the audited 95 events.
# exit research contains the fixed-time returns in dedicated files; discover them by
# reading the repository result if present.
exit_path=R/"oos_exit_returns.csv"
if not exit_path.exists():
    # fall back to condition_search_results only for candidate ranking is unsafe;
    # therefore require the dedicated return table rather than inventing values.
    raise RuntimeError("Missing oos_exit_returns.csv; rolling condition selection requires event-level audited returns.")

returns=pd.read_csv(exit_path)
returns["event_id"]=returns["event_id"].astype(int)
returns["event_time"]=pd.to_datetime(returns["event_time"],utc=True)

features=[
 "rsi_reentry","rsi_min","rsi_confirm","bb_z_reentry","bb_width_reentry",
 "atr_pct_reentry","ret4_reentry","ret12_reentry","ret24_reentry","vol_z20_reentry",
 "bb_z_entry","bb_width_entry","atr_pct_entry","ret4_entry","ret12_entry",
 "ret24_entry","vol_z20_entry"
]
grid={
 "rsi_reentry":[20,25,30,35,38],
 "rsi_min":[20,25,30,35],
 "rsi_confirm":[25,30,35,40,45],
 "bb_z_reentry":[-3,-2.5,-2.2,-2,-1.8],
 "bb_width_reentry":[.02,.03,.05,.08,.12],
 "atr_pct_reentry":[.01,.02,.03,.05,.08],
 "ret4_reentry":[-.08,-.05,-.03,-.01,0],
 "ret12_reentry":[-.12,-.08,-.05,-.02,0],
 "ret24_reentry":[-.20,-.12,-.08,-.04,0],
 "vol_z20_reentry":[-1,0,1,2,3],
 "bb_z_entry":[-2.5,-2.2,-2,-1.8,-1.5],
 "bb_width_entry":[.02,.03,.05,.08,.12],
 "atr_pct_entry":[.01,.02,.03,.05,.08],
 "ret4_entry":[-.08,-.05,-.03,-.01,0],
 "ret12_entry":[-.12,-.08,-.05,-.02,0],
 "ret24_entry":[-.20,-.12,-.08,-.04,0],
 "vol_z20_entry":[-1,0,1,2,3]
}
def op(f):
    return "<=" if f.startswith(("rsi_","bb_z_","ret")) else ">="
def mask(df,f,o,t):
    s=pd.to_numeric(df[f],errors="coerce")
    return s<=t if o=="<=" else s>=t
def metric(x):
    x=pd.Series(x,dtype=float)
    if len(x)==0:return (0,np.nan,np.nan,np.nan,np.nan)
    w=x[x>0];l=x[x<0]
    pf=w.sum()/(-l.sum()) if len(l) else np.inf
    eq=(1+x).cumprod();dd=(eq/eq.cummax()-1).min()
    return len(x),x.mean(),(x>0).mean(),pf, x.mean()-COST

events["event_time"]=pd.to_datetime(events["event_time"],utc=True)
# Need event-level returns; normalize.
returns["horizon"]=returns["horizon"].astype(int)

splits=[
 ("2020-2022","2023-2023",pd.Timestamp("2023-01-01",tz="UTC"),pd.Timestamp("2024-01-01",tz="UTC")),
 ("2020-2023","2024-2024",pd.Timestamp("2024-01-01",tz="UTC"),pd.Timestamp("2025-01-01",tz="UTC")),
 ("2020-2024","2025-2025",pd.Timestamp("2025-01-01",tz="UTC"),pd.Timestamp("2026-01-01",tz="UTC")),
 ("2020-2025","2026-2026",pd.Timestamp("2026-01-01",tz="UTC"),pd.Timestamp("2027-01-01",tz="UTC")),
]
rows=[]
selected=[]
for train_name,val_name,val_start,val_end in splits:
    train=events[events.event_time<val_start]
    val=events[(events.event_time>=val_start)&(events.event_time<val_end)]
    candidates=[]
    for f in features:
        for t in grid[f]:
            ids=train.loc[mask(train,f,op(f),t),"event_id"]
            rr=returns[(returns.event_id.isin(ids))&(returns.horizon==2)]
            n,avg,win,pf,net=metric(rr["return"])
            if n<MIN_TRAIN:continue
            score=net+0.0015*(win-.5)-0.0005*abs(min(dd if False else 0,0))
            candidates.append((score,f,op(f),t,n,avg,win,pf,net))
    candidates.sort(reverse=True)
    for rank,c in enumerate(candidates[:5],1):
        _,f,o,t,tn,ta,tw,tp,tnet=c
        ids=val.loc[mask(val,f,o,t),"event_id"]
        for h in HORIZONS:
            rr=returns[(returns.event_id.isin(ids))&(returns.horizon==h)]
            n,a,w,p,net=metric(rr["return"])
            rows.append({"split":train_name+" -> "+val_name,"rank":rank,"feature":f,"op":o,"threshold":t,
                         "train_n":tn,"train_net_avg":tnet,"period":"validation","horizon":h,
                         "n":n,"avg":a,"win":w,"pf":p,"net_avg":net})
        selected.append({"split":train_name+" -> "+val_name,"rank":rank,"feature":f,"op":o,"threshold":t,
                         "train_n":tn,"train_net_avg":tnet})
out=pd.DataFrame(rows)
sel=pd.DataFrame(selected)
out.to_csv(R/"rolling_condition_validation.csv",index=False)
sel.to_csv(R/"rolling_condition_selected.csv",index=False)
summary={
 "cost":COST,"min_train":MIN_TRAIN,
 "splits":[x[0]+" -> "+x[1] for x in splits],
 "note":"Condition thresholds are selected inside each training window only; validation is untouched. No automatic promotion.",
 "selection":sel.to_dict("records")
}
(R/"rolling_condition_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
print(out.sort_values(["split","horizon","net_avg"],ascending=[True,True,False]).head(40).to_string(index=False))
