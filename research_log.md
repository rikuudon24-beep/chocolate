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
- OOS-002b: 1Dレジーム分解 — DONE※暫定
- OOS-AUDIT-001: 正本データ監査 — IN PROGRESS
- OOS-003: 全イベント出口比較 — TODO
- OOS-004: パラメータ近傍ロバストネス — TODO

## Frozen provisional counts
Previous exploratory pipelines produced 85 and 113 events. These are provisional only and must not be treated as the audited event count.

## OOS-AUDIT-001 frozen specification
- Symbol: BTCUSDT Spot
- Interval: 4h
- Timezone: UTC
- Period: 2020-01-01 through the latest fully closed 4H candle within 2026-09-28
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
