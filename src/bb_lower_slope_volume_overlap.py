import pandas as pd, numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"

s=pd.read_csv(R/"bb_lower_slope_events.csv")
v=pd.read_csv(R/"volume_trajectory_events.csv").sort_values(["event_id","horizon"]).drop_duplicates("event_id")
v=v[["event_id","reentry_vol_z","confirmation_vol_z","entry_vol_z","category"]].rename(columns={"category":"volume_trajectory"})
m=s.merge(v,on="event_id",how="left")
m["volume_anchor"]=(m["reentry_vol_z"]>=1.0).astype(int)
m["slope_group"]=m["category"].eq("falling").map({True:"falling",False:"not_falling"})
m.to_csv(R/"bb_lower_slope_volume_overlap_events.csv",index=False)

rows=[]
for (sg,a),g in m.groupby(["slope_group","volume_anchor"]):
    rec={"slope_group":sg,"volume_anchor":int(a),"n_events":g.event_id.nunique()}
    for h in [2,3,6,12]:
        x=g[g.horizon==h].net_return.dropna()
        rec[f"avg_net_{h}"]=x.mean() if len(x) else np.nan
        rec[f"win_{h}"]=(x>0).mean() if len(x) else np.nan
    rows.append(rec)
pd.DataFrame(rows).to_csv(R/"bb_lower_slope_volume_overlap_summary.csv",index=False)
print(pd.DataFrame(rows).to_string(index=False))

# workflow trigger refresh
