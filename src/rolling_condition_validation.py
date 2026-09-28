import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import time

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
# Build fixed-horizon event returns directly from Binance, matching the frozen event set.
rows=[]
start=int(pd.Timestamp("2020-01-01",tz="UTC").timestamp()*1000)
end=int(pd.Timestamp("2026-09-27 20:00:00",tz="UTC").timestamp()*1000)
step=4*60*60*1000
while start<end:
    q={"symbol":"BTCUSDT","interval":"4h","startTime":start,"endTime":end,"limit":1000}
    b=requests.get("https://data-api.binance.vision/api/v3/klines",params=q,timeout=30).json()
    if not b: break
    rows.extend(b); start=int(b[-1][0])+step
    time.sleep(.08)
    if len(b)<1000: break
m=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","qv","trades","tb","tq","ignore"])
m["open_time"]=pd.to_datetime(m["open_time"],unit="ms",utc=True)
m["close_time"]=pd.to_datetime(m["close_time"],unit="ms",utc=True)
m["close"]=pd.to_numeric(m["close"],errors="coerce")
m["open"]=pd.to_numeric(m["open"],errors="coerce")
m=m.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
idx={t:i for i,t in enumerate(m.open_time)}
rr=[]
for _,e in events.iterrows():
    p=idx.get(pd.Timestamp(e.entry_time))
    if p is None: continue
    for h in HORIZONS:
        j=p+h-1
        if j<len(m):
            rr.append({"event_id":int(e.event_id),"horizon":h,
                       "return":float(m.iloc[j].close)/float(e.entry_price)-1})
returns=pd.DataFrame(rr)

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
