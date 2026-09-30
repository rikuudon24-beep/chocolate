import json
from pathlib import Path
import pandas as pd, numpy as np
from audit_oos import fetch_klines, add_indicators, extract_events
ROOT=Path(__file__).resolve().parents[1]; RESULTS=ROOT/"results"; RESULTS.mkdir(exist_ok=True)
def rma(s,n=14): return s.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
def atr(df,n=14):
 p=df.close.shift(1); tr=pd.concat([(df.high-df.low).abs(),(df.high-p).abs(),(df.low-p).abs()],axis=1).max(axis=1); return rma(tr,n)
def main():
 df=add_indicators(fetch_klines()); df["atr14"]=atr(df); df["volz"]=(df.volume-df.volume.rolling(20).mean())/df.volume.rolling(20).std(ddof=0)
 ev=extract_events(df); rows=[]
 for _,e in ev.iterrows():
  ii=df.index[df.open_time==pd.Timestamp(e.entry_time)]; ri=df.index[df.open_time==pd.Timestamp(e.reentry_time)]
  if not len(ii) or not len(ri): continue
  i=int(ii[0]); r=int(ri[0]); entry=float(e.entry_price)
  for h in [2,3,6,12]:
   end=min(i+h,len(df)-1); rows.append({"event_id":int(e.event_id),"vol_bin":pd.cut([float(df.iloc[r].volz)],[-99,0,1,2,99],labels=["<0","0~<1","1~<2",">=2"])[0],"rsi_bin":pd.cut([float(e.rsi_at_reentry)],[-99,20,30,40,99],labels=["<20","20~<30","30~<40",">=40"])[0],"atr_bin":pd.cut([float(df.iloc[i].atr14/entry)],[-1,.01,.02,.04,99],labels=["<1%","1~<2%","2~<4%",">=4%"])[0],"h":h,"ret":float(df.iloc[end].close/entry-1)})
 out=pd.DataFrame(rows)
 for dim in ["rsi_bin","atr_bin"]:
  tab=out[out.vol_bin.isin(["1~<2",">=2"])].groupby(["vol_bin",dim,"h"],observed=True).agg(n=("ret","size"),avg=("ret","mean"),win=("ret",lambda s:(s>0).mean())).reset_index()
  tab.to_csv(RESULTS/f"historical_volume_{dim}_interaction.csv",index=False)
  print(f"=== {dim.upper()} ==="); print(tab.to_csv(index=False))
 summary={"events":int(len(ev)),"purpose":"Fixed volume-by-context interaction audit; descriptive cross-strata only; no threshold optimization or promotion.","lookahead":"All conditioning variables known by re-entry/entry; returns begin at entry open."}
 (RESULTS/"historical_volume_interaction_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print("=== SUMMARY ==="); print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
