import numpy as np
import pandas as pd
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
N_BOOT = 10000
SEED = 20260928

def pf(x):
    gains = x[x > 0].sum()
    losses = -x[x < 0].sum()
    return gains / losses if losses > 0 else np.nan

def bootstrap_event_returns(x, rng, n_boot=N_BOOT):
    x = np.asarray(x, dtype=float)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    samples = x[idx]
    avg = samples.mean(axis=1)
    win = (samples > 0).mean(axis=1)
    pfv = np.array([pf(row) for row in samples])
    return avg, win, pfv

def bootstrap_year_blocks(detail, rng, n_boot=N_BOOT):
    years = sorted(detail["validation_year"].unique())
    grouped = {y: detail.loc[detail.validation_year == y, "return"].to_numpy(float) for y in years}
    out = []
    for _ in range(n_boot):
        sampled_years = rng.choice(years, size=len(years), replace=True)
        vals = np.concatenate([grouped[y] for y in sampled_years])
        out.append(vals)
    arr = np.array(out, dtype=object)
    return arr

def ci(v):
    return float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))

def main():
    detail = pd.read_csv(RESULTS / "oos_walkforward_events.csv")
    rng = np.random.default_rng(SEED)
    rows = []

    for horizon, g in detail.groupby("horizon"):
        base = g["return"].to_numpy(float)
        for cost in [0.0, 0.0005, 0.0010, 0.0015]:
            x = base - cost
            avg, win, pfv = bootstrap_event_returns(x, rng)
            lo, hi = ci(avg)
            wlo, whi = ci(win)
            rows.append({
                "horizon": int(horizon), "round_trip_cost": cost,
                "method": "event_bootstrap", "n": len(x),
                "point_avg_return": float(x.mean()), "avg_return_ci_low": lo,
                "avg_return_ci_high": hi, "point_win_rate": float((x > 0).mean()),
                "win_rate_ci_low": wlo, "win_rate_ci_high": whi,
                "point_profit_factor": pf(x),
                "profit_factor_ci_low": ci(pfv)[0], "profit_factor_ci_high": ci(pfv)[1],
                "bootstrap_reps": N_BOOT
            })

        years = sorted(g["validation_year"].unique())
        by_year = [g.loc[g.validation_year == y, "return"].to_numpy(float) - 0.0005 for y in years]
        block_rows = []
        for _ in range(N_BOOT):
            sampled = rng.choice(len(years), size=len(years), replace=True)
            vals = np.concatenate([by_year[i] for i in sampled])
            block_rows.append((vals.mean(), (vals > 0).mean(), pf(vals)))
        b = np.asarray(block_rows, float)
        rows.append({
            "horizon": int(horizon), "round_trip_cost": 0.0005,
            "method": "year_block_bootstrap", "n": len(g),
            "point_avg_return": float(g["return"].mean() - 0.0005),
            "avg_return_ci_low": float(np.quantile(b[:,0], 0.025)),
            "avg_return_ci_high": float(np.quantile(b[:,0], 0.975)),
            "point_win_rate": float(((g["return"] - 0.0005) > 0).mean()),
            "win_rate_ci_low": float(np.quantile(b[:,1], 0.025)),
            "win_rate_ci_high": float(np.quantile(b[:,1], 0.975)),
            "point_profit_factor": pf(g["return"].to_numpy(float) - 0.0005),
            "profit_factor_ci_low": float(np.quantile(b[:,2], 0.025)),
            "profit_factor_ci_high": float(np.quantile(b[:,2], 0.975)),
            "bootstrap_reps": N_BOOT
        })

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "oos_walkforward_bootstrap.csv", index=False)
    print(out.to_string(index=False))

if __name__ == "__main__":
    main()
