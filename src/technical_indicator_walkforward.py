import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

SYMBOL="BTCUSDT"; INTERVAL="4h"
START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
BASE_URL="https://data-api.binance.vision/api/v3/klines"
COST=0.001; HORIZONS=(2,3,6,12)
ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/"results"

def fetch():
    rows=[]; s=int(START.timestamp()*1000); e=int(END.timestamp()*1000); step=4*60*60*1000
    while s<e:
        r=requests.get(BASE_URL,params={"symbol":SYMBOL,"interval":INTERVAL,"startTime":s,"endTime":e,"limit":1000},timeout=30); r.raise_for_status()
        b=r.json()
        if not b: break
        rows+=b; s=int(b[-1][0])+step; time.sleep(.05)
        if len(b)<1000: break
    cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
    d=pd.DataFrame(rows,columns=cols); d["open_time"]=pd.to_datetime(d.open_time,unit="ms",utc=True); d["close_time"]=pd.to_datetime(d.close_time,unit="ms",utc=True)
    for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
    return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); al=l.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return 100-100/(1+ag/al.replace(0,np.nan))

def feat(d):
    x=d.copy(); c,o,h,l,v=x.close,x.open,x.high,x.low,x.volume
    x["rsi"]=rsi(c); ema12=c.ewm(span=12,adjust=False).mean(); ema26=c.ewm(span=26,adjust=False).mean()
    x["macd"]=ema12-ema26; x["macd_signal"]=x.macd.ewm(span=9,adjust=False).mean(); x["macd_hist"]=x.macd-x.macd_signal
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean(); x["atr_pct"]=atr/c
    up=h.diff(); dn=-l.diff()
    pdm=pd.Series(np.where((up>dn)&(up>0),up,0.),index=x.index); mdm=pd.Series(np.where((dn>up)&(dn>0),dn,0.),index=x.index)
    pdi=100*pdm.rolling(14).mean()/atr.replace(0,np.nan); mdi=100*mdm.rolling(14).mean()/atr.replace(0,np.nan)
    x["plus_di"]=pdi; x["minus_di"]=mdi; x["di_spread"]=pdi-mdi; x["adx"]=(100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)).rolling(14).mean()
    for n in (20,50,200):
        em=c.ewm(span=n,adjust=False).mean(); x[f"ema{n}_dist"]=c/em-1; x[f"ema{n}_slope12"]=em/em.shift(3)-1
    lo,hi=l.rolling(14).min(),h.rolling(14).max(); x["stoch"]=100*(c-lo)/(hi-lo).replace(0,np.nan)
    x["mfi"]=100-100/(1+(((h+l+c)/3*v).where(((h+l+c)/3).diff()>0,0).rolling(14).sum())/(-((h+l+c)/3*v).where(((h+l+c)/3).diff()<0,0).rolling(14).sum()).replace(0,np.nan))
    obv=(np.sign(c.diff()).fillna(0)*v).cumsum(); x["obv_z"]=(obv-obv.rolling(20).mean())/obv.rolling(20).std(ddof=0).replace(0,np.nan)
    tp=(h+l+c)/3; x["vwap_dist"]=c/((tp*v).rolling(20).sum()/v.rolling(20).sum())-1
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0); x["bb_width"]=4*sd/mid; x["bb_z"]=(c-mid)/sd.replace(0,np.nan)
    x["vol_z"]=(v-v.rolling(20).mean())/v.rolling(20).std(ddof=0).replace(0,np.nan)
    x["body"]=abs(c-o)/(h-l).replace(0,np.nan); x["lower_wick"]=(np.minimum(o,c)-l)/(h-l).replace(0,np.nan); x["close_loc"]=(c-l)/(h-l).replace(0,np.nan)
    return x

