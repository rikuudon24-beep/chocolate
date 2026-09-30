import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")

def fetch():
    rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
    while s<e:
        q=requests.get("https://data-api.binance.vision/api/v3/klines",
                       params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30)
        q.raise_for_status(); b=q.json()
        if not b: break
        rows += b; s=int(b[-1][0])+step; time.sleep(.03)
        if len(b)<1000: break
    c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"]
    d=pd.DataFrame(rows,columns=c); d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
    for z in ["open","high","low","close","volume"]: d[z]=pd.to_numeric(d[z],errors="coerce")
    return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rma(s,n=14):
    a=s.to_numpy(float); o=np.full(len(a),np.nan)
    if len(a)<n:return pd.Series(o,index=s.index)
    o[n-1]=np.nanmean(a[:n]); k=1/n
    for i in range(n,len(a)): o[i]=(1-k)*o[i-1]+k*a[i]
    return pd.Series(o,index=s.index)

def events(x):
    c=x.close; mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0); lo=mid-2*sd
    d=c.diff(); ag=rma(d.clip(lower=0)); al=rma(-d.clip(upper=0))
    r=100-100/(1+ag/al.replace(0,np.nan))
    x=x.copy(); x["lo"]=lo; x["rsi"]=r
    ev=[]; cons=-1; i=20
    while i<len(x)-1:
        p,q=x.iloc[i-1],x.iloc[i]
        if not(i>cons and p.close<p.lo and q.close>=q.lo and q.rsi<40):
            i+=1; continue
        low=float(q.low); mn=float(q.rsi); conf=None; fail=False; end=min(i+6,len(x)-2)
        for j in range(i+1,end+1):
            z=x.iloc[j]; mn=min(mn,float(z.rsi))
            if z.low<low or z.close<x.iloc[j].lo: fail=True; break
            if z.rsi>=mn+5: conf=j; break
        if not fail and conf is not None and conf+1<len(x):
            ev.append({"event_id":len(ev)+1,"entry":conf+1,"event_time":q.open_time,"year":q.open_time.year})
            cons=conf+1; i=conf+2; continue
        cons=max(cons,end); i+=1
    return pd.DataFrame(ev)

def metrics(x,e,h=12):
    rows=[]
    for _,q in e.iterrows():
        p=int(q.entry)
        if p+h-1>=len(x): continue
        ep=float(x.iloc[p].open); w=x.iloc[p:p+h]
        rr=(w.close.to_numpy()/ep)-1; hi=(w.high.to_numpy()/ep)-1; lo=(w.low.to_numpy()/ep)-1
        def first(arr,thr,kind="ge"):
            idx=np.where(arr>=thr if kind=="ge" else arr<=thr)[0]
            return int(idx[0]+1) if len(idx) else 0
        fp=first(rr,0); p05=first(hi,.005); p10=first(hi,.01); p20=first(hi,.02)
        n05=first(lo,-.005,"le"); n10=first(lo,-.01,"le")
        im=int(np.argmax(hi)); jm=int(np.argmin(lo))
        rows.append({
            "event_id":q.event_id,"year":q.year,"group":q.group,"n":1,
            "close_ret":float(rr[-1]),"mfe":float(hi.max()),"mae":float(lo.min()),
            "mfe_before_mae":im<jm,
            "first_positive_h":fp,"first_plus_0_5_h":p05,"first_plus_1_h":p10,"first_plus_2_h":p20,
            "first_minus_0_5_h":n05,"first_minus_1_h":n10,
            "plus_0_5_before_minus_0_5": bool(p05 and (not n05 or p05<n05)),
            "plus_1_before_minus_1": bool(p10 and (not n10 or p10<n10)),
            "mae_before_plus_0_5": bool(n05 and (not p05 or n05<p05)),
            "mae_before_plus_1": bool(n10 and (not p10 or n10<p10)),
            "max_adverse_before_plus_0_5": float(np.min(lo[:p05])) if p05 else np.nan,
            "max_adverse_before_plus_1": float(np.min(lo[:p10])) if p10 else np.nan
        })
    return pd.DataFrame(rows)

