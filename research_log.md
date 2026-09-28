# Research Log

## Status
- DONE: tested and completed
- HOLD: tested but not enough evidence / awaiting validation
- REJECT: tested and rejected
- TODO: not yet tested

## Existing research
- BB-LONG-001: BB単独 — DONE / REJECT
- BB-LONG-002: BB再入場 — DONE
- BB-LONG-003: BB + RSI — HOLD
- BB-LONG-004: 下ヒゲ — REJECT / HOLD
- BB-LONG-005: 新安値なし — DONE
- BB-LONG-006: ADX — HOLD / REJECT
- BB-LONG-007: コスト調整 — DONE
- BB-LONG-008: WAIT比較 — DONE
- BB-LONG-009: FAIL / NO-GO — DONE
- BB-LONG-010: EXIT探索 — HOLD
- OOS-001: 長期OOS — HOLD
- OOS-002b: 1Dレジーム分解 — DONE※暫定・再現仕様未固定
- OOS-AUDIT-001: 正本データ監査 — DONE※暫定
- OOS-003: 全イベント出口比較 — DONE※暫定
- OOS-004: パラメータ近傍ロバストネス — DONE※市場反応指標として
- OOS-005: コスト感度・イベント独立性 — DONE※暫定
- OOS-006: 1Dレジーム分解の再検証 — DONE※仕様v1を事前固定
- OOS-007: 構造的失敗条件の再検証 — DONE※暫定
- OOS-008: 最終OOSレビュー — DONE※独立検証前のHOLD
- OOS-009: 固定仕様・時系列ウォークフォワード検証 — DONE※暫定

## Frozen provisional counts
Previous exploratory pipelines produced 85 and 113 events. These are provisional only and must not be treated as the audited event count.

## OOS-AUDIT-001 frozen specification
- Symbol: BTCUSDT Spot
- Interval: 4h
- Timezone: UTC
- Period: 2020-01-01 through 2026-09-27 16:00 UTC (frozen cutoff)
- Source: Binance public Spot Kline API
- Closed candles only
- Validate duplicate open times
- Validate 4-hour spacing and missing intervals
- Validate basic OHLC consistency
- Recalculate BB(20,2) and RSI(14)
- Detect one independent event at a time
- No future information may influence entry confirmation
- Save the audit summary and event table

## Frozen entry candidate
1. Previous close below lower BB
2. Current close re-enters the lower BB
3. RSI at re-entry < 40
4. Within at most 6 following candles, RSI recovers by >= 5 points from the running minimum
5. No new low versus the re-entry candle before confirmation
6. No lower-BB re-break before confirmation
7. Entry at the next 4H open after confirmation

## OOS rules
- Do not tune parameters after inspecting OOS results.
- Do not count overlapping confirmations as separate independent events.
- Keep market reaction metrics separate from strategy P&L.
- If an OHLC candle cannot establish intrabar order between conflicting exit/stop conditions, classify it as ambiguous rather than choosing the favorable interpretation.

## Handoff checkpoint — 2026-09-28
- OOS-AUDIT-001: DONE※暫定 / official Binance series frozen as primary source.
- Audited data: 14,770 closed BTCUSDT 4H candles, 2020-01-01 through 2026-09-27 16:00 UTC.
- Duplicates: 0. OHLC inconsistencies: 0. Spacing errors: 1. No secondary repair is applied.
- Audited independent event count: 95. Event-year counts: 2020=12, 2021=11, 2022=19, 2023=14, 2024=12, 2025=16, 2026=11.
- OOS-003: DONE※provisional. Full 95-event denominator exit comparison exists in results/oos_exit_summary.csv. No exit is adopted yet. RSI50 aggregate avg return -0.259%, PF 0.831; BB-middle -0.455%, PF 0.694; 8H fixed-time +0.034%, PF 1.058.
- OOS-004: DONE※provisional. Corrected event generator now matches the frozen audit logic. Tested recovery deltas +3 through +8 and horizons 2/3/6/12 candles. Results are market-reaction measurements, not adopted strategy P&L. The +5 / 12-candle result is +0.377% average in the robustness table, but this must NOT be interpreted as a tradable 48h strategy result because it does not apply the structural failure/exit logic used by OOS-003.
- OOS-005: DONE※provisional. Using the full 95-event exit table, fixed-time 2-candle average return is +0.034% before costs and falls to -0.016% at 0.05% round-trip cost, -0.066% at 0.10%, and -0.116% at 0.15%. Other tested exits are already negative before costs. Therefore the small raw 2-candle edge is cost-sensitive.
- Event independence audit: consecutive audited event gaps are mostly long (median 364h; mean 608.9h). 2 gaps are <24h, 5 are <48h, 10 are <72h, 14 are <96h. This does not prove statistical independence, but dense clustering is limited in the frozen 95-event set.
- Important correction: OOS-004 robustness horizon returns and OOS-003 strategy exits are different measurements. Do not compare them as if they were the same P&L definition.
- OOS-006 next: reconstruct and freeze the exact 1D regime specification before interpreting regime effects.
- OOS-007 next: test structural failure handling and close-vs-intrabar ambiguity.
- Research principle: never overwrite earlier exploratory results silently; preserve discrepancies and mark invalid/provisional runs explicitly.


