# Volume Trajectory Research — 2026-10-02

## Status
Implemented and queued for GitHub Actions execution. No result is promoted from the static cache.

## Frozen scope
- BTCUSDT Spot
- 4h UTC
- Frozen OOS cutoff: 2026-09-27 20:00 UTC exclusive
- Frozen event denominator: 95
- Cost: 0.10% round trip
- Horizons: 2/3/6/12h
- Walk-forward splits: 2020-22→2023, 2020-23→2024, 2020-24→2025, 2020-25→2026

## Fixed trajectory categories
Priority order:
1. sharply_decreases: confirmation z20 <= re-entry z20 - 0.5 AND entry z20 <= re-entry z20 - 1.0
2. decreases_then_reincreases: confirmation z20 <= re-entry z20 - 0.5 AND entry z20 >= confirmation z20 + 0.5
3. increasing: confirmation z20 >= re-entry z20 + 0.5 AND entry z20 >= confirmation z20 - 0.25
4. remains_elevated: all three z20 values >= 1.0
5. other: none of the above

Thresholds are fixed and are not optimized from outcomes.

## Important timing audit
Full entry-candle volume is not known at the entry open. Therefore categories using entry-candle volume are diagnostic unless execution is explicitly delayed until that candle closes. The workflow records this limitation and does not present the category as deployment-ready.

## Implementation
- src/volume_trajectory_walkforward.py
- .github/workflows/volume_trajectory.yml
- Results expected:
  - results/volume_trajectory_events.csv
  - results/volume_trajectory_summary.csv
  - results/volume_trajectory_walkforward.csv
  - results/volume_trajectory_audit.json

## Data-source audit
The frozen research source remains Binance public Spot Kline data. Binance documents GET /api/v3/klines as public market data and identifies klines by open time. The independent static-klines cache was inspected as a secondary check, but its volume z-scores did not reproduce the frozen 34-event volume-anchor count, so it is not used for the final result.

## Current decision
HOLD. No deployment recommendation. Await the exact-Binance workflow result before interpreting the trajectory categories.
