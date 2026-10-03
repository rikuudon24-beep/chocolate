import pandas as pd, numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
m=pd.read_csv(R/"bb_slope_decomposition_events.csv")
v=pd.read_csv(R/"volume_trajectory_events.csv").sort_values(["event_id","horizon"]).drop_duplicates("event_id")
v=v[["event_id","reentry_vol_z"]]
m=m.merge(v,on="event_id",how="left"); m["volume_anchor"]=(m.reentry_vol_z>=1).astype(int)
m["combo"]=m["mid_category"]+"__"+m["width_category"]+"__vol"+m.volume_anchor.astype(str)
S=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]; H=[2,3,6,12]
rows=[]
for a,b,y in S:
 tr=m[(m.year>=a)&(m.year<=b)]; va=m[m.year==y]
 cand=[]
 for c,g in tr.groupby("combo"):
  n=g.event_id.nunique()
  if n>=5: cand.append((c,n,g[g.horizon==12].net_return.mean()))
 sel=max(cand,key=lambda z:(z[2],z[0])) if cand else None
 for h in H:
  x=va[(va.combo==sel[0])&(va.horizon==h)].net_return if sel else pd.Series(dtype=float)
  rows.append({"train":f"{a}-{b}","validation":y,"selected_combo":sel[0] if sel else None,
               "train_n":sel[1] if sel else 0,"horizon":h,"validation_n":len(x),
               "avg_net":x.mean() if len(x) else np.nan,"win":(x>0).mean() if len(x) else np.nan})
out=pd.DataFrame(rows); out.to_csv(R/"bb_slope_decomposition_volume_walkforward.csv",index=False)
print(out.to_string(index=False))

# workflow trigger refresh
