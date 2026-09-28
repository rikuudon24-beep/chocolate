import json
import urllib.request
from datetime import datetime, timezone

import pandas as pd

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = "2020-01-01"
END = "2026-09-29"
BASE = "https://data-api.binance.vision/api/v3/klines"

def fetch_klines():
    rows = []
    start_ms = int(pd.Timestamp(START, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(END, tz="UTC").timestamp() * 1000)
    while start_ms < end_ms:
        url = f"{BASE}?symbol={SYMBOL}&interval={INTERVAL}&startTime={start_ms}&endTime={end_ms}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 1
        if nxt <= start_ms:
            break
        start_ms = nxt
        if len(batch) < 1000:
            break
    cols=["open_time","open","high","low","close","volume","close_time","qav","trades","tbav","tbqav","ignore"]
    df=pd.DataFrame(rows, columns=cols)
    df["open_time"]=pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open","high","low","close"]:
        df[c]=pd.to_numeric(df[c])
    return df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)

def rsi(s, n=14):
    d=s.diff()
    up=d.clip(lower=0)
    dn=-d.clip(upper=0)
    au=up.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    ad=dn.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs=au/ad.replace(0, pd.NA)
    return 100-(100/(1+rs))

def build_events(df, delta):
    mid=df.close.rolling(20).mean()
    sd=df.close.rolling(20).std(ddof=0)
    lower=mid-2*sd
    rs=rsi(df.close)
    events=[]
    consumed=-1
    for i in range(20, len(df)-8):
        if i <= consumed:
            continue
        if pd.isna(lower.iloc[i-1]) or pd.isna(rs.iloc[i]):
            continue
        if df.close.iloc[i-1] >= lower.iloc[i-1] or df.close.iloc[i] < lower.iloc[i]:
            continue
        if rs.iloc[i] >= 40:
            continue
        event_low=df.low.iloc[i]
        rmin=rs.iloc[i]
        conf=None
        for j in range(i, min(i+7,len(df))):
            rmin=min(rmin, rs.iloc[j])
            if df.low.iloc[j] < event_low or df.close.iloc[j] < lower.iloc[j]:
                break
            if rs.iloc[j] >= rmin + delta:
                conf=j
                break
        if conf is None:
            consumed=i+6
            continue
        entry=conf+1
        if entry >= len(df):
            break
        events.append({"event_time":df.open_time.iloc[i],"entry_idx":entry,"entry_time":df.open_time.iloc[entry],"entry_price":df.open.iloc[entry],"event_low":event_low})
        consumed=conf+6
    return pd.DataFrame(events)

def metrics(df, events, horizon=12):
    out=[]
    for _,e in events.iterrows():
        k=int(e.entry_idx); end=min(k+horizon,len(df)-1)
        entry=e.entry_price
        ret=df.close.iloc[end]/entry-1
        path=df.close.iloc[k:end+1]/entry-1
        out.append({"ret":ret,"mfe":df.high.iloc[k:end+1].max()/entry-1,"mae":df.low.iloc[k:end+1].min()/entry-1})
    x=pd.DataFrame(out)
    if x.empty: return {"n":0}
    gains=x.loc[x.ret>0,"ret"].sum(); losses=-x.loc[x.ret<0,"ret"].sum()
    return {"n":len(x),"avg":x.ret.mean(),"median":x.ret.median(),"win":(x.ret>0).mean(),"pf":(gains/losses if losses else None),"mfe":x.mfe.mean(),"mae":x.mae.mean()}

def main():
    df=fetch_klines()
    rows=[]
    for delta in [3,4,5,6,7,8]:
        ev=build_events(df,delta)
        for h in [2,3,6,12]:
            m=metrics(df,ev,h)
            m.update(delta=delta,horizon=h)
            rows.append(m)
    pd.DataFrame(rows).to_csv("results/oos_robustness.csv",index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=="__main__":
    main()
