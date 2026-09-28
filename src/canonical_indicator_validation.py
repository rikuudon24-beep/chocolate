import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

SYMBOL="BTCUSDT"; INTERVAL="4h"
START=pd.Timestamp("2020-01-01",tz="UTC")
END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
BASE_URL="https://data-api.binance.vision/api/v3/klines"
HORIZONS=(2,3,6,12)
COST=0.001
ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/"results"

def fetch():
    rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
    while s<e:
        r=requests.get(BASE_URL,params={"symbol":SYMBOL,"interval":INTERVAL,"startTime":s,"endTime":e,"limit":1000},timeout=30)
        r.raise_for_status(); b=r.json()
        if not b: break
        rows+=b; s=int(b[-1][0])+step; time.sleep(.05)
        if len(b)<1000: break
    cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
    d=pd.DataFrame(rows,columns=cols)
    d["open_time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    d["close_time"]=pd.to_datetime(d.close_time,unit="ms",utc=True)
    for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
    return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rma(s,n):
    # Wilder smoothing: SMA seed, then recursive RMA.
    a=s.to_numpy(dtype=float); out=np.full(len(a),np.nan)
    if len(a)<n: return pd.Series(out,index=s.index)
    valid=np.where(np.isfinite(a))[0]
    if len(valid)<n: return pd.Series(out,index=s.index)
    seed_idx=valid[n-1]
    seed=np.mean(a[valid[:n]]); out[seed_idx]=seed
    alpha=1/n
    for i in range(seed_idx+1,len(a)):
        if np.isfinite(a[i]): out[i]=(1-alpha)*out[i-1]+alpha*a[i]
        else: out[i]=out[i-1]
    return pd.Series(out,index=s.index)

def rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0); loss=-d.clip(upper=0)
    ag=rma(g,n); al=rma(loss,n)
    rs=ag/al.replace(0,np.nan)
    return 100-100/(1+rs)

def add_canonical(d):
    x=d.copy(); c,o,h,l,v=x.close,x.open,x.high,x.low,x.volume
    # Canonical Wilder DMI/ADX
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up=h.diff(); dn=-l.diff()
    pdm=pd.Series(np.where((up>dn)&(up>0),up,0.0),index=x.index)
    mdm=pd.Series(np.where((dn>up)&(dn>0),dn,0.0),index=x.index)
    atr=rma(tr,14); p_dm=rma(pdm,14); m_dm=rma(mdm,14)
    pdi=100*p_dm/atr.replace(0,np.nan); mdi=100*m_dm/atr.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx=rma(dx,14)
    x["plus_di_w"]=pdi; x["minus_di_w"]=mdi; x["di_spread_w"]=pdi-mdi; x["adx14_w"]=adx

    # Standard MFI: positive/negative money flow from typical-price direction.
    tp=(h+l+c)/3; raw=tp*v; direction=tp.diff()
    pos=raw.where(direction>0,0.0).rolling(14,min_periods=14).sum()
    neg=raw.where(direction<0,0.0).rolling(14,min_periods=14).sum()
    ratio=pos/neg.replace(0,np.nan)
    x["mfi14_std"]=100-100/(1+ratio)

    # Standard OBV; z-score is a derived normalization, not a replacement for OBV.
    obv=(np.sign(c.diff()).fillna(0)*v).cumsum()
    x["obv_std"]=obv
    x["obv_z20_std"]=(obv-obv.rolling(20,min_periods=20).mean())/obv.rolling(20,min_periods=20).std(ddof=0).replace(0,np.nan)

    # Shared base indicators, matching frozen event definition.
    mid=c.rolling(20,min_periods=20).mean(); sd=c.rolling(20,min_periods=20).std(ddof=0)
    x["bb_lower"]=mid-2*sd
    x["rsi14"]=rsi(c,14)
    return x

def extract_events(x):
    ev=[]; consumed_until=-1; i=20
    while i<len(x)-1:
        prev=x.iloc[i-1]; cur=x.iloc[i]
        candidate=(i>consumed_until and pd.notna(prev.bb_lower) and pd.notna(cur.bb_lower)
                   and prev.close<prev.bb_lower and cur.close>=cur.bb_lower
                   and pd.notna(cur.rsi14) and cur.rsi14<40)
        if not candidate:
            i+=1; continue
        event_low=float(cur.low); running_min=float(cur.rsi14); conf=None; failed=False
        window_end=min(i+6,len(x)-2)
        for j in range(i+1,window_end+1):
            row=x.iloc[j]
            if pd.notna(row.rsi14): running_min=min(running_min,float(row.rsi14))
            new_low=float(row.low)<event_low
            rebreak=pd.notna(row.bb_lower) and float(row.close)<float(row.bb_lower)
            if new_low or rebreak: failed=True; break
            if pd.notna(row.rsi14) and float(row.rsi14)>=running_min+5:
                conf=j; break
        if not failed and conf is not None:
            entry=conf+1
            if entry<len(x):
                ev.append({"event_id":len(ev)+1,"event_idx":i,"entry_idx":entry,
                           "event_time":cur.open_time,"entry_time":x.iloc[entry].open_time,
                           "entry_price":float(x.iloc[entry].open)})
                consumed_until=entry; i=entry+1; continue
        consumed_until=max(consumed_until,window_end); i+=1
    return pd.DataFrame(ev)

