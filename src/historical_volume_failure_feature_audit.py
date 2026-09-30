import numpy as np,pandas as pd
from pathlib import Path
from historical_volume_path_timing import fetch,events,metrics
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
def main():
 x=fetch(); e=events(x)
 if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
 x["vol_z20"]=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
 d=x.close.diff()
 # Reuse the same Wilder-style RSI implementation as the canonical timing module.
 from historical_volume_path_timing import rma
 ag=rma(d.clip(lower=0)); al=rma(-d.clip(upper=0)); x["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
 x["ret4"]=x.close.pct_change(4); x["ret12"]=x.close.pct_change(12); x["ret24"]=x.close.pct_change(24)
 x["bb_width"]=4*x.close.rolling(20).std(ddof=0)/x.close.rolling(20).mean()
 x["atr_pct"]=(x.high-x.low).rolling(14).mean()/x.close
 vol_by_time=dict(zip(x.open_time.astype(str),x.vol_z20))
 e=e.copy(); e["group"]=np.where(e.event_time.astype(str).map(vol_by_time)>=1.0,"vol_z>=1","base")
 # Canonical 12h path metrics from the timing audit.
 m=metrics(x,e,12)
 # The metrics function's event rows retain exact canonical event ids/group labels.
 rows=[]
 idx_by_time=dict(zip(x.open_time.astype(str),range(len(x))))
 for _,q in e.iterrows():
  i=idx_by_time[str(q.event_time)]; p=int(q.entry)
  mm=m[m.event_id==q.event_id].iloc[0]
  p05=int(mm.first_plus_0_5_h); n05=int(mm.first_minus_0_5_h)
  if p05 and (not n05 or p05<n05): arch="immediate_rebound"
  elif n05 and p05 and n05<p05: arch="pullback_then_rebound"
  elif n05 and not p05: arch="failure_after_adverse_move"
  else: arch="no_0_5_hit"
  rows.append({"event_id":q.event_id,"year":q.event_time.year,"group":q.group,"archetype":arch,
   "rsi_reentry":x.iloc[i].rsi,"vol_z_reentry":x.iloc[i].vol_z20,"ret4_reentry":x.iloc[i].ret4,
   "ret12_reentry":x.iloc[i].ret12,"ret24_reentry":x.iloc[i].ret24,"bb_width_reentry":x.iloc[i].bb_width,
   "atr_pct_reentry":x.iloc[i].atr_pct,"rsi_entry":x.iloc[p].rsi,"vol_z_entry":x.iloc[p].vol_z20,
   "confirm_delay_h":(p-i)*4})
 d=pd.DataFrame(rows)
 if len(d[d.group=="vol_z>=1"])!=34: raise RuntimeError("volume anchor mismatch")
 feats=["rsi_reentry","vol_z_reentry","ret4_reentry","ret12_reentry","ret24_reentry","bb_width_reentry","atr_pct_reentry","rsi_entry","vol_z_entry","confirm_delay_h"]
 out=[]
 for g,gp in d.groupby("group"):
  for a,ap in gp.groupby("archetype"):
   for f in feats:
    z=pd.to_numeric(ap[f],errors="coerce").dropna()
    out.append({"group":g,"archetype":a,"feature":f,"n":len(z),"mean":z.mean(),"median":z.median()})
 pd.DataFrame(out).to_csv(R/"historical_volume_failure_feature_audit.csv",index=False)
 print("=== COUNTS ==="); print(d.groupby(["group","archetype"]).size().to_string())
 print("=== VOLUME ANCHOR MEDIANS ==="); print(d[d.group=="vol_z>=1"].groupby("archetype")[feats].median().to_string())
 print("=== VOLUME ANCHOR MEANS ==="); print(d[d.group=="vol_z>=1"].groupby("archetype")[feats].mean().to_string())
if __name__=="__main__": main()
