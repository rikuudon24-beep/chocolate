import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
START=pd.Timestamp("2020-01-01",tz="UTC"); END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
COST=0.001; H=(2,3,6,12); URL="https://data-api.binance.vision/api/v3/klines"
def fetch():
 rows=[];s=int(START.timestamp()*1000);e=int(END.timestamp()*1000);step=4*60*60*1000
 while s<e:
  b=requests.get(URL,params={"symbol":"BTCUSDT","interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30).json()
  if not b:break
  rows+=b;s=int(b[-1][0])+step;time.sleep(.05)
  if len(b)<1000:break
 d=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","ct","qv","tr","tb","tq","ig"])
 d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for c in ["open","high","low","close","volume"]:d[c]=pd.to_numeric(d[c],errors="coerce")
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
def rma(s,n=14):
 a=s.to_numpy(float);o=np.full(len(a),np.nan);v=np.where(np.isfinite(a))[0]
 if len(v)<n:return pd.Series(o,index=s.index)
 k=v[n-1];o[k]=np.mean(a[v[:n]]);alpha=1/n
 for i in range(k+1,len(a)):o[i]=(1-alpha)*o[i-1]+alpha*a[i] if np.isfinite(a[i]) else o[i-1]
 return pd.Series(o,index=s.index)
def events(x):
 c=x.close;mid=c.rolling(20).mean();sd=c.rolling(20).std(ddof=0);lo=mid-2*sd
 d=c.diff();g=d.clip(lower=0);loss=-d.clip(upper=0);r=100-100/(1+rma(g)/rma(loss).replace(0,np.nan))
 ev=[];cons=-1;i=20
 while i<len(x)-1:
  p=x.iloc[i-1];q=x.iloc[i]
  if not(i>cons and p.close<lo.iloc[i-1] and q.close>=lo.iloc[i] and r.iloc[i]<40):i+=1;continue
  low=q.low;mn=r.iloc[i];conf=None;failed=False;end=min(i+6,len(x)-2)
  for j in range(i+1,end+1):
   z=x.iloc[j];mn=min(mn,r.iloc[j])
   if z.low<low or z.close<lo.iloc[j]:failed=True;break
   if r.iloc[j]>=mn+5:conf=j;break
  if not failed and conf is not None and conf+1<len(x):
   ev.append((i,conf+1,q.open_time));cons=conf+1;i=conf+2;continue
  cons=max(cons,end);i+=1
 return ev
def main():
 x=fetch();volz=(x.volume-x.volume.rolling(20).mean())/x.volume.rolling(20).std(ddof=0)
 ev=events(x)
 if len(ev)!=95:raise RuntimeError(f"expected 95 events, got {len(ev)}")
 rows=[]
 for yi in range(2020,2027):
  subset=[e for e in ev if e[2].year==yi and volz.iloc[e[0]]>=1]
  for h in H:
   vals=[x.close.iloc[e[1]+h-1]/x.open.iloc[e[1]]-1 for e in subset if e[1]+h-1<len(x)]
   a=np.asarray(vals,float)
   rows.append({"year":yi,"horizon":h,"n":len(a),"avg":a.mean() if len(a) else np.nan,"net_avg":a.mean()-COST if len(a) else np.nan,"win":(a>0).mean() if len(a) else np.nan})
 out=pd.DataFrame(rows);out.to_csv(R/"fixed_volume_state_validation.csv",index=False)
 summary={"rule":"event re-entry volume z20 >= 1.0","events":95,"cost":COST,"horizons":list(H),"selection":"none; threshold fixed before evaluation","results":out.to_dict("records")}
 (R/"fixed_volume_state_validation_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(out.to_string(index=False))
if __name__=="__main__":main()