RULES={
 "ADX>=20":("adx14_w",">=",20),"ADX>=25":("adx14_w",">=",25),
 "DI_spread>=0":("di_spread_w",">=",0),"DI_spread<=-5":("di_spread_w","<=",-5),
 "MFI<=30":("mfi14_std","<=",30),"MFI>=50":("mfi14_std",">=",50),
 "OBV_z>=1":("obv_z20_std",">=",1),"OBV_z<=-1":("obv_z20_std","<=",-1),
}
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def ret(x,e,h):
    j=int(e.entry_idx)+h-1
    if j>=len(x): return np.nan
    return float(x.iloc[j].close)/float(e.entry_price)-1

def calc(vals):
    a=np.asarray(vals,dtype=float); a=a[np.isfinite(a)]
    if len(a)==0: return {"n":0,"avg":np.nan,"net_avg":np.nan,"win":np.nan,"pf":np.nan}
    w=a[a>0]; l=a[a<0]; pf=(w.sum()/(-l.sum())) if len(l) else np.inf
    return {"n":int(len(a)),"avg":float(a.mean()),"net_avg":float(a.mean()-COST),
            "win":float((a>0).mean()),"pf":float(pf)}

def main():
    x=add_canonical(fetch()); ev=extract_events(x)
    if len(ev)!=95: raise RuntimeError(f"Frozen base-event mismatch: expected 95, got {len(ev)}")
    idx=x.set_index("open_time")
    for col in ["adx14_w","di_spread_w","mfi14_std","obv_z20_std"]:
        ev[col]=ev.event_time.map(idx[col])
    rows=[]
    for rule,(col,op,thr) in RULES.items():
        mask={"<=":ev[col]<=thr,">=":ev[col]>=thr}[op]
        for ts,te,vy in SPLITS:
            for label,sample in [("train",ev[(ev.event_time.dt.year>=ts)&(ev.event_time.dt.year<=te)&mask]),
                                 ("validation",ev[(ev.event_time.dt.year==vy)&mask])]:
                for h in HORIZONS:
                    vals=[ret(x,e,h) for _,e in sample.iterrows()]
                    rows.append({"rule":rule,"train_end":te,"validation_year":vy,"sample":label,
                                 "horizon":h,**calc(vals)})
    out=pd.DataFrame(rows)
    comparison=[]
    for rule,(col,op,thr) in RULES.items():
        for year in [2023,2024,2025,2026]:
            z=out[(out.rule==rule)&(out.validation_year==year)&(out.sample=="validation")]
            comparison.append({"rule":rule,"year":year,"events":int(z.n.max() if len(z) else 0),
                               "net_avg_mean_horizons":float(z.net_avg.mean()) if len(z) else np.nan,
                               "positive_horizons":int((z.net_avg>0).sum()) if len(z) else 0,
                               "pf_mean":float(z.pf.replace([np.inf],np.nan).mean()) if len(z) else np.nan})
    summary={"purpose":"Canonical implementation audit on the frozen 95-event denominator; no threshold selection or promotion.",
             "definitions":{"DMI_ADX":"Wilder RMA(14) for TR/+DM/-DM, DX, then ADX RMA(14).",
                            "MFI":"Typical-price direction; positive/negative raw money-flow sums over 14.",
                            "OBV":"Cumulative signed volume; OBV_z20 is rolling z-score of canonical OBV.",
                            "lookahead":"Only re-entry candle close values are used."},
             "events":95,"cost":COST,"horizons":HORIZONS}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS/"canonical_indicator_validation_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    out.to_csv(RESULTS/"canonical_indicator_validation.csv",index=False)
    pd.DataFrame(comparison).to_csv(RESULTS/"canonical_indicator_validation_comparison.csv",index=False)
    ev.to_csv(RESULTS/"canonical_indicator_validation_events.csv",index=False)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(pd.DataFrame(comparison).to_string(index=False))

if __name__=="__main__": main()
