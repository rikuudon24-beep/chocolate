import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests
from audit_oos import add_indicators,extract_events

START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
URL="https://data-api.binance.vision/api/v3/klines"; COST=.001; H=(2,3,6,12); SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
R=Path(__file__).resolve().parents[1]/"results"

def fetch():
 rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
 while s<e:
  b=requests.get(URL,params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30).json()
  if not b: break
  rows+=b;s=int(b[-1][0])+step;time.sleep(.05)
  if len(b)<1000: break
 c=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
 d=pd.DataFrame(rows,columns=c);d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for x in c[1:6]+c[7:11]: d[x]=pd.to_numeric(d[x],errors="coerce")
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def main():
 x=fetch(); ev=extract_events(add_indicators(x)); idx={t:i for i,t in enumerate(x.open_time)}
 rows=[]
 for _,e in ev.iterrows():
  i=idx[pd.Timestamp(e.reentry_time)]
  br=float(x.taker_base_volume.iloc[i]/x.volume.iloc[i]) if x.volume.iloc[i]>0 else np.nan
  prev=float(x.taker_base_volume.iloc[i-3:i].sum()/x.volume.iloc[i-3:i].sum()) if x.volume.iloc[i-3:i].sum()>0 else np.nan
  delta=br-prev
  anchor=float((x.volume.iloc[i]-x.volume.iloc[i-20:i].mean())/x.volume.iloc[i-20:i].std(ddof=0))>=1
  # fixed semantic states, no optimization
  state="buy" if br>=.55 else ("sell" if br<=.45 else "neutral")
  dstate="improving" if delta>=.05 else ("deteriorating" if delta<=-.05 else "flat")
  entry=idx[pd.Timestamp(e.entry_time)]
  r={"event_id":int(e.event_id),"year":int(pd.Timestamp(e.event_time).year),"buy_ratio":br,"delta3":delta,"state":state,"delta_state":dstate,"anchor":anchor}
  for h in H:
   j=entry+h
   r[f"net_{h}h"]=float(x.open.iloc[j]/x.open.iloc[entry]-1-COST) if j<len(x) else np.nan
  rows.append(r)
 e=pd.DataFrame(rows)
 if len(e)!=95: raise RuntimeError(f"expected 95, got {len(e)}")
 e.to_csv(R/"taker_buy_ratio_events.csv",index=False)
 def summ(g):
  z={"n":len(g)}
  for h in H:
   v=g[f"net_{h}h"].dropna();z[f"avg_{h}h"]=v.mean() if len(v) else np.nan
  return z
 out=[]
 for key,g in e.groupby(["state","delta_state"],observed=True): out.append({"state":key[0],"delta_state":key[1],**summ(g)})
 pd.DataFrame(out).to_csv(R/"taker_buy_ratio_states.csv",index=False)
 combos=[]
 for target_name,mask in {
  "buy":e.state.eq("buy"),"improving":e.delta_state.eq("improving"),
  "buy_or_improving":e.state.eq("buy")|e.delta_state.eq("improving"),
  "buy_and_improving":e.state.eq("buy")&e.delta_state.eq("improving"),
  "anchor_and_buy":e.anchor&e.state.eq("buy"),
  "anchor_and_improving":e.anchor&e.delta_state.eq("improving"),
 }.items():
  g=e[mask];combos.append({"condition":target_name,**summ(g)})
 pd.DataFrame(combos).to_csv(R/"taker_buy_ratio_conditions.csv",index=False)
 # Same-event matched residual vs volume anchor and BB decomposition target.
 for name, strata in {"year_anchor":["year","anchor"],"year_target":["year",(e.buy_ratio.between(.45,.55))]}.items():
  pass
 # explicit matched controls: buy state vs non-buy within year+volume anchor
 ms=[]
 e["bb_target"]=False
 # recompute structural target from prior saved event file if available
 try:
  bb=pd.read_csv(R/"bb_decomposition_redundancy_events.csv")
  e=e.merge(bb[["event_id","target"]],on="event_id",how="left");e["bb_target"]=e.target.fillna(False)
 except Exception: e["bb_target"]=False
 for strata in [["year","anchor"],["year","anchor","bb_target"]]:
  parts=[]
  for keys,g in e.groupby(strata,observed=True):
   if not isinstance(keys,tuple): keys=(keys,)
   t=g[g.state=="buy"];c=g[g.state!="buy"]
   if len(t)==0 or len(c)==0: continue
   row={k:v for k,v in zip(strata,keys)};row["target_n"]=len(t);row["control_n"]=len(c)
   for h in H: row[f"diff_{h}h"]=t[f"net_{h}h"].mean()-c[f"net_{h}h"].mean()
   parts.append(row)
  pd.DataFrame(parts).to_csv(R/f"taker_buy_matched_{'_'.join(strata)}.csv",index=False)
 # OOS fixed condition coverage, no training selection.
 wf=[]
 for a,b,y in SPLITS:
  va=e[e.year==y]
  for cond,mask in {"buy":va.state=="buy","improving":va.delta_state=="improving","anchor_buy":va.anchor&(va.state=="buy"),"anchor_improving":va.anchor&(va.delta_state=="improving")}.items():
   g=va[mask];wf.append({"train":f"{a}-{b}","year":y,"condition":cond,**summ(g)})
 pd.DataFrame(wf).to_csv(R/"taker_buy_ratio_oos.csv",index=False)
 (R/"taker_buy_ratio_audit.json").write_text(json.dumps({"events":95,"cost":COST,"definition":"Taker buy base volume / total volume at re-entry; buy >=55%, sell <=45%; delta3 compares re-entry ratio with preceding 3-candle aggregate; improving >=+5pp.","status":"research_only","no_threshold_search":True},ensure_ascii=False,indent=2))
 print(pd.DataFrame(out).to_string(index=False));print("\nconditions\n",pd.DataFrame(combos).to_string(index=False));print("\nOOS\n",pd.DataFrame(wf).to_string(index=False))
main()
