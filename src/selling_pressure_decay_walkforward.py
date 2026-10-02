import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_oos import fetch_klines, add_indicators, extract_events

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

HORIZONS = [2, 3, 6, 12]
COST = 0.001
SPLITS = [(2020, 2022, 2023), (2020, 2023, 2024),
          (2020, 2024, 2025), (2020, 2025, 2026)]


def add_pressure_features(df):
    x = df.copy()
    rng = (x["high"] - x["low"]).replace(0, np.nan)
    bearish_body_frac = ((x["open"] - x["close"]).clip(lower=0) / rng).fillna(0)
    lower_wick_frac = ((np.minimum(x["open"], x["close"]) - x["low"]).clip(lower=0) / rng).fillna(0)
    red = (x["close"] < x["open"]).astype(float)

    x["bear_body_frac"] = bearish_body_frac
    x["lower_wick_frac"] = lower_wick_frac
    x["red_volume_flag"] = red
    # Positive score only when volume is above its 20-candle baseline.
    x["downside_pressure"] = x["vol_z20"].clip(lower=0) * bearish_body_frac
    x["downside_effort"] = x["volume"] * bearish_body_frac
    x["red_volume_z"] = x["vol_z20"] * red
    return x


def classify(decay_ratio, reentry_pressure, confirmation_pressure, delay_h):
    # Fixed definitions registered before outcome inspection.
    if pd.isna(reentry_pressure) or pd.isna(confirmation_pressure):
        return "unclassified"
    if reentry_pressure <= 0 and confirmation_pressure <= 0.25:
        return "low_pressure"
    if reentry_pressure > 0 and pd.notna(decay_ratio) and confirmation_pressure <= reentry_pressure * 0.50:
        return "strong_decay"
    if reentry_pressure > 0 and pd.notna(decay_ratio) and confirmation_pressure <= reentry_pressure * 0.85:
        return "decay"
    if reentry_pressure > 0 and pd.notna(decay_ratio) and confirmation_pressure >= reentry_pressure * 1.50:
        return "increasing"
    if confirmation_pressure <= 0.25 and (reentry_pressure <= 0 or decay_ratio <= 1.0):
        return "low_pressure"
    return "persistent"


def main():
    df = add_indicators(fetch_klines())
    df["vol_z20"] = (
        (df["volume"] - df["volume"].rolling(20).mean())
        / df["volume"].rolling(20).std(ddof=0)
    )
    df = add_pressure_features(df)

    events = extract_events(df)
    if len(events) != 95:
        raise RuntimeError(f"frozen event mismatch: {len(events)} != 95")

    rows = []
    for _, e in events.iterrows():
        re_idx = int(df.index[df["open_time"] == pd.Timestamp(e["reentry_time"])][0])
        cf_idx = int(df.index[df["open_time"] == pd.Timestamp(e["confirmation_time"])][0])
        en_idx = int(df.index[df["open_time"] == pd.Timestamp(e["entry_time"])][0])
        entry = float(e["entry_price"])

        rp = float(df.iloc[re_idx]["downside_pressure"])
        cp = float(df.iloc[cf_idx]["downside_pressure"])
        ep = float(df.iloc[en_idx]["downside_pressure"])  # diagnostic only: known after entry candle closes
        ratio = (cp / rp) if rp > 0 else np.nan
        cat = classify(ratio, rp, cp, (cf_idx - re_idx) * 4)

        re_red = float(df.iloc[re_idx]["red_volume_flag"])
        cf_red = float(df.iloc[cf_idx]["red_volume_flag"])
        red_path = float(df.iloc[re_idx:cf_idx + 1]["red_volume_flag"].mean())

        for h in HORIZONS:
            j = en_idx + h - 1
            if j >= len(df):
                continue
            ret = float(df.iloc[j]["close"] / entry - 1)
            rows.append({
                "event_id": int(e["event_id"]),
                "year": int(pd.Timestamp(e["entry_time"]).year),
                "reentry_pressure": rp,
                "confirmation_pressure": cp,
                "entry_pressure_diagnostic": ep,
                "pressure_ratio": ratio,
                "reentry_red": re_red,
                "confirmation_red": cf_red,
                "red_candle_fraction": red_path,
                "category": cat,
                "horizon": h,
                "gross_return": ret,
                "net_return": ret - COST,
            })

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "selling_pressure_decay_events.csv", index=False)

    summary = (
        out.groupby(["category", "horizon"])
        .agg(
            n=("event_id", "size"),
            avg_net=("net_return", "mean"),
            median_net=("net_return", "median"),
            win=("net_return", lambda s: (s > 0).mean()),
            pf=("net_return", lambda s: s[s > 0].sum() / (-s[s < 0].sum()) if (s < 0).any() else np.inf),
        )
        .reset_index()
    )
    summary.to_csv(RESULTS / "selling_pressure_decay_summary.csv", index=False)
    print("=== CATEGORY COUNTS ===")
    print(out[["event_id", "category"]].drop_duplicates()["category"].value_counts(dropna=False).to_string())

    # Walk-forward: category is selected only from training data using 12h mean net return.
    cats = ["strong_decay", "decay", "low_pressure", "increasing", "persistent"]
    wf = []
    for a, b, vy in SPLITS:
        train = out[(out.year >= a) & (out.year <= b) & (out.horizon == 12)]
        scores = []
        for cat in cats:
            z = train[train.category == cat]["net_return"]
            if len(z) >= 3:
                scores.append((float(z.mean()), float(z.median()), cat, len(z)))
        scores.sort(reverse=True)
        selected = scores[0][2] if scores else "none"
        train_n = scores[0][3] if scores else 0
        for h in HORIZONS:
            va = out[(out.year == vy) & (out.horizon == h) & (out.category == selected)] if selected != "none" else out.iloc[0:0]
            wf.append({
                "train": f"{a}-{b}", "validation": vy,
                "selected_category": selected, "train_n": train_n,
                "horizon": h, "validation_n": len(va),
                "validation_avg_net": float(va.net_return.mean()) if len(va) else np.nan,
                "validation_median_net": float(va.net_return.median()) if len(va) else np.nan,
                "validation_win": float((va.net_return > 0).mean()) if len(va) else np.nan,
            })
    walk = pd.DataFrame(wf)
    walk.to_csv(RESULTS / "selling_pressure_decay_walkforward.csv", index=False)

    audit = {
        "events": len(events),
        "cost_round_trip": COST,
        "horizons": HORIZONS,
        "definition": {
            "downside_pressure": "max(vol_z20, 0) * max(open-close, 0) / (high-low)",
            "strong_decay": "re-entry pressure > 0 and confirmation pressure <= 50% of re-entry",
            "decay": "re-entry pressure > 0 and confirmation pressure <= 85% of re-entry, excluding strong_decay",
            "increasing": "re-entry pressure > 0 and confirmation pressure >= 150% of re-entry",
            "low_pressure": "confirmation pressure <= 0.25 and (re-entry pressure <= 0 or pressure ratio <= 1.0), after higher-priority categories",
            "persistent": "all remaining classified events",
        },
        "live_information_boundary": "Selection features use re-entry and confirmation candles, both closed before next-candle entry. Entry-candle pressure is diagnostic only and is never used for category selection.",
        "walkforward": "Each split selects the category with highest training mean 12h net return among categories with >=3 events, then validates at 2/3/6/12h.",
        "status": "research_only",
    }
    (RESULTS / "selling_pressure_decay_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("=== SUMMARY ===")
    print(summary.to_string(index=False))
    print("=== WALKFORWARD ===")
    print(walk.to_string(index=False))


if __name__ == "__main__":
    main()
