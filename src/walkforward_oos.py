import pandas as pd
import numpy as np
from pathlib import Path
from audit_oos import fetch_klines, add_indicators, extract_events

RESULTS=Path(__file__).resolve().parents[1]/"results"
CUT=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")

def main():
    df=fetch_klines()
    df=df[df["open_time"]<CUT].copy()
    df=add_indicators(df)
    events=extract_events(df)
    events["event_year"]=pd.to_datetime(events["event_time"],utc=True).dt.year

    folds=[
        (2020,2022,2023),
        (2020,2023,2024),
        (2020,2024,2025),
        (2020,2025,2026),
    ]
    rows=[]
    for train_start,train_end,val_year in folds:
        train=events[(events.event_year>=train_start)&(events.event_year<=train_end)]
        val=events[events.event_year==val_year]
        for horizon in [2,3,6,12]:
            for _,e in val.iterrows():
                entry_idx=df.index[df.open_time>=pd.Timestamp(e.entry_time, tz="UTC")]
                if len(entry_idx)==0: continue
                pos=df.index.get_loc(entry_idx[0])
                target=pos+horizon-1
                if target>=len(df): continue
                ret=float(df.iloc[target].close)/float(e.entry_price)-1
                rows.append({"train_end":train_end,"validation_year":val_year,"train_events":len(train),"validation_event_id":int(e.event_id),"horizon":horizon,"return":ret})
    detail=pd.DataFrame(rows)
    detail.to_csv(RESULTS/"oos_walkforward_events.csv",index=False)
    summary=[]
    for (te,vy,h),g in detail.groupby(["train_end","validation_year","horizon"]):
        wins=(g["return"]>0).sum(); losses=(-g.loc[g["return"]<0,"return"]).sum()
        gains=g.loc[g["return"]>0,"return"].sum()
        summary.append({"train_end":te,"validation_year":vy,"horizon":h,"n":len(g),"avg_return":g["return"].mean(),"median_return":g["return"].median(),"win_rate":wins/len(g),"profit_factor":gains/losses if losses else np.nan})
    pd.DataFrame(summary).to_csv(RESULTS/"oos_walkforward_summary.csv",index=False)
    summary_df=pd.DataFrame(summary)
    agg=[]
    for h,g in detail.groupby("horizon"):
        for cost in [0.0,0.0005,0.0010,0.0015]:
            rr=g["return"]-cost
            wins=rr[rr>0].sum(); losses=-rr[rr<0].sum()
            agg.append({"horizon":h,"round_trip_cost":cost,"n":len(rr),"avg_return":rr.mean(),"win_rate":(rr>0).mean(),"profit_factor":wins/losses if losses else np.nan})
    pd.DataFrame(agg).to_csv(RESULTS/"oos_walkforward_cost_summary.csv",index=False)
    print(summary_df.to_string(index=False))
    print(pd.DataFrame(agg).to_string(index=False))

if __name__=="__main__": main()
