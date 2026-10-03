import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
H = [2, 3, 6, 12]
COST = 0.001
SPLITS = [(2020,2022,2023),(2020,2023,2024),(2020,2024,2025),(2020,2025,2026)]

def enrich(x):
    x = x.copy()
    prev = x.close.shift(1)
    tr = pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.rolling(14).mean()
    x["atr_pct"] = x.atr14 / x.close
    std = x.close.rolling(20).std(ddof=0)
    x["bb_width_abs"] = 4 * std
    x["bb_width_pct"] = x["bb_width_abs"] / x.close.rolling(20).mean()
    mean20=x.volume.rolling(20).mean(); std20=x.volume.rolling(20).std(ddof=0)
    x["vol_z20"]=(x.volume-mean20)/std20.replace(0,np.nan)
    return x

def build(x):
    ev = extract_events(x)
    idx={pd.Timestamp(t):i for i,t in enumerate(x.open_time)}
    rows=[]
    for _,e in ev.iterrows():
        i=idx[pd.Timestamp(e.reentry_time)]; p=i-1
        if p<3: continue
        atr=float(x.iloc[p].atr14)
        if not np.isfinite(atr) or atr<=0: continue
        mid_s=(x.bb_mid.iloc[p]-x.bb_mid.iloc[p-3])/atr
        width_s=(x.bb_width_abs.iloc[p]-x.bb_width_abs.iloc[p-3])/atr
        mc="down" if mid_s<=-.5 else ("flat" if mid_s<.5 else "up")
        wc="contracting" if width_s<=-.5 else ("flat" if width_s<.5 else "expanding")
        entry_i=idx[pd.Timestamp(e.entry_time)]
        row={**e.to_dict(),"year":int(pd.Timestamp(e.event_time).year),
             "mid_slope_atr":mid_s,"width_slope_atr":width_s,
             "mid_category":mc,"width_category":wc,
             "target": mc=="flat" and wc=="expanding",
             "anchor": float(x.iloc[i].vol_z20)>=1.0,
             "reentry_atr_pct":float(x.iloc[i].atr14/x.iloc[i].close),
             "reentry_bb_width_pct":float(x.iloc[i].bb_width_pct),
             "entry_index":entry_i}
        for h in H:
            j=entry_i+h
            row[f"net_{h}h"]=float(x.iloc[j].open/x.iloc[entry_i].open-1-COST) if j<len(x) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

def add_bins(e):
    e=e.copy()
    e["atr_bin"]=pd.cut(e.reentry_atr_pct,[-np.inf,.01,.02,.04,np.inf],labels=["<1%","1-2%","2-4%",">=4%"],right=False)
    e["bb_bin"]=pd.cut(e.reentry_bb_width_pct,[-np.inf,.05,.12,np.inf],labels=["<5%","5-12%",">=12%"],right=False)
    e["anchor_label"]=np.where(e.anchor,"vol1","vol0")
    e["target_label"]=np.where(e.target,"flat_expand","other")
    return e

def group_summary(e, groupcols):
    rows=[]
    for keys,g in e.groupby(groupcols,dropna=False,observed=True):
        if not isinstance(keys,tuple): keys=(keys,)
        row={k:v for k,v in zip(groupcols,keys)}
        row["n"]=g.event_id.nunique()
        for h in H:
            v=g[f"net_{h}h"].dropna()
            row[f"avg_{h}h"]=v.mean() if len(v) else np.nan
            row[f"win_{h}h"]=(v>0).mean() if len(v) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

def matched_diff(e, strata):
    pieces=[]
    for keys,g in e.groupby(strata,dropna=False,observed=True):
        if not isinstance(keys,tuple): keys=(keys,)
        t=g[g.target]; c=g[~g.target]
        if len(t)==0 or len(c)==0: continue
        row={k:v for k,v in zip(strata,keys)}
        row["target_n"]=len(t); row["control_n"]=len(c)
        for h in H:
            a=t[f"net_{h}h"].mean(); b=c[f"net_{h}h"].mean()
            row[f"diff_{h}h"]=a-b
        pieces.append(row)
    d=pd.DataFrame(pieces)
    s=[]
    for h in H:
        if d.empty: s.append({"horizon":h,"matched_strata":0,"target_weighted_diff":np.nan}); continue
        v=d.dropna(subset=[f"diff_{h}h"])
        if v.empty: s.append({"horizon":h,"matched_strata":0,"target_weighted_diff":np.nan}); continue
        w=v.target_n.to_numpy(float); z=v[f"diff_{h}h"].to_numpy(float)
        s.append({"horizon":h,"matched_strata":len(v),"target_weighted_diff":float(np.average(z,weights=w)),
                   "target_n_in_matched_strata":int(w.sum())})
    return d,pd.DataFrame(s)

