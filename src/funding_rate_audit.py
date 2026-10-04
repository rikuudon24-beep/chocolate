import pandas as pd, requests, time
from pathlib import Path
from datetime import datetime, timezone

R=Path(__file__).resolve().parents[1]/"results"
H=[2,3,6,12]
BASE="https://fapi.binance.com/fapi/v1/fundingRate"

events=pd.read_csv(R/"taker_buy_ratio_events.csv")[["event_id","reentry_time"]+[f"net_{h}h" for h in H]]
events["reentry_time"]=pd.to_datetime(events["reentry_time"],utc=True)
rows=[]
for _,e in events.iterrows():
    ts=int(e.reentry_time.timestamp()*1000)
    end=ts+8*60*60*1000
    try:
        r=requests.get(BASE,params={"symbol":"BTCUSDT","startTime":ts-24*60*60*1000,"endTime":end,"limit":1000},timeout=20)
        r.raise_for_status()
        data=r.json()
    except Exception as ex:
        raise RuntimeError(f"funding fetch failed event={e.event_id}: {ex}")
    if not data:
        rows.append({"event_id":e.event_id,"funding":float("nan"),"funding_prev":float("nan")})
        continue
    f=pd.DataFrame(data)
    f["fundingTime"]=pd.to_datetime(f["fundingTime"],unit="ms",utc=True)
    f["fundingRate"]=f["fundingRate"].astype(float)
    before=f[f.fundingTime<=e.reentry_time]
    current=before.iloc[-1] if len(before) else f.iloc[0]
    prev=before.iloc[-2] if len(before)>=2 else None
    rows.append({
        "event_id":e.event_id,
        "funding":float(current.fundingRate),
        "funding_prev":float(prev.fundingRate) if prev is not None else float("nan")
    })
    time.sleep(0.05)

f=pd.DataFrame(rows)
x=events.merge(f,on="event_id",how="left")
if len(x)!=95: raise RuntimeError(f"merge={len(x)}")

# Fixed semantic states, registered before outcome inspection.
x["state"]=x.funding.map(lambda v:"positive" if v>=0.0001 else ("negative" if v<=-0.0001 else "neutral"))
x["easing"]=((x.funding-x.funding_prev)<=-0.0001)
x["tightening"]=((x.funding-x.funding_prev)>=0.0001)

rows=[]
for name,m in {
    "positive":x.state.eq("positive"),
    "negative":x.state.eq("negative"),
    "neutral":x.state.eq("neutral"),
    "easing":x.easing,
    "tightening":x.tightening,
}.items():
    g=x[m]
    row={"condition":name,"n":len(g)}
    for h in H: row[f"avg_{h}h"]=g[f"net_{h}h"].mean()
    rows.append(row)
summary=pd.DataFrame(rows)
summary.to_csv(R/"funding_rate_audit_summary.csv",index=False)
x.to_csv(R/"funding_rate_events.csv",index=False)

wf=[]
for y in [2023,2024,2025,2026]:
    g=x[x.reentry_time.dt.year.eq(y)]
    for name,m in {
        "positive":g.state.eq("positive"),
        "negative":g.state.eq("negative"),
        "easing":g.easing,
        "tightening":g.tightening,
    }.items():
        z=g[m]
        row={"year":y,"condition":name,"n":len(z)}
        for h in H: row[f"avg_{h}h"]=z[f"net_{h}h"].mean()
        wf.append(row)
pd.DataFrame(wf).to_csv(R/"funding_rate_audit_oos.csv",index=False)

print(summary.to_string(index=False))
print("\nOOS\n",pd.DataFrame(wf).to_string(index=False))
