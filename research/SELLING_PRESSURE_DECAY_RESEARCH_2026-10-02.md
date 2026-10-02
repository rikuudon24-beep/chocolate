# Selling Pressure Decay Research — 2026-10-02

## Purpose
Test whether the fixed 95-event BTCUSDT 4H setup contains a repeatable pre-entry signature in which downside pressure weakens from Bollinger re-entry to RSI recovery confirmation.

## Frozen denominator
- BTCUSDT Spot, 4H, UTC
- Same frozen OOS event definition as research/BTC_RESEARCH_HANDOFF_2026-10-02.md
- Expected events: 95
- Cost: 0.10% round trip
- Horizons: 2 / 3 / 6 / 12 bars
- Walk-forward splits: 2020-22 -> 2023; 2020-23 -> 2024; 2020-24 -> 2025; 2020-25 -> 2026

## Pre-registered feature
downside_pressure = max(vol_z20, 0) * max(open-close, 0) / (high-low)

This combines abnormal volume with bearish candle-body intensity. It is deliberately different from raw volume alone.

## Fixed categories
1. strong_decay: confirmation pressure <= 50% of re-entry pressure, with positive re-entry pressure.
2. decay: confirmation pressure <= 85% of re-entry pressure, excluding strong decay.
3. increasing: confirmation pressure >= 150% of re-entry pressure, with positive re-entry pressure.
4. low_pressure: confirmation pressure <= 0.25 and pressure ratio <= 1.0, after higher-priority categories.
5. persistent: remaining classified events.

No thresholds are selected from outcome data.

## Information boundary
Re-entry and confirmation candles are closed before the next-candle entry, so their OHLCV information is available at the entry decision. Entry-candle pressure is retained only as a diagnostic and cannot affect selection.

## Validation
For each rolling split, select the category with the highest training mean 12-bar net return among categories with at least 3 training events. Apply that category unchanged to the validation year and inspect 2/3/6/12-bar results.

## Interpretation rule
This is a research diagnostic, not a deployment rule. Small samples, regime dependence, overlapping effects, and selection artifacts must be treated as threats to validity.

## Status
**HOLD / research-only until exact GitHub Actions results are available.**