def events(x):
    ev=[]; consumed=-1; i=20
    while i<len(x)-1:
        mp=x.close.iloc[i-20:i].mean(); sp=x.close.iloc[i-20:i].std(ddof=0)
        mc=x.close.iloc[i-19:i+1].mean(); sc=x.close.iloc[i-19:i+1].std(ddof=0)
        if i>consumed and x.close.iloc[i-1]<mp-2*sp and x.close.iloc[i]>=mc-2*sc and x.rsi.iloc[i]<40:
            low=float(x.low.iloc[i]); mn=float(x.rsi.iloc[i]); conf=None
            for j in range(i+1,min(i+6,len(x)-2)+1):
                mn=min(mn,float(x.rsi.iloc[j]))
                mj=x.close.iloc[j-19:j+1].mean(); sj=x.close.iloc[j-19:j+1].std(ddof=0)
                if x.low.iloc[j]<low or x.close.iloc[j]<mj-2*sj: break
                if x.rsi.iloc[j]>=mn+5: conf=j; break
            if conf is not None:
                entry=conf+1
                if entry<len(x): ev.append({"idx":i,"entry":entry,"date":x.open_time.iloc[entry],"vol_z":x.vol_z.iloc[i],"rsi":x.rsi.iloc[i],"macd_hist":x.macd_hist.iloc[i],"di_spread":x.di_spread.iloc[i],"adx":x.adx.iloc[i],"ema20_dist":x.ema20_dist.iloc[i],"ema20_slope12":x.ema20_slope12.iloc[i],"ema200_dist":x.ema200_dist.iloc[i],"ema200_slope12":x.ema200_slope12.iloc[i],"stoch":x.stoch.iloc[i],"mfi":x.mfi.iloc[i],"obv_z":x.obv_z.iloc[i],"vwap_dist":x.vwap_dist.iloc[i],"bb_width":x.bb_width.iloc[i],"body":x.body.iloc[i],"lower_wick":x.lower_wick.iloc[i],"close_loc":x.close_loc.iloc[i]})
                consumed=conf
                i=conf+1; continue
        i+=1
    return pd.DataFrame(ev)

def ret(x,e,h):
    k=int(e.entry); j=k+h
    if j>=len(x): return np.nan
    return x.close.iloc[j]/x.open.iloc[k]-1

# Fixed, semantic thresholds; no optimization.
RULES={
 "vol_z>=1":("vol_z",">=",1.0),"vol_z>=2":("vol_z",">=",2.0),
 "macd_hist>=0":("macd_hist",">=",0.0),"macd_hist<0":("macd_hist","<",0.0),
 "di_spread>=0":("di_spread",">=",0.0),"di_spread<=-5":("di_spread","<=",-5.0),
 "adx>=20":("adx",">=",20.0),"adx>=25":("adx",">=",25.0),
 "ema20_dist>=0":("ema20_dist",">=",0.0),"ema20_dist<0":("ema20_dist","<",0.0),
 "ema20_slope12>=0":("ema20_slope12",">=",0.0),"ema20_slope12<0":("ema20_slope12","<",0.0),
 "ema200_dist>=0":("ema200_dist",">=",0.0),"ema200_dist<0":("ema200_dist","<",0.0),
 "ema200_slope12>=0":("ema200_slope12",">=",0.0),"ema200_slope12<0":("ema200_slope12","<",0.0),
 "stoch<=20":("stoch","<=",20.0),"stoch>=50":("stoch",">=",50.0),
 "mfi<=30":("mfi","<=",30.0),"mfi>=50":("mfi",">=",50.0),
 "obv_z>=1":("obv_z",">=",1.0),"obv_z<=-1":("obv_z","<=",-1.0),
 "vwap_dist>=0":("vwap_dist",">=",0.0),"vwap_dist<0":("vwap_dist","<",0.0),
 "bb_width<=0.05":("bb_width","<=",0.05),"bb_width>=0.12":("bb_width",">=",0.12),
 "body<=0.3":("body","<=",0.3),"body>=0.7":("body",">=",0.7),
 "lower_wick>=0.5":("lower_wick",">=",0.5),"close_loc>=0.5":("close_loc",">=",0.5),
}
SPLITS=[(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def main():
    x=feat(fetch()); ev=events(x)
    if len(ev)!=95: raise RuntimeError(f"expected 95 events, got {len(ev)}")
    rows=[]
    for name,(col,op,thr) in RULES.items():
        mask={"<":ev[col]<thr,"<=":ev[col]<=thr,">":ev[col]>thr,">=":ev[col]>=thr}[op]
        for ts,te,vy in SPLITS:
            tr=ev[(ev.date.dt.year>=ts)&(ev.date.dt.year<=te)&mask]
            va=ev[(ev.date.dt.year==vy)&mask]
            for sample,label in ((tr,"train"),(va,"validation")):
                for h in HORIZONS:
                    vals=[ret(x,e,h) for _,e in sample.iterrows()]; vals=np.array([z for z in vals if np.isfinite(z)])
                    net=vals-COST
                    rows.append({"rule":name,"train_end":te,"validation_year":vy,"sample":label,"horizon":h,"n":len(vals),"avg":float(vals.mean()) if len(vals) else np.nan,"net_avg":float(net.mean()) if len(vals) else np.nan,"win":float((vals>0).mean()) if len(vals) else np.nan})
    out=pd.DataFrame(rows); RESULTS.mkdir(exist_ok=True)
    out.to_csv(RESULTS/"technical_indicator_walkforward.csv",index=False)
    summary={"purpose":"Fixed semantic-threshold walk-forward validation; thresholds pre-registered, no optimization or promotion.","events":95,"cost":COST,"rules":list(RULES),"splits":SPLITS}
    (RESULTS/"technical_indicator_walkforward_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
main()
