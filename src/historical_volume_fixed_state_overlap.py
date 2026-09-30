import numpy as np,pandas as pd
from pathlib import Path
from historical_volume_path_timing import fetch,events,metrics,rma
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
def main():
 x=fetch(); e=events(x)
 if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
 x["vol_z20"]=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
 d=x.close.diff(); ag=rma(d.clip(lower=0)); al=rma(-d.clip(upper=0)); x["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
 x["bb_width"]=4*x.close.rolling(20).std(ddof=0)/x.close.rolling(20).mean()
 x["atr_pct"]=(x.high-x.low).rolling(14).mean()/x.close
 e=e.copy(); vt=dict(zip(x.open_time.astype(str),x.vol_z20)); e["group"]=np.where(e.event_time.astype(str).map(vt)>=1,"vol_z>=1","base")
 m=metrics(x,e,12)
 idx=dict(zip(x.open_time.astype(str),range(len(x)))); rows=[]
 for _,q in e.iterrows():
  i=idx[str(q.event_time)]; mm=m[m.event_id==q.event_id].iloc[0]
  p05=int(mm.first_plus_0_5_h); n05=int(mm.first_minus_0_5_h)
  if p05 and (not n05 or p05<n05): a="immediate_rebound"
  elif n05 and p05 and n05<p05: a="pullback_then_rebound"
  elif n05 and not p05: a="failure_after_adverse_move"
  else: a="no_0_5_hit"
  rows.append({"event_id":q.event_id,"group":q.group,"archetype":a,"rsi":x.iloc[i].rsi,"bb_width":x.iloc[i].bb_width,"atr_pct":x.iloc[i].atr_pct,"entry_vol_z":x.iloc[int(q.entry)].vol_z20})
 d=pd.DataFrame(rows); v=d[d.group=="vol_z>=1"].copy()
 states={
  "RSI_reentry>=30":v.rsi>=30,
  "BB_width<=0.12":v.bb_width<=0.12,
  "ATR_pct<0.02":v.atr_pct<0.02,
  "entry_vol_z>=0":v.entry_vol_z>=0,
  "all_4_fixed":(v.rsi>=30)&(v.bb_width<=0.12)&(v.atr_pct<0.02)&(v.entry_vol_z>=0)
 }
 out=[]
 year_rows=[]
 for name,mask in states.items():
  z=v[mask]; out.append({"state":name,"n":len(z),"immediate":int((z.archetype=="immediate_rebound").sum()),"pullback":int((z.archetype=="pullback_then_rebound").sum()),"no_hit":int((z.archetype=="no_0_5_hit").sum()),"failure":int((z.archetype=="failure_after_adverse_move").sum()),"immediate_rate":float((z.archetype=="immediate_rebound").mean()) if len(z) else np.nan})
 pd.DataFrame(out).to_csv(R/"historical_volume_fixed_state_overlap.csv",index=False)
 year_mask=(v.rsi>=30)&(v.bb_width<=0.12)&(v.atr_pct<0.02)&(v.entry_vol_z>=0)
 for y,g in v[year_mask].groupby(v.loc[year_mask,"event_id"].map(lambda z: int(d.loc[d.event_id==z,"event_id"].iloc[0])) if False else v.loc[year_mask].index.map(lambda idx: 0)):
  pass
 # Year distribution using the event timestamp year carried in d.
 vv=v[year_mask].copy()
 vv["year"]=d.loc[vv.index,"year"]
 print("=== FIXED 4-CONDITION YEAR DISTRIBUTION ===")
 print(vv.groupby("year").size().to_string())
 print(pd.DataFrame(out).to_string(index=False))
if __name__=="__main__": main()
