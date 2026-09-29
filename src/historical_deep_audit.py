import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

SYMBOL="BTCUSDT"; START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
COST=0.001; H=(1,2,3,6,12)
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; R.mkdir(exist_ok=True)

def fetch():
    rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
    while s<e:
        z=requests.get("https://data-api.binance.vision/api/v3/klines",
            params={"symbol":SYMBOL,"interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30)
        z.raise_for_status(); b=z.json()
        if not b: break
        rows+=b; s=int(b[-1][0])+step; time.sleep(.04)
        if len(b)<1000: break
    c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"]
    d=pd.DataFrame(rows,columns=c)
    d["open_time"]=pd.to_datetime(d.open_time,unit="ms",utc=True)
    d["close_time"]=pd.to_datetime(d.close_time,unit="ms",utc=True)
    for q in ["open","high","low","close","volume"]: d[q]=pd.to_numeric(d[q],errors="coerce")
    return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rma(s,n=14):
    a=s.to_numpy(float); o=np.full(len(a),np.nan)
    if len(a)<n:return pd.Series(o,index=s.index)
    o[n-1]=np.nanmean(a[:n]); alpha=1/n
    for i in range(n,len(a)):
        o[i]=(1-alpha)*o[i-1]+alpha*a[i]
    return pd.Series(o,index=s.index)

def features(d):
    x=d.copy(); c,o,h,l,v=x.close,x.open,x.high,x.low,x.volume
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    x["bblo"]=mid-2*sd
    dg=c.diff(); ag=rma(dg.clip(lower=0)); al=rma(-dg.clip(upper=0)); x["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
    x["volz"]=(v-v.rolling(20).mean())/v.rolling(20).std(ddof=0)
    return x

def extract(x):
    ev=[]; cons=-1; i=20
    while i<len(x)-1:
        p,q=x.iloc[i-1],x.iloc[i]
        ok=(i>cons and p.close<p.bblo and q.close>=q.bblo and pd.notna(q.rsi) and q.rsi<40)
        if not ok: i+=1; continue
        low=float(q.low); mn=float(q.rsi); conf=None; fail=False; end=min(i+6,len(x)-2)
        for j in range(i+1,end+1):
            z=x.iloc[j]; mn=min(mn,float(z.rsi))
            if z.low<low or z.close<x.iloc[j].bblo: fail=True; break
            if z.rsi>=mn+5: conf=j; break
        if not fail and conf is not None and conf+1<len(x):
            ep=conf+1
            ev.append({"event_id":len(ev)+1,"reentry_idx":i,"confirm_idx":conf,"entry_idx":ep,
                       "event_time":q.open_time,"entry_price":float(x.iloc[ep].open),
                       "year":int(q.open_time.year),"reentry_volz":float(x.iloc[i].volz)})
            cons=ep; i=ep+1
        else:
            cons=max(cons,end); i+=1
    return pd.DataFrame(ev)

def path_stats(x,e,h):
    p=int(e.entry_idx); ep=float(e.entry_price); j=p+h-1
    if j>=len(x): return None
    w=x.iloc[p:j+1]
    return {"event_id":int(e.event_id),"horizon":h,
            "close_ret":float(x.iloc[j].close/ep-1),
            "mfe":float(w.high.max()/ep-1),
            "mae":float(w.low.min()/ep-1),
            "final_close":float(x.iloc[j].close/ep-1),
            "max_high_idx":int(w.high.idxmax()-p),
            "min_low_idx":int(w.low.idxmin()-p)}

def main():
    x=features(fetch()); e=extract(x)
    if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
    # Event path / excursion audit.
    rows=[]
    for _,q in e.iterrows():
        for h in H:
            z=path_stats(x,q,h)
            if z: rows.append(z)
    paths=pd.DataFrame(rows)
    paths.to_csv(R/"historical_deep_paths.csv",index=False)

    # Fixed volume candidate: pre-registered threshold from prior work, descriptive only.
    e["volume_anchor"]=e.reentry_volz>=1.0
    vol=e[e.volume_anchor].copy()
    vol.to_csv(R/"historical_deep_volume_events.csv",index=False)

    # Fixed target/stop surface. Not an optimization result; every cell is reported.
    surfaces=[]
    targets=[0.005,0.01,0.015,0.02,0.03,0.05]
    stops=[-0.005,-0.01,-0.015,-0.02,-0.03,-0.05]
    for label,sub in [("base",e),("vol_z>=1",vol)]:
        for tp in targets:
            for sl in stops:
                vals=[]; wins=0; losses=0; amb=0
                for _,q in sub.iterrows():
                    p=int(q.entry_idx); ep=float(q.entry_price); end=min(p+12,len(x)-1)
                    outcome=None
                    for j in range(p,end+1):
                        hi=float(x.iloc[j].high/ep-1); lo=float(x.iloc[j].low/ep-1)
                        hit_t=hi>=tp; hit_s=lo<=sl
                        if hit_t and hit_s: amb+=1; outcome=np.nan; break
                        if hit_t: outcome=tp; break
                        if hit_s: outcome=sl; break
                    if outcome is None: outcome=float(x.iloc[end].close/ep-1)
                    if np.isfinite(outcome): vals.append(outcome-COST)
                a=np.array(vals,float)
                pf=(a[a>0].sum()/(-a[a<0].sum())) if np.any(a<0) else np.inf
                surfaces.append({"sample":label,"target":tp,"stop":sl,"n":len(a),
                                 "avg_net":float(a.mean()) if len(a) else np.nan,
                                 "win":float((a>0).mean()) if len(a) else np.nan,
                                 "pf":float(pf),"ambiguous":amb})
    pd.DataFrame(surfaces).to_csv(R/"historical_deep_target_stop_surface.csv",index=False)

    # Bootstrap uncertainty for fixed horizons, with deterministic seed.
    rng=np.random.default_rng(20260929)
    boot=[]
    for label,sub in [("base",e),("vol_z>=1",vol)]:
        ids=sub.event_id.astype(int).tolist()
        for h in (2,3,6,12):
            vals=paths[(paths.event_id.isin(ids))&(paths.horizon==h)].close_ret.to_numpy(float)-COST
            if len(vals)==0: continue
            samples=rng.choice(vals,size=(10000,len(vals)),replace=True).mean(axis=1)
            boot.append({"sample":label,"horizon":h,"n":len(vals),"observed_net_avg":float(vals.mean()),
                         "ci2.5":float(np.quantile(samples,.025)),"ci50":float(np.quantile(samples,.5)),
                         "ci97.5":float(np.quantile(samples,.975)),
                         "p_boot_le_zero":float(np.mean(samples<=0))})
    pd.DataFrame(boot).to_csv(R/"historical_deep_bootstrap.csv",index=False)

    # Year stability for the fixed volume anchor.
    ys=[]
    for label,sub in [("base",e),("vol_z>=1",vol)]:
        for y in sorted(e.year.unique()):
            z=sub[sub.year==y]
            for h in (2,3,6,12):
                vals=paths[(paths.event_id.isin(z.event_id))&(paths.horizon==h)].close_ret.to_numpy(float)-COST
                if len(vals): ys.append({"sample":label,"year":y,"horizon":h,"n":len(vals),"net_avg":float(vals.mean()),"win":float((vals>0).mean())})
    pd.DataFrame(ys).to_csv(R/"historical_deep_year_stability.csv",index=False)

    # Event spacing / clustering.
    et=pd.to_datetime(e.event_time,utc=True).sort_values()
    gaps=et.diff().dropna().dt.total_seconds()/3600
    cluster={"n_events":len(e),"median_gap_h":float(gaps.median()),"mean_gap_h":float(gaps.mean()),
             "p10_gap_h":float(gaps.quantile(.10)),"gaps_lt_24h":int((gaps<24).sum()),
             "gaps_lt_48h":int((gaps<48).sum()),"gaps_lt_72h":int((gaps<72).sum()),
             "min_gap_h":float(gaps.min())}
    (R/"historical_deep_cluster.json").write_text(json.dumps(cluster,indent=2),encoding="utf-8")

    summary={"events":95,"volume_anchor_events":int(len(vol)),"cost":COST,
             "purpose":"Deep historical audit of the frozen event sample. All analyses are descriptive or uncertainty audits; no automatic promotion.",
             "target_stop_note":"Fixed grid is fully reported, first-hit logic; same-bar target+stop is ambiguous and excluded from averages.",
             "bootstrap_seed":20260929,"bootstrap_n":10000,
             "lookahead":"All entry features are known at or before entry; target/stop paths begin at entry open.",
             "cluster":cluster}
    (R/"historical_deep_audit_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=="__main__": main()
