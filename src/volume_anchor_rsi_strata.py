import json,time
from pathlib import Path
import pandas as pd,requests

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
events=pd.read_csv(R/"condition_search_events.csv",parse_dates=["event_time","entry_time"])
start=int(pd.Timestamp("2020-01-01",tz="UTC").timestamp()*1000)
end=int(pd.Timestamp("2026-09-27 20:00:00",tz="UTC").timestamp()*1000)
step=4*60*60*1000; rows=[]
while start<end:
    b=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":"BTCUSDT","interval":"4h","startTime":start,"endTime":end,"limit":1000},timeout=30).json()
    if not b: break
    rows.extend(b); start=int(b[-1][0])+step; time.sleep(.08)
    if len(b)<1000: break
m=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","qv","trades","tb","tq","ignore"])
m["open_time"]=pd.to_datetime(m["open_time"],unit="ms",utc=True); m["close"]=pd.to_numeric(m["close"],errors="coerce")
m=m.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
idx={t:i for i,t in enumerate(m.open_time)}
rr=[]
for _,e in events.iterrows():
    p=idx.get(pd.Timestamp(e.entry_time))
    if p is None: continue
    for h in (2,3,6,12):
        j=p+h-1
        if j<len(m): rr.append({"event_id":int(e.event_id),"horizon":h,"return":float(m.iloc[j].close)/float(e.entry_price)-1})
returns=pd.DataFrame(rr)
anchor=events.vol_z20_reentry>=1.0
events=events[anchor].copy()
# Fixed descriptive bins, defined before inspecting results.
bins=[-float("inf"),20,30,40,float("inf")]
labels=["RSI<20","RSI20-<30","RSI30-<40","RSI>=40"]
events["rsi_bin"]=pd.cut(events.rsi_reentry,bins=bins,labels=labels,right=False)
rows=[]
for label in labels:
    ids=set(events.loc[events.rsi_bin==label,"event_id"])
    for h in (2,3,6,12):
        x=returns[(returns.event_id.isin(ids))&(returns.horizon==h)].return
        if len(x):
            w=x[x>0]; l=x[x<0]; pf=float(w.sum()/(-l.sum())) if len(l) else float("inf")
            eq=(1+x).cumprod(); dd=float((eq/eq.cummax()-1).min())
            rows.append({"rsi_bin":label,"horizon":h,"n":int(len(x)),"avg":float(x.mean()),"net_avg_0.10pct":float(x.mean()-0.001),"win":float((x>0).mean()),"pf":pf,"dd":dd})
        else: rows.append({"rsi_bin":label,"horizon":h,"n":0})
summary={"anchor":"vol_z20_reentry >= 1.0","purpose":"Fixed RSI strata descriptive audit; bins pre-defined, no threshold selection or promotion.","rows":rows}
(R/"volume_anchor_rsi_strata.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2))