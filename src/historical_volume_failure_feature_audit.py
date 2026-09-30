import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
def fetch():
 rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
 while s<e:
  q=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30); q.raise_for_status(); b=q.json()
  if not b: break
  rows+=b; s=int(b[-1][0])+step; time.sleep(.03)
  if len(b)<1000: break
 c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"]
 d=pd.DataFrame(rows,columns=c); d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for z in ["open","high","low","close","volume"]: d[z]=pd.to_numeric(d[z],errors="coerce")
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
def rma(s,n=14):
 a=s.to_numpy(float); o=np.full(len(a),np.nan)
 if len(a)<n:return pd.Series(o,index=s.index)
 o[n-1]=np.nanmean(a[:n]); k=1/n
 for i in range(n,len(a)): o[i]=(1-k)*o[i-1]+k*o[i]
 return pd.Series(o,index=s.index)
def events(x):
 c=x.close; mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0); lo=mid-2*sd; d=c.diff(); ag=rma(d.clip(lower=0)); al=rma(-d.clip(upper=0)); r=100-100/(1+ag/al.replace(0,np.nan))
 x=x.copy(); x["lo"]=lo; x["rsi"]=r
 ev=[]; cons=-1; i=20
 while i<len(x)-1:
  p,q=x.iloc[i-1],x.iloc[i]
  if not(i>cons and p.close<p.lo and q.close>=q.lo and q.rsi<40): i+=1; continue
  low=float(q.low); mn=float(q.rsi); conf=None; fail=False; end=min(i+6,len(x)-2)
  for j in range(i+1,end+1):
   z=x.iloc[j]; mn=min(mn,float(z.rsi))
   if z.low<low or z.close<x.iloc[j].lo: fail=True; break
   if z.rsi>=mn+5: conf=j; break
  if not fail and conf is not None and conf+1<len(x):
   ev.append({"event_id":len(ev)+1,"reentry":i,"entry":conf+1,"event_time":q.open_time,"confirm_delay_h":(conf-i+1)*4})
   cons=conf+1; i=conf+2; continue
  cons=max(cons,end); i+=1
 return pd.DataFrame(ev)
def main():
 x=fetch(); e=events(x)
 if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
 x["vol_z20"]=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
 x["ret4"]=x.close.pct_change(4); x["ret12"]=x.close.pct_change(12); x["ret24"]=x.close.pct_change(24)
 x["bb_width"]=4*x.close.rolling(20).std(ddof=0)/x.close.rolling(20).mean()
 x["atr14"]=(x.high-x.low).rolling(14).mean()/x.close
 # Fixed descriptive features known by re-entry / entry; labels use post-entry 12h path only.
 rows=[]
 for _,q in e.iterrows():
  i=int(q.reentry); p=int(q.entry); ep=float(x.iloc[p].open); w=x.iloc[p:p+12]
  hi=(w.high.to_numpy()/ep)-1; lo=(w.low.to_numpy()/ep)-1
  p05=np.where(hi>=.005)[0]; n05=np.where(lo<=-.005)[0]
  ph=int(p05[0]) if len(p05) else 999; nh=int(n05[0]) if len(n05) else 999
  if ph<nh: arch="immediate_rebound"
  elif nh<999 and ph<999: arch="pullback_then_rebound"
  elif nh<999 and ph==999: arch="failure_after_adverse_move"
  else: arch="no_0_5_hit"
  rows.append({"event_id":q.event_id,"year":q.event_time.year,"group":"vol_z>=1" if x.iloc[i].vol_z20>=1 else "base","archetype":arch,
   "rsi_reentry":x.iloc[i].rsi,"vol_z_reentry":x.iloc[i].vol_z20,"ret4_reentry":x.iloc[i].ret4,"ret12_reentry":x.iloc[i].ret12,"ret24_reentry":x.iloc[i].ret24,
   "bb_width_reentry":x.iloc[i].bb_width,"atr_pct_reentry":x.iloc[i].atr14,"rsi_entry":x.iloc[p].rsi,"vol_z_entry":x.iloc[p].vol_z20,
   "confirm_delay_h":q.confirm_delay_h})
 d=pd.DataFrame(rows)
 feats=[c for c in d.columns if c not in ["event_id","year","group","archetype"]]
 out=[]
 for g,gp in d.groupby("group"):
  for a,ap in gp.groupby("archetype"):
   for f in feats:
    z=pd.to_numeric(ap[f],errors="coerce").dropna()
    out.append({"group":g,"archetype":a,"feature":f,"n":len(z),"mean":z.mean(),"median":z.median()})
 pd.DataFrame(out).to_csv(R/"historical_volume_failure_feature_audit.csv",index=False)
 print("=== COUNTS ==="); print(d.groupby(["group","archetype"]).size().to_string())
 print("=== VOLUME ANCHOR FEATURE MEDIANS ==="); print(d[d.group=="vol_z>=1"].groupby("archetype")[feats].median().to_string())
 print("=== VOLUME ANCHOR FEATURE MEANS ==="); print(d[d.group=="vol_z>=1"].groupby("archetype")[feats].mean().to_string())
if __name__=="__main__": main()