def summarize(m):
    out=[]
    for g,gp in m.groupby("group"):
        for h,hp in gp.groupby("horizon"):
            for col in ["first_positive_h","first_plus_0_5_h","first_plus_1_h","first_plus_2_h","first_minus_0_5_h","first_minus_1_h"]:
                z=hp[col]; hit=z>0
                out.append({"group":g,"horizon":h,"metric":col,"n":len(hp),
                             "hit_rate":float(hit.mean()),"median_h":float(z[hit].median()) if hit.any() else np.nan})
            for col in ["plus_0_5_before_minus_0_5","plus_1_before_minus_1","mae_before_plus_0_5","mae_before_plus_1","mfe_before_mae"]:
                out.append({"group":g,"horizon":h,"metric":col,"n":len(hp),
                             "hit_rate":float(hp[col].mean()),"median_h":np.nan})
            for col in ["max_adverse_before_plus_0_5","max_adverse_before_plus_1"]:
                z=hp[col].dropna()
                out.append({"group":g,"horizon":h,"metric":col,"n":len(z),
                             "hit_rate":np.nan,"median_h":float(z.median()) if len(z) else np.nan})
    return pd.DataFrame(out)

def main():
    x=fetch(); e=events(x)
    if len(e)!=95: raise RuntimeError(f"expected95 got {len(e)}")
    mid=x.volume.rolling(20).mean(); sd=x.volume.rolling(20).std(ddof=0)
    x["vol_z20"]=(x.volume-mid)/sd.replace(0,np.nan)
    e=e.copy(); vol_by_time=dict(zip(x.open_time.astype(str),x.vol_z20)); e["vol_z20"]=e.event_time.astype(str).map(vol_by_time); e["group"]=np.where(e.vol_z20>=1.0,"vol_z>=1","base")
    allm=[]
    for h in [2,3,6,12]:
        z=metrics(x,e,h); z["horizon"]=h; allm.append(z)
    m=pd.concat(allm,ignore_index=True)
    m.to_csv(R/"historical_volume_path_timing.csv",index=False)
    s=summarize(m); s.to_csv(R/"historical_volume_path_timing_summary.csv",index=False)
    # Fixed descriptive bins for adverse excursion before +0.5%: no optimization.
    q=m[(m.horizon==6)&m.max_adverse_before_plus_0_5.notna()].copy()
    bins=[-np.inf,-.03,-.02,-.01,-.005,0]; labels=["<-3%","-3~-2%","-2~-1%","-1~-0.5%","-0.5~0%"]
    q["adverse_bin"]=pd.cut(q.max_adverse_before_plus_0_5,bins=bins,labels=labels)
    b=q.groupby(["group","adverse_bin"],observed=True).agg(n=("event_id","size"),mean_close_ret=("close_ret","mean"),hit_plus05_before_minus05=("plus_0_5_before_minus_0_5","mean")).reset_index()
    b.to_csv(R/"historical_volume_path_adverse_bins.csv",index=False)
    # Fixed 12h path archetypes: descriptive only, no threshold search.
    a=m[m.horizon==12].copy()
    def archetype(r):
        p=float(r.first_plus_0_5_h); n=float(r.first_minus_0_5_h)
        if p>0 and (n==0 or p<n): return "immediate_rebound"
        if n>0 and p>0 and n<p: return "pullback_then_rebound"
        if n>0 and p==0: return "failure_after_adverse_move"
        return "no_0_5_hit"
    a["archetype"]=a.apply(archetype,axis=1)
    aa=a.groupby(["group","archetype"]).agg(n=("event_id","size"),mean_close_ret=("close_ret","mean"),median_close_ret=("close_ret","median"),plus1_rate=("first_plus_1_h",lambda s:(s>0).mean()),plus2_rate=("first_plus_2_h",lambda s:(s>0).mean())).reset_index()
    aa.to_csv(R/"historical_volume_path_archetypes.csv",index=False)
    byyear=a.groupby(["group","year","archetype"]).size().reset_index(name="n")
    byyear.to_csv(R/"historical_volume_path_archetypes_by_year.csv",index=False)

    summary={"events":95,"volume_anchor_events":int((e.vol_z20>=1).sum()),"horizons":[2,3,6,12],
             "purpose":"Historical-only timing/order audit of post-entry paths; descriptive, fixed thresholds, no parameter promotion.",
             "entry_rule":"Exact frozen 95-event rule; volume anchor is re-entry volume z20 >= 1.0.",
             "lookahead":"All timing/path variables are measured after entry and are not candidate entry predictors."}
    (R/"historical_volume_path_timing_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("=== TIMING ==="); print(s.to_string(index=False))
    print("=== ADVERSE BINS ==="); print(b.to_string(index=False))

if __name__=="__main__": main()
