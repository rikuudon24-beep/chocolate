import json
from pathlib import Path
import numpy as np, pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/"results"; RESULTS.mkdir(exist_ok=True)

def rma(s,n=14): return s.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
def atr(df,n=14):
    p=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-p).abs(),(df.low-p).abs()],axis=1).max(axis=1)
    return rma(tr,n)

def main():
    df=add_indicators(fetch_klines()); df["atr14"]=atr(df)
    df["vol_z20"]=(df.volume-df.volume.rolling(20).mean())/df.volume.rolling(20).std(ddof=0)
    ev=extract_events(df)
    rows=[]
    for _,e in ev.iterrows():
        ii=df.index[df.open_time==pd.Timestamp(e.entry_time)]
        if not len(ii): continue
        i=int(ii[0]); entry=float(e.entry_price); re=pd.Timestamp(e.reentry_time); conf=pd.Timestamp(e.confirmation_time)
        vol=float(df.iloc[i-1].vol_z20) if i>0 else np.nan
        # Re-entry candle is known; use that value, and entry ATR known at entry.
        ri=df.index[df.open_time==re]; rix=int(ri[0]) if len(ri) else i
        vol_re=float(df.iloc[rix].vol_z20)
        atrp=float(df.iloc[i].atr14/entry)
        delay=(conf-re).total_seconds()/3600
        for h in [2,3,6,12]:
            end=min(i+h,len(df)-1); p=df.iloc[i:end+1]
            rows.append(dict(event_id=int(e.event_id),year=int(pd.Timestamp(e.entry_time).year),
                             volz_re=vol_re,atr_pct=atrp,delay_h=delay,rsi_re=float(e.rsi_at_reentry),
                             horizon=h,ret=float(df.iloc[end].close/entry-1),
                             mfe=float(p.high.max()/entry-1),mae=float(p.low.min()/entry-1)))
    out=pd.DataFrame(rows); out.to_csv(RESULTS/"historical_volume_context.csv",index=False)
    bins=[]
    dims={
      "volz":[(-99,0,"<0"),(0,1,"0~<1"),(1,2,"1~<2"),(2,99,">=2")],
      "rsi":[(-99,20,"<20"),(20,30,"20~<30"),(30,40,"30~<40"),(40,99,">=40")],
      "atr":[(0,.01,"<1%"),(.01,.02,"1~<2%"),(.02,.04,"2~<4%"),(.04,99,">=4%")],
      "delay":[(0,4,"<4h"),(4,8,"4~<8h"),(8,99,">=8h")],
      "mfe6":[(-99,.005,"<0.5%"),(.005,.01,"0.5~<1%"),(.01,.02,"1~<2%"),(.02,.03,"2~<3%"),(.03,99,">=3%")]
    }
    for d,ranges in dims.items():
      for lo,hi,label in ranges:
        for h in [2,3,6,12]:
          x=out[(out.horizon==h)&((out[{"volz":"volz_re","rsi":"rsi_re","atr":"atr_pct","delay":"delay_h","mfe6":"mfe"}[d]]>=lo)&(out[{"volz":"volz_re","rsi":"rsi_re","atr":"atr_pct","delay":"delay_h","mfe6":"mfe"}[d]]<hi))]
          if len(x): bins.append(dict(dimension=d,bin=label,horizon=h,n=len(x),avg_ret=x.ret.mean(),win=(x.ret>0).mean(),median_mfe=x.mfe.median(),median_mae=x.mae.median()))
    # Explicitly inspect volume anchor by year and context, but no selection.
    anchor=out[out.volz_re>=1]
    anchor_year=anchor.groupby(["year","horizon"]).agg(n=("ret","size"),avg_ret=("ret","mean"),win=("ret",lambda s:(s>0).mean())).reset_index()
    pd.DataFrame(bins).to_csv(RESULTS/"historical_volume_context_bins.csv",index=False)
    anchor_year.to_csv(RESULTS/"historical_volume_anchor_year.csv",index=False)
    summary={"events":int(ev.shape[0]),"volume_anchor_events":int((out[out.horizon==2].volz_re>=1).sum()),"purpose":"Fixed historical context strata around volume shock; descriptive only; no threshold optimization or promotion.","lookahead":"All context features are known at or before entry; path starts at entry open."}
    (RESULTS/"historical_volume_context_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("=== SUMMARY ==="); print(json.dumps(summary,ensure_ascii=False,indent=2))
    print("=== BINS ==="); print(pd.DataFrame(bins).to_csv(index=False))
    print("=== ANCHOR YEAR ==="); print(anchor_year.to_csv(index=False))

if __name__=="__main__": main()
