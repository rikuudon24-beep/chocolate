import json,time
from pathlib import Path
import numpy as np,pandas as pd,requests
SYMBOL="BTCUSDT";START=pd.Timestamp("2020-01-01",tz="UTC");END=pd.Timestamp("2026-09-27 20:00:00",tz="UTC")
URL="https://data-api.binance.vision/api/v3/klines"; COST=.001; H=(2,3,6,12)
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"
def fetch():
 rows=[];s=int(START.timestamp()*1000);e=int(END.timestamp()*1000);step=4*60*60*1000
 while s<e:
  z=requests.get(URL,params={"symbol":SYMBOL,"interval":"4h","startTime":s,"endTime":e,"limit":1000},timeout=30);z.raise_for_status();b=z.json()
  if not b:break
  rows+=b;s=int(b[-1][0])+step;time.sleep(.04)
  if len(b)<1000:break
 c=["open_time","open","high","low","close","volume","close_time","qv","tr","tb","tq","ig"];d=pd.DataFrame(rows,columns=c)
 d.open_time=pd.to_datetime(d.open_time,unit="ms",utc=True)
 for q in ["open","high","low","close","volume"]:d[q]=pd.to_numeric(d[q])
 return d[(d.open_time>=START)&(d.open_time<END)].drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
def rma(s,n=14):
 a=s.to_numpy(float);o=np.full(len(a),np.nan)
 if len(a)<n:return pd.Series(o,index=s.index)
 o[n-1]=np.mean(a[:n]);alpha=1/n
 for i in range(n,len(a)):o[i]=(1-alpha)*o[i-1]+alpha*a[i]
 return pd.Series(o,index=s.index)
def features(d):
 x=d.copy();c,o,h,l,v=x.close,x.open,x.high,x.low,x.volume
 tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
 up=h.diff();dn=-l.diff();p=pd.Series(np.where((up>dn)&(up>0),up,0),index=x.index);m=pd.Series(np.where((dn>up)&(dn>0),dn,0),index=x.index)
 atr=rma(tr);pdi=100*rma(p)/atr;mdi=100*rma(m)/atr;dx=100*(pdi-mdi).abs()/(pdi+mdi)
 x["adx"]=rma(dx);x["di"]=pdi-mdi
 tp=(h+l+c)/3;raw=tp*v;sg=tp.diff()
 pos=raw.where(sg>0,0).rolling(14).sum();neg=raw.where(sg<0,0).rolling(14).sum()
 x["mfi"]=100-100/(1+pos/neg.replace(0,np.nan))
 obv=(np.sign(c.diff()).fillna(0)*v).cumsum();x["obvz"]=(obv-obv.rolling(20).mean())/obv.rolling(20).std(ddof=0)
 x["volz"]=(v-v.rolling(20).mean())/v.rolling(20).std(ddof=0)
 x["body"]=abs(c-o)/(h-l).replace(0,np.nan)
 mid=c.rolling(20).mean();sd=c.rolling(20).std(ddof=0);x["bbwidth"]=4*sd/mid
 dlt=c.diff();g=dlt.clip(lower=0);loss=-dlt.clip(upper=0);ag=rma(g);al=rma(loss);x["rsi"]=100-100/(1+ag/al.replace(0,np.nan))
 x["bblo"]=mid-2*sd
 return x
def events(x):
 ev=[];cons=-1;i=20
 while i<len(x)-1:
  p=x.iloc[i-1];q=x.iloc[i]
  if not(i>cons and p.close<p.bblo and q.close>=q.bblo and q.rsi<40):i+=1;continue
  low=float(q.low);mn=float(q.rsi);conf=None;fail=False;end=min(i+6,len(x)-2)
  for j in range(i+1,end+1):
   z=x.iloc[j];mn=min(mn,float(z.rsi))
   if z.low<low or z.close<x.iloc[j].bblo:fail=True;break
   if z.rsi>=mn+5:conf=j;break
  if not fail and conf is not None and conf+1<len(x):
   ev.append({"id":len(ev)+1,"i":i,"entry":conf+1,"time":q.open_time,"year":q.open_time.year})
   cons=conf+1;i=conf+2;continue
  cons=max(cons,end);i+=1
 return pd.DataFrame(ev)
def main():
 x=features(fetch());e=events(x)
 if len(e)!=95:raise RuntimeError(f"expected95 got{len(e)}")
 for c in ["adx","di","mfi","obvz","volz","body","bbwidth","rsi"]:e[c]=e.i.map(lambda i:x.iloc[i][c])
 # Pre-registered state buckets. No threshold selection.
 rules={"ADX<20":e.adx<20,"ADX20-25":(e.adx>=20)&(e.adx<25),"ADX>=25":e.adx>=25,
 "MFI<20":e.mfi<20,"MFI20-30":(e.mfi>=20)&(e.mfi<30),"MFI30-50":(e.mfi>=30)&(e.mfi<50),
 "OBVz<-1":e.obvz<-1,"OBVz-1to1":(e.obvz>=-1)&(e.obvz<1),"OBVz>=1":e.obvz>=1,
 "Volz<0":e.volz<0,"Volz0-1":(e.volz>=0)&(e.volz<1),"Volz>=1":e.volz>=1,
 "Body<0.3":e.body<.3,"Body0.3-0.7":(e.body>=.3)&(e.body<.7),"Body>=0.7":e.body>=.7,
 "BBwidth<0.05":e.bbwidth<.05,"BBwidth0.05-0.12":(e.bbwidth>=.05)&(e.bbwidth<.12),"BBwidth>=0.12":e.bbwidth>=.12,
 "RSI<20":e.rsi<20,"RSI20-30":(e.rsi>=20)&(e.rsi<30),"RSI30-40":e.rsi>=30}
 rows=[]
 for name,mask in rules.items():
  for y in sorted(e.year.unique()):
   z=e[(e.year==y)&mask]
   vals={h:[] for h in H}
   for _,q in z.iterrows():
    for h in H:
     j=int(q.entry)+h-1
     if j<len(x):vals[h].append(x.iloc[j].close/x.iloc[int(q.entry)].open-1)
   for h in H:
    a=np.array(vals[h]);rows.append({"state":name,"year":y,"n":len(a),"h":h,"avg":a.mean() if len(a) else np.nan,"net":a.mean()-COST if len(a) else np.nan,"win":(a>0).mean() if len(a) else np.nan})
 out=pd.DataFrame(rows);out.to_csv(R/"market_state_strata.csv",index=False)
 summary={"purpose":"Pre-registered descriptive market-state strata on frozen 95 events; no threshold optimization or promotion.","events":95,"cost":COST,"states":list(rules)}
 (R/"market_state_strata_summary.json").write_text(json.dumps(summary,indent=2))
 print(out.to_string(index=False))
if __name__=="__main__":main()
