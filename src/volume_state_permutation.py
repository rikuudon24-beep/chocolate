import json
from pathlib import Path
import numpy as np,pandas as pd,requests,time
ROOT=Path(__file__).resolve().parents[1];R=ROOT/"results"
START=pd.Timestamp("2020-01-01",tz="UTC");END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC");COST=.001;H=(2,3,6,12);N=10000;SEED=20260929
def fetch():
 rows=[];s=int(START.timestamp()*1000);e=int(END.timestamp()*1000);step=4*60*60*1000
 while s<e:
  b=requests.get("https://data-api.binance.vision/api/v3/klines",params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30).json()
  if not b:break
  rows+=b;s=int(b[-1][0])+step;time.sleep(.05)
  if len(b)<1000:break
 d=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","ct","qv","tr","tb","tq","ig"])
 d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for c in ["open","high","low","close","volume"]:d[c]=pd.to_numeric(d[c],errors="coerce")
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
def rma(s,n=14):
 a=s.to_numpy(float);o=np.full(len(a),np.nan);v=np.where(np.isfinite(a))[0]
 k=v[n-1];o[k]=np.mean(a[v[:n]]);alpha=1/n
 for i in range(k+1,len(a)):o[i]=(1-alpha)*o[i-1]+alpha*o[i] if np.isfinite(a[i]) else o[i-1]
 return pd.Series(o,index=s.index)
def main():
 x=fetch();v=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0);c=x.close;mid=c.rolling(20).mean();sd=c.rolling(20).std(ddof=0);lo=mid-2*sd;d=c.diff();r=100-100/(1+rma(d.clip(lower=0))/rma(-d.clip(upper=0)).replace(0,np.nan))
 ev=[];cons=-1;i=20
 while i<len(x)-1:
  p=x.iloc[i-1];q=x.iloc[i]
  if not(i>cons and p.close<lo.iloc[i-1] and q.close>=lo.iloc[i] and r.iloc[i]<40):i+=1;continue
  low=q.low;mn=r.iloc[i];conf=None;fail=False;end=min(i+6,len(x)-2)
  for j in range(i+1,end+1):
   z=x.iloc[j];mn=min(mn,r.iloc[j])
   if z.low<low or z.close<lo.iloc[j]:fail=True;break
   if r.iloc[j]>=mn+5:conf=j;break
  if not fail and conf is not None:
   ev.append({"year":q.open_time.year,"ri":i,"entry":conf+1});cons=conf+1;i=conf+2;continue
  cons=max(cons,end);i+=1
 if len(ev)!=95:raise RuntimeError(f"expected 95, got {len(ev)}")
 ev=pd.DataFrame(ev)
 def vals(mask,h):
  z=ev[mask];return np.array([x.close.iloc[int(e)+h-1]/x.open.iloc[int(e)]-1 for e in z.entry if int(e)+h-1<len(x)])
 obs={h:vals(v.iloc[ev.ri].to_numpy()>=1,h) for h in H}
 observed={h:float(a.mean())-COST for h,a in obs.items()}
 rng=np.random.default_rng(SEED);null={h:np.empty(N) for h in H}
 for k in range(N):
  sel=[]
  for y,g in ev.groupby("year"):
   arr=v.iloc[g.ri].to_numpy(float);sh=rng.permutation(arr);sel.extend((g.index[sh>=1]).tolist())
  m=ev.index.isin(sel)
  for h in H:
   a=vals(m,h);null[h][k]=a.mean()-COST if len(a) else np.nan
 rows=[]
 for h in H:
  a=null[h];o=observed[h];p=float((a>=o).mean())
  rows.append({"horizon":h,"observed_net_avg":o,"null_mean":float(np.nanmean(a)),"null_p_one_sided":p,"n_obs":len(obs[h])})
 out=pd.DataFrame(rows);out.to_csv(R/"volume_state_permutation.csv",index=False)
 summary={"purpose":"Descriptive permutation audit of fixed volume-z>=1 association; not an inferential p-value because threshold was previously explored on the same sample.","events":95,"permutations":N,"seed":SEED,"within_year_shuffle":True,"results":out.to_dict("records")}
 (R/"volume_state_permutation_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 print(out.to_string(index=False))
if __name__=="__main__":main()
