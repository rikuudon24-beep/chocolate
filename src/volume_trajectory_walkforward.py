import json, time, math
from pathlib import Path
import pandas as pd, numpy as np, requests

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/"results"; R.mkdir(exist_ok=True)
SYMBOL="BTCUSDT"; INTERVAL="4h"
START=pd.Timestamp("2020-01-01",tz="UTC")
END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
BASE="https://data-api.binance.vision/api/v3/klines"
COST=0.001
HORIZONS=[2,3,6,12]
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def fetch():
    rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000)
    step=4*60*60*1000
    while s<e:
        q=requests.get(BASE,params={"symbol":SYMBOL,"interval":INTERVAL,"startTime":s,"endTime":e,"limit":1000},timeout=30)
        q.raise_for_status(); b=q.json()
        if not b: break
        rows.extend(b); nxt=int(b[-1][0])+step
        if nxt<=s: raise RuntimeError("pagination did not advance")
        s=nxt; time.sleep(.03)
        if len(b)<1000: break
    c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"]
    d=pd.DataFrame(rows,columns=c)
    d["open_time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    d["close_time"]=pd.to_datetime(d.close_time,unit="ms",utc=True)
    for z in ["open","high","low","close","volume"]: d[z]=pd.to_numeric(d[z],errors="coerce")
    d=d[(d.open_time>=START)&(d.open_time<END)&(d.close_time<=pd.Timestamp.now(tz="UTC"))].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    return d

def rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    al=l.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return 100-100/(1+ag/al.replace(0,np.nan))

def add_ind(d):
    x=d.copy(); mid=x.close.rolling(20).mean(); sd=x.close.rolling(20).std(ddof=0)
    x["bb_lower"]=mid-2*sd; x["rsi"]=rsi(x.close)
    x["vol_z20"]=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
    return x

def events(x):
    out=[]; i=20; consumed=-1
    while i<len(x)-1:
        p,q=x.iloc[i-1],x.iloc[i]
        cand=(i>consumed and p.close<p.bb_lower and q.close>=q.bb_lower and pd.notna(q.rsi) and q.rsi<40)
        if not cand: i+=1; continue
        low=float(q.low); mn=float(q.rsi); conf=None; fail=False
        end=min(i+6,len(x)-2)
        for j in range(i+1,end+1):
            z=x.iloc[j]; mn=min(mn,float(z.rsi))
            if float(z.low)<low or float(z.close)<float(z.bb_lower): fail=True; break
            if float(z.rsi)>=mn+5: conf=j; break
        if not fail and conf is not None and conf+1<len(x):
            en=conf+1
            out.append({"event_id":len(out)+1,"event_i":i,"conf_i":conf,"entry_i":en,
                        "event_time":q.open_time.isoformat(),"year":q.open_time.year,
                        "entry_price":float(x.iloc[en].open)})
            consumed=en; i=en+1; continue
        consumed=max(consumed,end); i+=1
    return pd.DataFrame(out)

def classify(rz,cz,ez):
    vals=[rz,cz,ez]
    if any(pd.isna(v) for v in vals): return "unclassified"
    if ez<=rz-1.0 and cz<=rz-0.5: return "sharply_decreases"
    if cz<=rz-0.5 and ez>=cz+0.5: return "decreases_then_reincreases"
    if cz>=rz+0.5 and ez>=cz-0.25: return "increasing"
    if min(vals)>=1.0: return "remains_elevated"
    return "other"

def main():
    x=add_ind(fetch()); e=events(x)
    if len(e)!=95: raise RuntimeError(f"frozen event mismatch: {len(e)} != 95")
    rows=[]
    for _,q in e.iterrows():
        i=int(q.entry_i); r=int(q.event_i); c=int(q.conf_i)
        rz=float(x.iloc[r].vol_z20); cz=float(x.iloc[c].vol_z20); ez=float(x.iloc[i].vol_z20)
        cat=classify(rz,cz,ez)
        for h in HORIZONS:
            j=i+h-1
            if j>=len(x): continue
            ret=float(x.iloc[j].close/q.entry_price-1)
            rows.append({"event_id":int(q.event_id),"year":int(q.year),"reentry_vol_z":rz,
                         "confirmation_vol_z":cz,"entry_vol_z":ez,"category":cat,
                         "horizon":h,"gross_return":ret,"net_return":ret-COST})
    m=pd.DataFrame(rows)
    m.to_csv(R/"volume_trajectory_events.csv",index=False)
    summary=m.groupby(["category","horizon"]).agg(n=("event_id","size"),avg_net=("net_return","mean"),
        median_net=("net_return","median"),win=("net_return",lambda s:(s>0).mean()),
        pf=("net_return",lambda s:s[s>0].sum()/(-s[s<0].sum()) if (s<0).any() else np.inf)).reset_index()
    summary.to_csv(R/"volume_trajectory_summary.csv",index=False)

    wf=[]
    cats=["increasing","remains_elevated","sharply_decreases","decreases_then_reincreases","other"]
    for a,b,vy in SPLITS:
        tr=m[(m.year>=a)&(m.year<=b)&(m.horizon==12)&m.category.isin(cats)]
        scores=[]
        for cat in cats:
            z=tr[tr.category==cat].net_return
            if len(z)>=3: scores.append((float(z.mean()),float(z.median()),cat,len(z)))
        scores.sort(reverse=True)
        selected=scores[0][2] if scores else "none"
        for h in HORIZONS:
            va=m[(m.year==vy)&(m.horizon==h)&(m.category==selected)] if selected!="none" else m.iloc[0:0]
            wf.append({"train":f"{a}-{b}","validation":vy,"selected_category":selected,
                       "train_n":scores[0][3] if scores else 0,"horizon":h,
                       "validation_n":len(va),
                       "validation_avg_net":float(va.net_return.mean()) if len(va) else np.nan,
                       "validation_median_net":float(va.net_return.median()) if len(va) else np.nan,
                       "validation_win":float((va.net_return>0).mean()) if len(va) else np.nan})
    w=pd.DataFrame(wf); w.to_csv(R/"volume_trajectory_walkforward.csv",index=False)

    audit={
      "events":len(e),"cost_round_trip":COST,"horizons":HORIZONS,
      "category_definitions":{
        "increasing":"confirmation z20 >= re-entry z20 + 0.5 AND entry z20 >= confirmation z20 - 0.25",
        "remains_elevated":"all three z20 values >= 1.0 after higher-priority directional categories",
        "sharply_decreases":"entry z20 <= re-entry z20 - 1.0 AND confirmation z20 <= re-entry z20 - 0.5",
        "decreases_then_reincreases":"confirmation z20 <= re-entry z20 - 0.5 AND entry z20 >= confirmation z20 + 0.5",
        "other":"does not meet a fixed category"
      },
      "priority":"sharply_decreases > decreases_then_reincreases > increasing > remains_elevated > other",
      "entry_volume_availability":"entry-candle volume is not known at the entry open; therefore entry-volume-based categories are diagnostic only unless explicitly delayed until entry candle close.",
      "selection_rule":"For each rolling split, choose the category with the highest training mean 12h net return among categories with >=3 training events; validate at 2/3/6/12h. No validation tuning.",
      "status":"research_only"
    }
    (R/"volume_trajectory_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    print("=== SUMMARY ==="); print(summary.to_string(index=False))
    print("=== WALKFORWARD ==="); print(w.to_string(index=False))

if __name__=="__main__": main()
