import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/"results"
COST=0.001
events=pd.read_csv(R/"condition_search_events.csv",parse_dates=["event_time","entry_time"])
ret=pd.read_csv(R/"rolling_volume_interaction.csv")
# Fixed, pre-registered candidate for descriptive replication only.
anchor=events["vol_z20_reentry"]>=1.0
candidate=anchor & (events["rsi_reentry"]>=30.0)
rows=[]
for label,mask in [("volume_anchor",anchor),("volume_plus_rsi30",candidate)]:
    sub=events[mask]
    for year,g in sub.groupby("year"):
        # rolling_volume_interaction contains validation returns only; use rows matching the
        # exact candidate where available, and report event count independently.
        rows.append({"sample":label,"year":int(year),"events":int(len(g))})
# Compare candidate coverage by year and identify years with zero events.
summary={"cost":COST,"anchor":"vol_z20_reentry >= 1.0",
         "fixed_candidate":"vol_z20_reentry >= 1.0 AND rsi_reentry >= 30.0",
         "purpose":"Pre-registered replication/coverage audit; no threshold selection and no promotion.",
         "coverage":rows,
         "anchor_total":int(anchor.sum()),
         "candidate_total":int(candidate.sum()),
         "candidate_years_with_zero":[int(y) for y in sorted(events.loc[events.year.unique(),"year"].unique()) if len(events[(events.year==y)&candidate])==0]}
(R/"fixed_candidate_coverage.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False,indent=2))