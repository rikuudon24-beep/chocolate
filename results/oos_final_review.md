# OOS-008 Final Review

## Frozen research scope
- Symbol: BTCUSDT Spot
- Interval: 4h
- Timezone: UTC
- Frozen cutoff: 2026-09-27 16:00 UTC last open candle
- Source: Binance public Spot Kline API
- Candles: 14,770
- Duplicate open times: 0
- OHLC inconsistency rows: 0
- 4h spacing errors: 1
- Secondary gap repairs: none
- Independent entry events: 95
- Event counts by event year: 2020=12, 2021=11, 2022=19, 2023=14, 2024=12, 2025=16, 2026=11

## Entry specification
1. Previous close below lower BB.
2. Current close re-enters the lower BB.
3. RSI(14) at re-entry < 40.
4. Within at most 6 following candles, RSI recovers >= 5 points from its running minimum.
5. No new low versus the re-entry candle before confirmation.
6. No lower-BB re-break before confirmation.
7. Entry at the next 4H open after confirmation.

## OOS-003 exit research
All 95 events were evaluated under the same denominator.
- RSI48: average return -0.287%, PF 0.804
- RSI50: average return -0.259%, PF 0.831
- RSI52: average return -0.200%, PF 0.876
- BB middle: average return -0.455%, PF 0.694
- Fixed 2-candle exit: average return +0.034%, PF 1.058
- Fixed 3-candle exit: average return -0.051%, PF 0.942
- Fixed 6-candle exit: average return -0.420%, PF 0.700
- Fixed 12-candle exit: average return -0.299%, PF 0.832
- Ambiguous exit/stop candles: 0 in the tested exit set.

The small positive fixed 2-candle result is not robust to transaction costs: approximately -0.016% at 0.05% round-trip cost, -0.066% at 0.10%, and -0.116% at 0.15%.

## OOS-004 robustness
The robustness table measures market reaction after the frozen event definition; it is not adopted strategy P&L.
- Recovery +5 / 2 candles: +0.096% average
- Recovery +5 / 3 candles: +0.076%
- Recovery +5 / 6 candles: -0.322%
- Recovery +5 / 12 candles: +0.377%
- Increasing the recovery threshold from +5 to +8 reduces event count from 95 to 64 while the 12-candle reaction becomes more positive. This is selection-sensitive and is not treated as evidence that +8 is superior.

## OOS-006 1D regime research
Frozen regime definition:
- BULL: daily close > SMA200 and daily RSI14 >= 50
- BEAR: daily close < SMA200 and daily RSI14 < 50
- NEUTRAL: otherwise

Event allocation:
- BEAR: 45
- BULL: 18
- NEUTRAL: 32

The neutral regime produced negative average returns across every tested exit in the regime table, while bull and bear regimes were generally less negative or positive. This is evidence of regime dependence, but the same 95-event OOS sample is being partitioned rather than independently validated. No regime filter is adopted from this result alone.

## OOS-007 structural failure research
Structural stop conditions were compared with the same exits without the structural stop.
- RSI exits: structural stops reduce average return by about 0.44–0.54 percentage points.
- BB-middle: reduce average return by about 0.51 percentage points.
- Time exits: effect is smaller, about 0.08–0.15 percentage points for 2–3 candles and about 0.45 percentage points at 12 candles.
- Ambiguous cases: 0.

The structural stop materially reduces the worst individual trade in this sample, but it does not reduce the sequential max drawdown under the tested exit definitions. For example, with RSI50 the worst trade changes from -15.44% without the stop to -9.99% with it, while the measured sequential max drawdown is -24.21% without the stop versus -42.17% with it. Because the stop changes trade timing and the exit sequence, these drawdown figures are descriptive rather than a fully optimized portfolio statistic.

Overall, the structural failure rule behaves primarily as a risk-control mechanism in this frozen sample, not as a proven source of positive expectancy.

## Final status
Research status: HOLD / not deployment-ready.

Reason:
1. The core entry event is reproducible on a frozen 4H BTCUSDT dataset.
2. The tested exits do not show a durable positive net edge after plausible costs.
3. The only positive aggregate exit result is a very small 8-hour fixed-time effect that is cost-sensitive.
4. Robustness results show sensitivity to recovery threshold and holding horizon.
5. Regime decomposition indicates strong context dependence, but it is not an independent validation set.
6. Structural failure handling reduces tail risk but also reduces average return in the tested sample.
7. The frozen dataset contains one 4H spacing error; no repair was applied.

No live trading rule is promoted from OOS-008. The next research step should be a genuinely independent validation design (for example, a time-separated validation window or walk-forward protocol) before any deployment decision.
