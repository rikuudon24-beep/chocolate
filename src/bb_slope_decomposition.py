import pandas as pd, numpy as np, json
from pathlib import Path
from audit_oos import fetch_klines, add_indicators, extract_events
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
H=[2,3,6,12]; COST=.001
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def build(df):
    df=df.copy()
    mid=df["bb_mid"]; width=(df["bb_lower"]*0) # placeholder
    # BB width in price units = upper-lower; recompute from close rolling std to keep definition explicit
    std=df["close"].rolling(20).std(ddof=0)
    df["bb_width"]=4*std
    ev=extract_events(df)
    idx={pd.Timestamp(t):i for i,t in enumerate(df.open_time)}
    rows=[]
    for _,e in ev.iterrows():
        i=idx[pd.Timestamp(e.reentry_time)]; p=i-1
        if p<3: continue
        atr=float(df.iloc[p]["atr14"]) if "atr14" in df else np.nan
        if not np.isfinite(atr) or atr<=0: continue
        mid_s=(mid.iloc[p]-mid.iloc[p-3])/atr
        width_s=(df.bb_width.iloc[p]-df.bb_width.iloc[p-3])/atr
        mid_cat="down" if mid_s<=-0.50 else ("flat" if mid_s<0.50 else "up")
        width_cat="contracting" if width_s<=-0.50 else ("flat" if width_s<0.50 else "expanding")
        rows.append({"event_id":int(e.event_id),"year":int(pd.Timestamp(e.event_time).year),
                     "entry_time":e.entry_time,"mid_slope_atr":mid_s,"width_slope_atr":width_s,
                     "mid_category":mid_cat,"width_category":width_cat})
    return pd.DataFrame(rows)

def returns(df,ev):
    idx={pd.Timestamp(t):i for i,t in enumerate(df.open_time)}
    op=df.open.to_numpy(); rows=[]
    for _,e in ev.iterrows():
        i=idx[pd.Timestamp(e.entry_time)]
        for h in H:
            if i+h<len(df):
                g=op[i+h]/op[i]-1
                rows.append({**e.to_dict(),"horizon":h,"net_return":g-COST})
    return pd.DataFrame(rows)

def summarize(r):
    out=[]
    for keys,g in r.groupby(["mid_category","width_category","horizon"]):
        v=g.net_return
        gp=v[v>0].sum(); loss=-v[v<0].sum()
        out.append({"mid_category":keys[0],"width_category":keys[1],"horizon":keys[2],
                    "n":g.event_id.nunique(),"avg_net":v.mean(),"win":(v>0).mean(),
                    "pf":gp/loss if loss else np.inf})
    return pd.DataFrame(out)

def wf(r):
    rows=[]
    for a,b,y in SPLITS:
        tr=r[(r.year>=a)&(r.year<=b)]; va=r[r.year==y]
        cand=[]
        for (mc,wc),g in tr.groupby(["mid_category","width_category"]):
            n=g.event_id.nunique()
            if n>=5:
                score=g[g.horizon==12].net_return.mean()
                cand.append((mc,wc,n,score))
        sel=sorted(cand,key=lambda z:(-z[3],z[0],z[1]))[0] if cand else None
        for h in H:
            v=va[(va.mid_category==sel[0])&(va.width_category==sel[1])&(va.horizon==h)] if sel else va.iloc[:0]
            rows.append({"train":f"{a}-{b}","validation":y,
                         "selected_mid":sel[0] if sel else None,"selected_width":sel[1] if sel else None,
                         "train_n":sel[2] if sel else 0,"horizon":h,
                         "validation_n":v.event_id.nunique(),
                         "validation_avg_net":v.net_return.mean() if len(v) else np.nan,
                         "validation_win":(v.net_return>0).mean() if len(v) else np.nan})
    return pd.DataFrame(rows)

def main():
    df=add_indicators(fetch_klines())
    prev=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    df["atr14"]=tr.rolling(14).mean()
    ev=build(df)
    if len(ev)!=95: raise RuntimeError(f"Frozen event count changed: {len(ev)}")
    r=returns(df,ev)
    r.to_csv(R/"bb_slope_decomposition_events.csv",index=False)
    summarize(r).to_csv(R/"bb_slope_decomposition_summary.csv",index=False)
    wf(r).to_csv(R/"bb_slope_decomposition_walkforward.csv",index=False)
    json.dump({"events":95,"cost":COST,"definition":"3-bar pre-reentry BB midline and BB width movement normalized by ATR14","thresholds":"down/contracting <= -0.50; flat -0.50..0.50; up/expanding >=0.50","status":"research_only"},open(R/"bb_slope_decomposition_audit.json","w"),ensure_ascii=False,indent=2)
    print(summarize(r).to_string(index=False)); print("\nWF\n"+wf(r).to_string(index=False))
if __name__=="__main__": main()

# workflow trigger refresh