## OOS-006 / OOS-007 / OOS-008 final checkpoint — 2026-09-28
- The OOS dataset cutoff is now explicitly frozen at 2026-09-27 20:00 UTC exclusive (last included candle open: 2026-09-27 16:00 UTC). This prevents later closed candles from silently changing historical OOS results.
- OOS-006 regime specification v1 is frozen: BULL = daily close > SMA200 and daily RSI14 >= 50; BEAR = daily close < SMA200 and daily RSI14 < 50; otherwise NEUTRAL.
- OOS-006 event allocation: BEAR 45, BULL 18, NEUTRAL 32. Neutral-regime returns are negative across every tested exit in the frozen sample; no regime filter is adopted because this is a partition of the same OOS sample, not independent validation.
- OOS-007 structural failure comparison: structural stops lower average return for every tested exit. They reduce the worst individual trade in the sample but do not improve sequential max drawdown in the tested definitions. Ambiguous cases = 0.
- OOS-008 final review: HOLD / not deployment-ready. The tested exit set has no durable positive net edge after plausible costs; the small fixed-2-candle raw edge is cost-sensitive. Robustness is sensitive to recovery threshold and horizon.
- Full final review is stored in results/oos_final_review.md.
- Next research requirement: independent validation design (time-separated OOS or walk-forward), not further tuning on this frozen sample.


## OOS-009 checkpoint — 2026-09-28
- Validation design is fixed-spec and time-separated: validate 2023 after training window through 2022; 2024 after 2023; 2025 after 2024; 2026 after 2025.
- No parameters are fitted from the training windows. The purpose is stability testing of the already-frozen entry specification, not post-hoc optimization.
- Validation events: 2023=14, 2024=12, 2025=16, 2026=11; total 53.
- Aggregate fixed-time reaction across all validation years: 2 candles avg +0.251%, 3 candles +0.385%, 6 candles +0.021%, 12 candles +0.824%.
- Aggregate figures are before costs and remain market-reaction measurements rather than adopted strategy P&L.
- Annual consistency is mixed: 2025 is negative at 2/3/6 candles while 2023/2024/2026 are generally positive at several horizons. Therefore the effect is not yet demonstrated as stable across regimes.
- At 0.05% round-trip cost, aggregate average return mechanically falls by 0.05 percentage points for every horizon; the 6-candle aggregate becomes slightly negative.
- OOS-009 does not justify selecting a particular exit horizon. Exit choice remains HOLD pending a pre-specified independent decision rule and further validation.


## OOS-010 checkpoint — 2026-09-28
- Added fixed-spec uncertainty analysis for the OOS-009 validation events. This does not alter the entry rule, exit rule, or validation cutoff.
- Event bootstrap uses 10,000 deterministic resamples per horizon/cost level; a separate year-block bootstrap is reported at 0.05% round-trip cost to show sensitivity to year-level dependence.
- Confidence intervals are descriptive uncertainty ranges, not proof of future performance and not a basis for selecting a horizon after the fact.
- The analysis is intentionally run after the fixed walk-forward outputs and cannot modify the frozen event set or parameters.


## Forward-shadow design checkpoint — 2026-09-28
- Added a separate forward-shadow validation path that only evaluates events at or after the frozen OOS cutoff (2026-09-27 20:00 UTC).
- Historical OOS outputs remain frozen; forward-shadow observations are stored separately and cannot alter the 95-event audited denominator.
- Returns are reported only after the fixed 2/3/6/12-candle horizons have fully matured. No parameter fitting or exit selection is performed.
- This is intended to become the genuinely untouched validation stream as new closed BTCUSDT 4H candles arrive.

- Automation note — after the prior run completed, the branch was re-triggered so the current workflow definition (including uncertainty and forward-shadow stages) can execute against the settled main branch.


## OOS-010 results — 2026-09-28
- The fixed-spec bootstrap completed successfully on the same 53 validation events. At 0.05% round-trip cost, the 95% event-bootstrap CI for average return crosses zero for every tested horizon: 2 candles [-0.263%, +0.680%], 3 [-0.186%, +0.855%], 6 [-0.712%, +0.617%], 12 [-0.332%, +1.779%].
- Therefore the positive point estimates at 2/3/12 candles are not statistically decisive in this small validation sample; uncertainty remains material.
- The year-block bootstrap at 0.05% gives positive average-return intervals for all four horizons, but it is based on only four validation years and should be treated as descriptive, not confirmatory.
- Untouched forward-shadow scan found 0 events at or after the frozen 2026-09-27 20:00 UTC cutoff and 0 matured horizon returns. This is expected immediately after the cutoff and is not evidence for or against the rule.
- OOS-010 strengthens the HOLD decision: no exit horizon is selected and no live deployment is authorized by this research stage.


## Forward-shadow implementation correction — 2026-09-28
- Corrected the forward-shadow data path: it now fetches closed BTCUSDT 4H candles from the frozen cutoff forward using the live Binance public API, instead of reusing the historical frozen-data fetch whose endpoint stops at the OOS cutoff.
- The historical audit remains frozen; only the separate forward-shadow stream is allowed to advance with new candles.
