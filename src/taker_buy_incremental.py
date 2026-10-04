import pandas as pd,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]/"results"
H=[2,3,6,12]
t=pd.read_csv(R/"taker_buy_ratio_events.csv")
b=pd.read_csv(R/"bb_decomposition_redundancy_events.csv")[["event_id","target","anchor"]]
x=t.merge(b,on="event_id",how="inner")
if len(x)!=95: raise RuntimeError(f"merge={len(x)}")
x["improving"]=x.delta_state.eq("improving")
x["bb_target"]=x.target.astype(bool)
conds={
"improving":x.improving,
"anchor":x.anchor_y.astype(bool),
"bb_target":x.bb_target,
"anchor_and_improving":x.anchor_y.astype(bool)&x.improving,
"bb_and_improving":x.bb_target&x.improving,
"bb_anchor":x.bb_target&x.anchor_y.astype(bool),
"bb_anchor_improving":x.bb_target&x.anchor_y.astype(bool)&x.improving,
}
rows=[]
for name,m in conds.items():
 g=x[m];r={"condition":name,"n":len(g)}
 for h in H:r[f"avg_{h}h"]=g[f"net_{h}h"].mean()
 rows.append(r)
# fixed incremental comparison: improving vs non-improving inside year x anchor, and year x bb_target x anchor
for label,strata in [("year_anchor",["year","anchor_y"]),("year_bb_anchor",["year","bb_target","anchor_y"])]:
 parts=[]
 for keys,g in x.groupby(strata,observed=True):
  if not isinstance(keys,tuple):keys=(keys,)
  a=g[g.improving];c=g[~g.improving]
  if len(a)==0 or len(c)==0:continue
  r={k:v for k,v in zip(strata,keys)};r["n_imp"]=len(a);r["n_ctrl"]=len(c)
  for h in H:r[f"diff_{h}h"]=a[f"net_{h}h"].mean()-c[f"net_{h}h"].mean()
  parts.append(r)
 pd.DataFrame(parts).to_csv(R/f"taker_buy_incremental_{label}.csv",index=False)
# OOS identical-event coverage
wf=[]
for a,bnd,y in [(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]:
 g=x[x.year==y]
 for name,m in {"improving":g.improving,"anchor_improving":g.anchor_y.astype(bool)&g.improving,"bb_anchor_improving":g.bb_target&g.anchor_y.astype(bool)&g.improving}.items():
  z=g[m];r={"train":f"{a}-{bnd}","year":y,"condition":name,"n":len(z)}
  for h in H:r[f"avg_{h}h"]=z[f"net_{h}h"].mean()
  wf.append(r)
pd.DataFrame(wf).to_csv(R/"taker_buy_incremental_oos.csv",index=False)
print(pd.DataFrame(rows).to_string(index=False))
print("\nOOS\n",pd.DataFrame(wf).to_string(index=False))

# trigger

# rerun
# deterministic incremental audit