def wf(e):
    rows=[]
    for a,b,y in SPLITS:
        tr=e[(e.year>=a)&(e.year<=b)]
        va=e[e.year==y]
        candidates=[]
        for target in [True,False]:
            g=tr[tr.target==target]
            if len(g)>=5:
                candidates.append((target,g.net_12h.mean(),len(g)))
        # Fixed pre-registered target is not selected here; this is coverage/incremental audit.
        for h in H:
            t=va[va.target]; a=va[va.target & va.anchor]; v=va[va.anchor]
            rows.append({"train":f"{a}-{b}","validation":y,"horizon":h,
                         "target_n":len(t),"anchor_n":len(v),"target_anchor_n":len(a),
                         "target_avg":t[f"net_{h}h"].mean() if len(t) else np.nan,
                         "anchor_avg":v[f"net_{h}h"].mean() if len(v) else np.nan,
                         "target_anchor_avg":a[f"net_{h}h"].mean() if len(a) else np.nan})
    return pd.DataFrame(rows)

def main():
    x=enrich(add_indicators(fetch_klines()))
    e=add_bins(build(x))
    if len(e)!=95: raise RuntimeError(f"Frozen event count changed: {len(e)}")
    e.to_csv(R/"bb_decomposition_redundancy_events.csv",index=False)
    group_summary(e,["target_label","anchor_label"]).to_csv(R/"bb_decomposition_redundancy_target_volume.csv",index=False)
    group_summary(e,["target_label","atr_bin"]).to_csv(R/"bb_decomposition_redundancy_target_atr.csv",index=False)
    group_summary(e,["target_label","bb_bin"]).to_csv(R/"bb_decomposition_redundancy_target_bb.csv",index=False)
    for name,strata in {
        "year_atr":["year","atr_bin"],
        "year_bb":["year","bb_bin"],
        "year_anchor":["year","anchor_label"],
        "year_atr_anchor":["year","atr_bin","anchor_label"],
        "year_bb_anchor":["year","bb_bin","anchor_label"],
    }.items():
        d,s=matched_diff(e,strata)
        d.to_csv(R/f"bb_decomposition_redundancy_match_{name}.csv",index=False)
        s.to_csv(R/f"bb_decomposition_redundancy_match_{name}_summary.csv",index=False)
    wf(e).to_csv(R/"bb_decomposition_redundancy_oos_coverage.csv",index=False)
    report={"events":len(e),"target_count":int(e.target.sum()),"anchor_count":int(e.anchor.sum()),
            "target_anchor_count":int((e.target&e.anchor).sum()),
            "definition":"target = pre-reentry BB mid slope flat (-0.50..0.50 ATR) AND BB width slope expanding (>=0.50 ATR); volume anchor = reentry vol_z20 >=1.0",
            "cost":COST,"status":"research_only",
            "interpretation":"Redundancy/matched-control audit; no threshold search and no deployment inference."}
    (R/"bb_decomposition_redundancy_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print("\nTARGET x VOLUME\n",group_summary(e,["target_label","anchor_label"]).to_string(index=False))
    print("\nMATCH year x ATR\n",pd.read_csv(R/"bb_decomposition_redundancy_match_year_atr_summary.csv").to_string(index=False))
    print("\nMATCH year x BB\n",pd.read_csv(R/"bb_decomposition_redundancy_match_year_bb_summary.csv").to_string(index=False))
    print("\nMATCH year x ATR x volume\n",pd.read_csv(R/"bb_decomposition_redundancy_match_year_atr_anchor_summary.csv").to_string(index=False))
    print("\nMATCH year x BB x volume\n",pd.read_csv(R/"bb_decomposition_redundancy_match_year_bb_anchor_summary.csv").to_string(index=False))
    print("\nOOS COVERAGE\n",wf(e).to_string(index=False))

if __name__=="__main__": main()

# trigger refresh
