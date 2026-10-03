import pandas as pd, numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
a=pd.read_csv(R/"bb_below_lower_streak_events.csv")
v=pd.read_csv(R/"volume_trajectory_events.csv")
# Keep one row/event from trajectory file and merge by event_id.
v=v.sort_values(["event_id","horizon"]).drop_duplicates("event_id")
cols=[c for c in ["event_id","category"] if c in v.columns]
v=v[cols].rename(columns={"category":"volume_trajectory"})
m=a.merge(v,on="event_id",how="left")
m["volume_anchor"]=np.nan
# If raw volume z is available in trajectory result, recover anchor flag.
for c in ["reentry_vol_z20","reentry_volume_z20","vol_z20_reentry"]:
    if c in v.columns: m["volume_anchor"]=(v[c]>=1).astype(int)
# Otherwise merge raw context event file if present.
try:
    h=pd.read_csv(R/"historical_volume_context_events.csv")
    h=h.drop_duplicates("event_id")
    z=[c for c in h.columns if "vol_z20" in c]
    if z:
        m=m.drop(columns=["volume_anchor"]).merge(h[["event_id",z[0]]],on="event_id",how="left")
        m["volume_anchor"]=(m[z[0]]>=1).astype(int)
except Exception: pass
m.to_csv(R/"bb_streak_volume_overlap_events.csv",index=False)
rows=[]
if "volume_anchor" in m.columns:
    for (cat,anchor),g in m.groupby(["category","volume_anchor"],dropna=False):
        rows.append({"streak_category":cat,"volume_anchor":anchor,"n":g.event_id.nunique()})
pd.DataFrame(rows).to_csv(R/"bb_streak_volume_overlap_summary.csv",index=False)
print(m[["event_id","category","volume_anchor"]].head(20).to_string(index=False))
print(pd.DataFrame(rows).to_string(index=False))
