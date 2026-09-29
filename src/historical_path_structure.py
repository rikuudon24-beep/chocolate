import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests

ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")

def fetch():
 rows=[];s=int(START.timestamp()*1000);e=int(END.timestamp()*1000);step=4*60*60*1000
 while s<e:
  q=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30);q.raise_for_status();b=q.json()
  if not b:break
  rows+=b;s=int(b[-1][0])+step;time.sleep(.03)
  if len(b)<1000:break
 c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"];d=pd.DataFrame(rows,columns=c)
 d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for z in ["open","high","low","close","volume"]:d[z]=pd.to_numeric(d[z],errors="coerce")
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rma(s,n=14):
 a=s.to_numpy(float);o=np.full(len(a),np.nan)
 if len(a)<n:return pd.Series(o,index=s.index)
 o[n-1]=np.nanmean(a[:n]);a1=1/n
 for i in range(n,len(a)):o[i]=(1-a1)*o[i-1]+a1*a[i]
 return pd.Series(o,index=s.index)

def events(x):
 c=x.close;mid=c.rolling(20).mean();sd=c.rolling(20).std(ddof=0);lo=mid-2*sd
 d=c.diff();ag=rma(d.clip(lower=0));al=rma(-d.clip(upper=0));r=100-100/(1+ag/al.replace(0,np.nan))
 x=x.copy();x["lo"]=lo;x["rsi"]=r
 ev=[];cons=-1;i=20
 while i<len(x)-1:
  p,q=x.iloc[i-1],x.iloc[i]
  if not(i>cons and p.close<p.lo and q.close>=q.lo and q.rsi<40):i+=1;continue
  low=float(q.low);mn=float(q.rsi);conf=None;fail=False;end=min(i+6,len(x)-2)
  for j in range(i+1,end+1):
   z=x.iloc[j];mn=min(mn,float(z.rsi))
   if z.low<low or z.close<x.iloc[j].lo:fail=True;break
   if z.rsi>=mn+5:conf=j;break
  if not fail and conf is not None and conf+1<len(x):
   ev.append({"event_id":len(ev)+1,"entry":conf+1,"event_time":q.open_time,"year":q.open_time.year})
   cons=conf+1;i=conf+2;continue
  cons=max(cons,end);i+=1
 return pd.DataFrame(ev)

def main():
 x=fetch();e=events(x)
 if len(e)!=95:raise RuntimeError(f"expected95 got{len(e)}")
 rows=[]
 for _,q in e.iterrows():
  p=int(q.entry);ep=float(x.iloc[p].open)
  for h in [1,2,3,4,6,8,12]:
   if p+h-1>=len(x):continue
   w=x.iloc[p:p+h]
   hi=w.high.to_numpy()/ep-1;lo=w.low.to_numpy()/ep-1;cl=float(x.iloc[p+h-1].close/ep-1)
   im=int(np.argmax(hi));jm=int(np.argmin(lo))
   rows.append({"event_id":q.event_id,"year":q.year,"horizon":h,"close_ret":cl,
                "mfe":float(hi.max()),"mae":float(lo.min()),"time_to_mfe":im+1,
                "time_to_mae":jm+1,"mfe_before_mae":im<jm,
                "efficiency":cl/hi.max() if hi.max()>0 else np.nan})
 p=pd.DataFrame(rows);p.to_csv(R/"historical_path_structure.csv",index=False)

 # Fixed descriptive bins: MFE magnitude and MAE magnitude, no optimization.
 bins=[-np.inf,-.03,-.02,-.01,-.005,0,.005,.01,.02,.03,np.inf]
 labels=["<-3%","-3~-2%","-2~-1%","-1~-0.5%","-0.5~0%","0~0.5%","0.5~1%","1~2%","2~3%",">3%"]
 p2=p[p.horizon==6].copy()
 p2["mfe_bin"]=pd.cut(p2.mfe,bins=bins,labels=labels)
 p2["mae_bin"]=pd.cut(p2.mae,bins=bins,labels=labels)
 rows2=[]
 for col in ["mfe_bin","mae_bin"]:
  for b,g in p2.groupby(col,observed=True):
   rows2.append({"metric":col,"bin":str(b),"n":len(g),"avg_close_ret":g.close_ret.mean(),"win":(g.close_ret>0).mean(),"median_mfe":g.mfe.median(),"median_mae":g.mae.median()})
 pd.DataFrame(rows2).to_csv(R/"historical_path_structure_bins.csv",index=False)

 # Sequence/run structure of 2h/3h/6h/12h outcomes, fixed 95-event order.
 seq=[]
 for h in [2,3,6,12]:
  z=p[p.horizon==h].sort_values("event_id").close_ret.to_numpy()
  signs=np.where(z>0,1,-1)
  runs=[];cur=signs[0];n=1
  for s in signs[1:]:
   if s==cur:n+=1
   else:runs.append((cur,n));cur=s;n=1
  runs.append((cur,n))
  seq.append({"horizon":h,"n":len(z),"wins":int((z>0).sum()),"losses":int((z<=0).sum()),
              "max_win_run":max(n for s,n in runs if s==1) if any(s==1 for s,n in runs) else 0,
              "max_loss_run":max(n for s,n in runs if s==-1) if any(s==-1 for s,n in runs) else 0,
              "mean_ret":float(z.mean()),"median_ret":float(np.median(z))})
 pd.DataFrame(seq).to_csv(R/"historical_sequence_structure.csv",index=False)

 # Shuffle test of sequential max drawdown: preserves returns, destroys order.
 rng=np.random.default_rng(20260930); sh=[]
 for h in [2,3,6,12]:
  z=p[p.horizon==h].sort_values("event_id").close_ret.to_numpy()-0.001
  eq=np.cumprod(1+z);obs=float(np.min(eq/np.maximum.accumulate(eq)-1))
  vals=[]
  for _ in range(10000):
   y=rng.permutation(z);ee=np.cumprod(1+y);vals.append(np.min(ee/np.maximum.accumulate(ee)-1))
  sh.append({"horizon":h,"observed_dd":obs,"shuffle_dd_median":float(np.median(vals)),
             "shuffle_dd_2.5":float(np.quantile(vals,.025)),"shuffle_dd_97.5":float(np.quantile(vals,.975)),
             "obs_rank_pct":float((np.asarray(vals)<=obs).mean())})
 pd.DataFrame(sh).to_csv(R/"historical_sequence_dd_shuffle.csv",index=False)

 summary={"events":95,"horizons":[1,2,3,4,6,8,12],"bootstrap":10000,
          "purpose":"Frozen-sample path-structure and sequence audit; descriptive only, no parameter promotion.",
          "lookahead":"Path statistics begin at entry open; no entry-time future information is used.",
          "bin_note":"Fixed descriptive bins only; no threshold search or selection."}
 (R/"historical_path_structure_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
