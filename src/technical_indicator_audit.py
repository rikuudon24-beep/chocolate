import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

SYMBOL = "BTCUSDT"
INTERVAL = "4h"
START = pd.Timestamp("2020-01-01", tz="UTC")
END = pd.Timestamp("2026-09-27 20:00:00", tz="UTC")
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
COST = 0.001
HORIZONS = (2, 3, 6, 12)
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def fetch_market():
    rows = []
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    step = 4 * 60 * 60 * 1000
    while start_ms < end_ms:
        r = requests.get(
            BASE_URL,
            params={"symbol": SYMBOL, "interval": INTERVAL,
                    "startTime": start_ms, "endTime": end_ms, "limit": 1000},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        start_ms = int(batch[-1][0]) + step
        time.sleep(0.08)
        if len(batch) < 1000:
            break

    cols = ["open_time","open","high","low","close","volume","close_time",
            "quote_volume","trades","taker_base_volume","taker_quote_volume","ignore"]
    df = pd.DataFrame(rows, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return (df[(df.open_time >= START) & (df.open_time < END) &
              (df.close_time <= pd.Timestamp.now(tz="UTC"))]
            .drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True))


def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    ag = g.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    al = l.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + ag / al.replace(0, np.nan))


def add_features(d):
    x = d.copy()
    c, o, h, l, v = x.close, x.open, x.high, x.low, x.volume

    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    x["macd"] = ema12 - ema26
    x["macd_signal"] = x.macd.ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x.macd - x.macd_signal

    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.rolling(14).mean()
    x["atr_pct"] = x.atr14 / c

    up = h.diff()
    dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=x.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=x.index)
    atr_s = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    x["plus_di"] = plus_di
    x["minus_di"] = minus_di
    x["adx14"] = dx.rolling(14).mean()
    x["di_spread"] = plus_di - minus_di

    for n in (20, 50, 200):
        e = c.ewm(span=n, adjust=False).mean()
        x[f"ema{n}"] = e
        x[f"ema{n}_dist"] = c / e - 1
        x[f"ema{n}_slope4"] = e / e.shift(1) - 1
        x[f"ema{n}_slope12"] = e / e.shift(3) - 1

    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    x["stoch_k"] = 100 * (c-lo14) / (hi14-lo14).replace(0, np.nan)
    x["stoch_d"] = x.stoch_k.rolling(3).mean()
    x["stoch_spread"] = x.stoch_k - x.stoch_d

    x["roc12"] = c / c.shift(3) - 1
    x["roc24"] = c / c.shift(6) - 1

    # Money Flow Index
    tp = (h+l+c)/3
    raw_mf = tp * v
    direction = np.sign(tp.diff()).fillna(0)
    pos = raw_mf.where(direction > 0, 0.0).rolling(14).sum()
    neg = (-raw_mf.where(direction < 0, 0.0)).rolling(14).sum()
    x["mfi14"] = 100 - 100 / (1 + pos / neg.replace(0, np.nan))

    # OBV and its normalized slopes
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    x["obv_z20"] = (obv-obv.rolling(20).mean()) / obv.rolling(20).std(ddof=0).replace(0, np.nan)
    x["obv_slope20"] = (obv-obv.shift(5)) / v.rolling(20).sum().replace(0, np.nan)

    # Rolling VWAP using typical price * volume
    x["vwap20_dist"] = c / ((tp*v).rolling(20).sum()/v.rolling(20).sum()) - 1

    # Bollinger family
    mid = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    lower, upper = mid-2*std, mid+2*std
    x["bb_pct_b"] = (c-lower) / (upper-lower).replace(0, np.nan)
    x["bb_width"] = (upper-lower) / mid.replace(0, np.nan)
    x["bb_z"] = (c-mid) / std.replace(0, np.nan)
    x["bb_below_lower_lookback20"] = (c < lower).rolling(20).sum()

    # Candle geometry at the re-entry candle (closed candle, therefore known)
    body = (c-o).abs()
    rng = (h-l).replace(0, np.nan)
    x["body_pct_range"] = body / rng
    x["body_signed_pct_range"] = (c-o) / rng
    x["upper_wick_pct"] = (h-np.maximum(o,c)) / rng
    x["lower_wick_pct"] = (np.minimum(o,c)-l) / rng
    x["close_location"] = (c-l) / rng
    x["range_atr"] = rng / x.atr14.replace(0, np.nan)

    # Volume structure
    x["vol_change"] = v / v.shift(1) - 1
    x["vol_z20"] = (v-v.rolling(20).mean()) / v.rolling(20).std(ddof=0).replace(0, np.nan)

    # Existing base indicators
    x["rsi14"] = rsi(c, 14)
    x["ret4"] = c.pct_change(1)
    x["ret12"] = c.pct_change(3)
    x["ret24"] = c.pct_change(6)
    return x


