import numpy as np,pandas as pd
from pathlib import Path
from historical_volume_path_timing import fetch,events,rma
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
def main():
 x=fetch(); e=events(x)
 if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
 x["vol_z20"]=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
 d=x.close.diff(); ag=rma(d.clip(lower=0)); al=rma(-d.clip(upper=0)); x["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
 x["bb_width"]=4*x.close.rolling(20).std(ddof=0)/x.close.rolling(20).mean()
 x["atr_pct"]=(x.high-x.low).rolling(14).mean()/x.close
 e=e.copy(); vt=dict(zip(x.open_time.astype(str),x.vol_z20)); e["vol_z_reentry"]=e.event_time.astype(str).map(vt)
 idx=dict(zip(x.open_time.astype(str),range(len(x))))
 rows=[]
 for _,q in e.iterrows():
  i=idx[str(q.event_time)]; p=int(q.entry)
  if p+11>=len(x): continue
  cond=(e.loc[e.event_id==q.event_id,"vol_z_reentry"].iloc[0]>=1 and x.iloc[i].rsi>=30 and x.iloc[i].bb_width<=0.12 and x.iloc[i].atr_pct<0.02 and x.iloc[p].vol_z20>=0)
  ep=float(x.iloc[p].open); ret=float(x.iloc[p+11].close/ep-1)
  rows.append({"event_id":q.event_id,"year":q.event_time.year,"selected":bool(cond),"ret12":ret,"net12":ret-0.001})
 d=pd.DataFrame(rows)
 out=[]
 for y,g in d.groupby("year"):
  z=g[g.selected]
  wins=(z.net12>0).sum(); gains=z.loc[z.net12>0,"net12"].sum(); losses=-z.loc[z.net12<0,"net12"].sum()
  out.append({"year":int(y),"n_selected":len(z),"avg_net":z.net12.mean() if len(z) else np.nan,"win_rate":wins/len(z) if len(z) else np.nan,"profit_factor":gains/losses if losses>0 else np.nan})
 v=d[(d.year>=2023)&d.selected]
 gains=v.loc[v.net12>0,"net12"].sum(); losses=-v.loc[v.net12<0,"net12"].sum()
 out.append({"year":"2023-2026","n_selected":len(v),"avg_net":v.net12.mean(),"win_rate":(v.net12>0).mean(),"profit_factor":gains/losses if losses>0 else np.nan})
 pd.DataFrame(out).to_csv(R/"historical_volume_fixed_rule_validation.csv",index=False)
 print(pd.DataFrame(out).to_string(index=False))
if __name__=="__main__": main()
