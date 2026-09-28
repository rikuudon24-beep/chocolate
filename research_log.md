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