def base_events(x):
    events, consumed = [], -1
    i = 20
    while i < len(x)-1:
        prev, cur = x.iloc[i-1], x.iloc[i]
        ok = (i > consumed and pd.notna(prev.get("bb_z")) and pd.notna(cur.get("bb_z"))
              and prev.close < (prev.close - 2*0 + (prev.close - prev.bb_z*(prev.close/x.bb_z if False else 0))) if False else True)
        # Explicitly reconstruct the base condition to avoid relying on hidden state.
        mid_prev = x.close.iloc[i-1-19:i].mean() if i >= 20 else np.nan
        std_prev = x.close.iloc[i-1-19:i].std(ddof=0) if i >= 20 else np.nan
        mid_cur = x.close.iloc[i-19:i+1].mean() if i >= 19 else np.nan
        std_cur = x.close.iloc[i-19:i+1].std(ddof=0) if i >= 19 else np.nan
        prev_lower = mid_prev - 2*std_prev
        cur_lower = mid_cur - 2*std_cur
        ok = (i > consumed and pd.notna(prev_lower) and pd.notna(cur_lower)
              and prev.close < prev_lower and cur.close >= cur_lower
              and pd.notna(cur.rsi14) and cur.rsi14 < 40)
        if not ok:
            i += 1
            continue
        event_low = float(cur.low)
        running_min = float(cur.rsi14)
        confirm = None
        failed = False
        end = min(i+6, len(x)-2)
        for j in range(i+1, end+1):
            row = x.iloc[j]
            running_min = min(running_min, float(row.rsi14)) if pd.notna(row.rsi14) else running_min
            if row.low < event_low or row.close < (x.iloc[j-19:j+1].close.mean()-2*x.iloc[j-19:j+1].close.std(ddof=0)):
                failed = True; break
            if pd.notna(row.rsi14) and row.rsi14 >= running_min+5:
                confirm=j; break
        if not failed and confirm is not None and confirm+1 < len(x):
            entry=x.iloc[confirm+1]
            events.append({"event_id":len(events)+1,"event_time":cur.open_time,
                           "entry_time":entry.open_time,"entry_price":float(entry.open)})
            consumed=confirm+1; i=confirm+2
        else:
            consumed=max(consumed,end); i+=1
    return pd.DataFrame(events)


def metrics(vals):
    x=pd.Series(vals,dtype=float).dropna()
    if len(x)==0: return {"n":0}
    wins=x[x>0]; losses=x[x<0]
    pf=float(wins.sum()/(-losses.sum())) if len(losses) else float("inf")
    return {"n":int(len(x)),"avg":float(x.mean()),"net_avg":float(x.mean()-COST),
            "win":float((x>0).mean()),"pf":pf}


def main():
    market=add_features(fetch_market())
    events=base_events(market)
    if len(events)!=95:
        raise RuntimeError(f"Frozen base-event count changed: expected 95, got {len(events)}")
    # Merge only features known at the re-entry candle close. Confirmation-derived
    # features are intentionally excluded from this audit.
    feature_names=[
        "macd","macd_signal","macd_hist","plus_di","minus_di","adx14","di_spread",
        "ema20_dist","ema50_dist","ema200_dist","ema20_slope4","ema50_slope4","ema200_slope4",
        "ema20_slope12","ema50_slope12","ema200_slope12","stoch_k","stoch_d","stoch_spread",
        "roc12","roc24","mfi14","obv_z20","obv_slope20","vwap20_dist","bb_pct_b","bb_width","bb_z",
        "bb_below_lower_lookback20","body_pct_range","body_signed_pct_range","upper_wick_pct",
        "lower_wick_pct","close_location","range_atr","vol_change","vol_z20","rsi14","ret4","ret12","ret24"
    ]
    feat=market.set_index("open_time")
    events["year"]=pd.to_datetime(events.event_time,utc=True).dt.year
    for f in feature_names:
        events[f]=events.event_time.map(feat[f])
    # Fixed quartiles are descriptive only; no threshold selection or promotion.
    qrows=[]
    retrows=[]
    idx={t:i for i,t in enumerate(market.open_time)}
    for _,e in events.iterrows():
        p=idx.get(pd.Timestamp(e.entry_time))
        if p is None: continue
        for h in HORIZONS:
            j=p+h-1
            if j<len(market):
                retrows.append({"event_id":int(e.event_id),"year":int(e.year),
                                "horizon":h,"return":float(market.iloc[j].close)/float(e.entry_price)-1})
    returns=pd.DataFrame(retrows)

    audit=[]
    for f in feature_names:
        s=pd.to_numeric(events[f],errors="coerce")
        valid=pd.DataFrame({"event_id":events.event_id,"value":s}).dropna()
        if len(valid)<20: continue
        rho={}
        for h in HORIZONS:
            z=returns[returns.horizon==h].merge(valid,on="event_id")
            rho[h]=float(z.value.corr(z["return"],method="spearman")) if len(z)>=20 else np.nan
        # Descriptive quartiles computed from feature distribution only.
        valid["bin"]=pd.qcut(valid.value,4,labels=["Q1","Q2","Q3","Q4"],duplicates="drop")
        for b in valid.bin.dropna().unique():
            ids=set(valid.loc[valid.bin==b,"event_id"])
            for h in HORIZONS:
                z=returns[(returns.horizon==h)&(returns.event_id.isin(ids))]["return"]
                m=metrics(z)
                audit.append({"feature":f,"bin":str(b),"horizon":h,**m})
        for h,r in rho.items():
            audit.append({"feature":f,"bin":"SPEARMAN","horizon":h,"spearman":r,"n":int(len(valid))})

    summary={"purpose":"Pre-registered broad technical indicator audit on frozen 95-event base sample; descriptive only; no threshold selection, ranking, or promotion.",
             "frozen_events":95,"features":feature_names,"cost":COST,"horizons":HORIZONS,
             "lookahead_rule":"Only values at the re-entry candle close are used; entry-candle close features and confirmation/future values are excluded.",
             "feature_count":len(feature_names)}
    (RESULTS/"technical_indicator_audit_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    pd.DataFrame(audit).to_csv(RESULTS/"technical_indicator_audit.csv",index=False)
    events.to_csv(RESULTS/"technical_indicator_audit_events.csv",index=False)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
