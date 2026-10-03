import pandas as pd, numpy as np
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/"results"

a=pd.read_csv(R/"bb_below_lower_streak_events.csv")
v=pd.read_csv(R/"volume_trajectory_events.csv")

# One row/event with the three closed-candle volume states.
v=v.sort_values(["event_id","horizon"]).drop_duplicates("event_id")
v=v[["event_id","year","reentry_vol_z","confirmation_vol_z","entry_vol_z","category"]].rename(
    columns={"category":"volume_trajectory"}
)

m=a.merge(v,on="event_id",how="left")
m["volume_anchor"]=(m["reentry_vol_z"]>=1.0).astype(int)

m.to_csv(R/"bb_streak_volume_overlap_events.csv",index=False)

rows=[]
for (streak,anchor),g in m.groupby(["category","volume_anchor"]):
    rec={"streak_category":streak,"volume_anchor":int(anchor),"n_events":g.event_id.nunique()}
    for h in [2,3,6,12]:
        x=g[g.horizon==h]["net_return"].dropna()
        rec[f"avg_net_{h}"]=x.mean() if len(x) else np.nan
        rec[f"win_{h}"]=(x>0).mean() if len(x) else np.nan
    rows.append(rec)

summary=pd.DataFrame(rows).sort_values(["volume_anchor","streak_category"])
summary.to_csv(R/"bb_streak_volume_overlap_summary.csv",index=False)

print(summary.to_string(index=False))

# Compare volume-anchor effect within each streak class.
cmp=[]
for streak,g in m.groupby("category"):
    for h in [2,3,6,12]:
        p=g[g.horizon==h]
        a1=p[p.volume_anchor==1]["net_return"].dropna()
        a0=p[p.volume_anchor==0]["net_return"].dropna()
        if len(a1) and len(a0):
            cmp.append({
                "streak_category":streak,"horizon":h,
                "n_anchor":len(a1),"n_nonanchor":len(a0),
                "anchor_avg_net":a1.mean(),"nonanchor_avg_net":a0.mean(),
                "difference":a1.mean()-a0.mean()
            })
pd.DataFrame(cmp).to_csv(R/"bb_streak_volume_overlap_comparison.csv",index=False)
print("\nWithin-streak volume-anchor comparison:")
print(pd.DataFrame(cmp).to_string(index=False))
