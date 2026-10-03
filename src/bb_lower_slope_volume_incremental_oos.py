import pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
H=[2,3,6,12]
m=pd.read_csv(R/"bb_lower_slope_volume_overlap_events.csv")
rows=[]
for a,b,y in SPLITS:
    va=m[m.year==y]
    for label,mask in {
        "volume_anchor":va.volume_anchor==1,
        "falling_volume_anchor":(va.volume_anchor==1)&(va.slope_group=="falling")
    }.items():
        for h in H:
            x=va[(mask)&(va.horizon==h)].net_return.dropna()
            rows.append({"validation":y,"signal":label,"horizon":h,"n":va[(mask)&(va.horizon==h)].event_id.nunique(),
                         "avg_net":x.mean() if len(x) else None,"win":(x>0).mean() if len(x) else None})
out=pd.DataFrame(rows); out.to_csv(R/"bb_lower_slope_volume_incremental_oos.csv",index=False)
print(out.to_string(index=False))

# workflow trigger refresh
