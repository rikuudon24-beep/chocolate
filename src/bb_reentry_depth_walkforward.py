import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/"results"
RESULTS.mkdir(exist_ok=True)
HORIZONS=[2,3,6,12]
COST=0.001
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def build(df):
    ev=extract_events(df)
    idx={pd.Timestamp(t):i for i,t in enumerate(df["open_time"])}
    rows=[]
    for _,e in ev.iterrows():
        i=idx[pd.Timestamp(e["reentry_time"])]
        p=df.iloc[i-1]
        width=float(p["bb_lower"]-p["close"])
        std=float((p["bb_lower"]-p["close"])/2) if pd.notna(p["bb_lower"]) else np.nan
        # Immediate pre-reentry penetration measured in standard deviations.
        # Since lower BB = mean - 2*std, this is equivalent to -2 - bb_z.
        depth=float((p["bb_lower"]-p["close"])/(p["bb_lower"]-p["bb_mid"])*2) if pd.notna(p["bb_lower"]) and pd.notna(p["bb_mid"]) and p["bb_lower"]!=p["bb_mid"] else np.nan
        if depth < 0.25: cat="shallow"
        elif depth < 0.50: cat="moderate"
        else: cat="deep"
        rows.append({
            "event_id":int(e["event_id"]),
            "year":int(pd.Timestamp(e["event_time"]).year),
            "entry_time":e["entry_time"],
            "pre_reentry_depth":depth,
            "pre_reentry_distance":width,
            "category":cat,
        })
    return pd.DataFrame(rows)

def returns(df,ev):
    idx={pd.Timestamp(t):i for i,t in enumerate(df["open_time"])}
    op=df["open"].to_numpy()
    rows=[]
    for _,e in ev.iterrows():
        i=idx[pd.Timestamp(e["entry_time"])]
        for h in HORIZONS:
            j=i+h
            if j<len(df):
                gross=float(op[j]/op[i]-1)
                rows.append({**e.to_dict(),"horizon":h,"gross_return":gross,"net_return":gross-COST})
    return pd.DataFrame(rows)

def summary(r):
    out=[]
    for (c,h),g in r.groupby(["category","horizon"]):
        v=g.net_return
        gains=v[v>0].sum(); loss=-v[v<0].sum()
        out.append({"category":c,"horizon":h,"n":len(v),"avg_net":v.mean(),"median_net":v.median(),
                    "win":(v>0).mean(),"pf":gains/loss if loss>0 else np.inf})
    return pd.DataFrame(out).sort_values(["category","horizon"])

def wf(r):
    out=[]
    for a,b,y in SPLITS:
        tr=r[(r.year>=a)&(r.year<=b)]
        va=r[r.year==y]
        cand=[]
        for c,g in tr.groupby("category"):
            n=g.event_id.nunique()
            if n>=3:
                cand.append((c,n,g[g.horizon==12].net_return.mean()))
        sel=sorted(cand,key=lambda z:(-z[2],z[0]))[0][0] if cand else None
        tn=next((n for c,n,_ in cand if c==sel),0)
        for h in HORIZONS:
            v=va[(va.category==sel)&(va.horizon==h)] if sel else va.iloc[0:0]
            out.append({"train":f"{a}-{b}","validation":str(y),"selected_category":sel,"train_n":tn,
                        "horizon":h,"validation_n":v.event_id.nunique(),
                        "validation_avg_net":v.net_return.mean() if len(v) else None,
                        "validation_win":(v.net_return>0).mean() if len(v) else None})
    return pd.DataFrame(out)

def main():
    df=add_indicators(fetch_klines())
    ev=build(df)
    if len(ev)!=95: raise RuntimeError(f"Frozen event count changed: {len(ev)} != 95")
    r=returns(df,ev)
    r.to_csv(RESULTS/"bb_reentry_depth_events.csv",index=False)
    summary(r).to_csv(RESULTS/"bb_reentry_depth_summary.csv",index=False)
    wf(r).to_csv(RESULTS/"bb_reentry_depth_walkforward.csv",index=False)
    audit={"events":95,"cost_round_trip":COST,"horizons":HORIZONS,
           "categories":"shallow <0.25, moderate 0.25-<0.50, deep >=0.50 standard deviations below lower BB on the immediately preceding closed candle",
           "information_boundary":"Uses only the closed candle immediately before Bollinger re-entry; no entry-candle or future data.",
           "status":"research_only"}
    json.dump(audit,open(RESULTS/"bb_reentry_depth_audit.json","w"),ensure_ascii=False,indent=2)
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    print(summary(r).to_string(index=False))
    print(wf(r).to_string(index=False))

if __name__=="__main__":
    main()
