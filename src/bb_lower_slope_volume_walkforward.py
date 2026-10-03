import pandas as pd, numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]
H=[2,3,6,12]

m=pd.read_csv(R/"bb_lower_slope_volume_overlap_events.csv")
m["combo"]=m["slope_group"]+"__vol"+m["volume_anchor"].astype(int)

rows=[]
for a,b,y in SPLITS:
    tr=m[(m.year>=a)&(m.year<=b)]
    va=m[m.year==y]
    candidates=[]
    for combo,g in tr.groupby("combo"):
        n=g.event_id.nunique()
        if n>=5:
            x=g[g.horizon==12].net_return
            candidates.append((combo,n,x.mean()))
    sel=sorted(candidates,key=lambda z:(-z[2],z[0]))[0][0] if candidates else None
    tn=next((n for c,n,_ in candidates if c==sel),0)
    for h in H:
        x=va[(va.combo==sel)&(va.horizon==h)].net_return if sel else pd.Series(dtype=float)
        rows.append({"train":f"{a}-{b}","validation":y,"selected_combo":sel,"train_n":tn,
                     "horizon":h,"validation_n":va[(va.combo==sel)&(va.horizon==h)].event_id.nunique() if sel else 0,
                     "validation_avg_net":x.mean() if len(x) else np.nan,
                     "validation_win":(x>0).mean() if len(x) else np.nan})
out=pd.DataFrame(rows)
out.to_csv(R/"bb_lower_slope_volume_walkforward.csv",index=False)
print(out.to_string(index=False))
