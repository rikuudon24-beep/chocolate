import pandas as pd
from pathlib import Path
R=Path(__file__).resolve().parents[1]/"results"; H=[2,3,6,12]
f=pd.read_csv(R/"funding_rate_events.csv")
b=pd.read_csv(R/"bb_decomposition_redundancy_events.csv")[["event_id","target","anchor"]]
x=f.merge(b,on="event_id",how="inner")
if len(x)!=95: raise RuntimeError(len(x))
x["positive"]=x.state.eq("positive")
x["target"]=x.target.astype(bool); x["anchor"]=x.anchor.astype(bool)
conds={
"positive":x.positive,
"neutral":x.state.eq("neutral"),
"anchor_positive":x.anchor&x.positive,
"anchor_neutral":x.anchor&x.state.eq("neutral"),
"target_positive":x.target&x.positive,
"target_neutral":x.target&x.state.eq("neutral"),
"target_anchor_positive":x.target&x.anchor&x.positive,
"target_anchor_neutral":x.target&x.anchor&x.state.eq("neutral")}
rows=[]
for n,m in conds.items():
 g=x[m]; r={"condition":n,"n":len(g)}
 for h in H:r[f"avg_{h}h"]=g[f"net_{h}h"].mean()
 rows.append(r)
pd.DataFrame(rows).to_csv(R/"funding_incremental_summary.csv",index=False)
rows=[]
for y in [2023,2024,2025,2026]:
 g=x[x.year.eq(y)]
 for n,m in {"positive":g.positive,"anchor_positive":g.anchor&g.positive,"target_anchor_positive":g.target&g.anchor&g.positive}.items():
  z=g[m];r={"year":y,"condition":n,"n":len(z)}
  for h in H:r[f"avg_{h}h"]=z[f"net_{h}h"].mean()
  rows.append(r)
pd.DataFrame(rows).to_csv(R/"funding_incremental_oos.csv",index=False)
# fixed matched differences inside year x anchor and year x target x anchor
for fn,keys in [("funding_incremental_year_anchor.csv",["year","anchor"]),("funding_incremental_year_target_anchor.csv",["year","target","anchor"])]:
 out=[]
 for k,g in x.groupby(keys,observed=True):
  if not isinstance(k,tuple): k=(k,)
  p=g[g.positive]; n=g[~g.positive]
  if len(p)==0 or len(n)==0: continue
  r=dict(zip(keys,k)); r.update(n_pos=len(p),n_ctrl=len(n))
  for h in H:r[f"diff_{h}h"]=p[f"net_{h}h"].mean()-n[f"net_{h}h"].mean()
  out.append(r)
 pd.DataFrame(out).to_csv(R/fn,index=False)
print(pd.DataFrame(rows).to_string(index=False))
