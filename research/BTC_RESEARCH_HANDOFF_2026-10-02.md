# Research Handoff — 2026-10-02

## Purpose
This document is the handoff point for the ongoing autonomous market-pattern research project.
The repository title/README intentionally remain unobvious; do not expose the underlying research theme in repository-facing metadata.

## Current decision
**HOLD / not deployment-ready.**
Do not move to live trading or recommend real-money deployment without explicit user approval.

## Frozen OOS audit
- Symbol: BTCUSDT Spot
- Interval: 4h
- Timezone: UTC
- Source: Binance public Spot Kline API
- Frozen cutoff: 2026-09-27 20:00 UTC exclusive
- Last included candle: 2026-09-27 16:00 UTC
- Closed candles: 14,770
- Duplicate opens: 0
- OHLC inconsistencies: 0
- 4h spacing errors: 1
- Independent event denominator: 95
- Event years: 2020=12, 2021=11, 2022=19, 2023=14, 2024=12, 2025=16, 2026=11

## Frozen entry candidate
1. Previous close below lower Bollinger Band.
2. Current close re-enters lower Bollinger Band.
3. RSI(14) at re-entry < 40.
4. Within <=6 following candles, RSI recovers >=5 points from running minimum.
5. No new low vs re-entry candle before confirmation.
6. No lower-BB re-break before confirmation.
7. Entry at next 4h open after confirmation.

Rules:
- No tuning after OOS inspection.
- No overlapping confirmations as independent events.
- Market-reaction metrics and strategy P&L are kept separate.
- Ambiguous intrabar OHLC conflicts are never interpreted favorably.
- Exact frozen event extraction must be preserved.

## Main historical findings
- Base candidate has no durable positive net edge after plausible costs.
- Fixed 2-candle raw reaction was only +0.0339% average; after 0.05% cost it becomes -0.0161%.
- Walk-forward fixed-spec reaction:
  - 2h +0.2514%
  - 3h +0.3848%
  - 6h +0.0213%
  - 12h +0.8239%
  across 53 validation events, but 2025 was weak at 2/3/6h.
- Event bootstrap 95% CIs cross zero for all tested horizons.
- Structural stops reduced individual losses but worsened sequential max DD and average return.
- Therefore the base setup remains HOLD.

## Volume shock finding
A fixed pre-entry feature, re-entry volume z-score over 20 periods:
**vol_z20_reentry >= 1.0**
has repeatedly looked more promising than most other static filters.

Historical anchor count:
2020=4, 2021=2, 2022=7, 2023=6, 2024=7, 2025=3, 2026=5; total 34.

Matched stratified controls (same historical sample):
- year x RSI: +0.7952%, +0.2912%, +0.4278%, +0.9675% weighted differences at 2/3/6/12h
- year x ATR: +0.9491%, +0.7094%, +0.8441%, +1.6031%
- year x BB width: +0.9605%, +0.6130%, +0.4536%, +0.7097%
These are descriptive, not independent OOS proof.

Volume-anchor path timing also looked stronger:
- At 12h, +0.5% before -0.5%: 35.29% vs base 31.15%
- MAE before +0.5%: 23.53% vs base 40.98%
- +0.5% hit: 94.12% vs base 85.25%
Again descriptive/path-conditioned, not proof.

## Fixed 5-condition rule investigated
Conditions:
- reentry volume z20 >= 1
- reentry RSI >= 30
- reentry BB width <= 0.12
- reentry ATR% < 0.02
- entry volume z20 >= 0
12h close return, 0.10% round-trip cost.

Full historical same-sample:
- n=8
- avg net +1.1406%
- win 50.0%
- PF 4.3087

Ablation:
- remove reentry volume condition: n25, avg +0.3184%, PF 1.3584
- remove reentry RSI: n9, avg +0.9546%, PF 3.6111
- remove BB width: unchanged n8/results
- remove ATR: unchanged n8/results
- remove entry-volume condition: n16, avg -0.2046%, PF 0.8142

Leave-one-year-out remained positive in this same-sample diagnostic, but n is only 5–8.
**Do not promote this rule.** It is retrospective/descriptive and has no independent OOS confirmation.

## Walk-forward failure-filter result
Fixed candidate filters included:
- none
- RSI reentry >=30
- BB width <=0.12
- ATR% <0.02
- entry volume z20 >=0
- combinations

Horizon 12h, cost 0.10%, training-only selection.

The same filter **entry_vol_z >= 0** was selected in all four rolling splits:
- 2020-22 -> 2023: validation n4, avg +3.215%, PF 14.03, win 50%
- 2020-23 -> 2024: validation n3, avg -0.514%, PF 0.108, win 33.3%
- 2020-24 -> 2025: validation n0
- 2020-25 -> 2026: validation n3, avg +2.784%, PF infinity, win 100%

Interpretation:
The recurring signal is not simply "large volume at re-entry"; persistence of volume through confirmation/entry may matter. But validation samples are tiny, so this is a research lead, not a deployable edge.

## Forward Shadow
Purpose: independently observe post-cutoff qualifying events without changing frozen OOS denominator.

- Starts from frozen cutoff and fetches closed 4h Binance candles forward.
- Uses 100 pre-cutoff warmup candles for indicators.
- Mature horizons: 2/3/6/12.
- Fixed volume candidate and fixed 5-condition monitor are both implemented.
- Workflow: .github/workflows/forward_shadow.yml
- Schedule: every 4h offset at UTC minutes 17 (00,04,08,12,16,20 UTC).
- Latest checked run had:
  - forward events 0
  - volume events 0
  - fixed-rule events 0
  - mature returns 0
No post-cutoff qualifying event had appeared as of the latest checked run.

## Important scripts/workflows
Core:
- src/audit_oos.py
- src/forward_shadow.py
- src/condition_search.py
- src/rolling_condition_validation.py
- src/rolling_condition_bidirectional.py
- src/rolling_volume_interaction.py
- src/technical_indicator_audit.py
- src/technical_indicator_walkforward.py
- src/technical_indicator_interactions.py
- src/canonical_indicator_validation.py
- src/market_state_strata.py
- src/fixed_volume_state_validation.py
- src/volume_state_permutation.py
- src/historical_deep_audit.py
- src/historical_path_structure.py
- src/historical_normalized_path.py
- src/historical_volume_context.py
- src/historical_volume_interaction.py
- src/historical_volume_path_timing.py
- src/historical_volume_failure_feature_audit.py
- src/historical_volume_fixed_state_overlap.py
- src/historical_volume_fixed_rule_validation.py
- src/historical_volume_fixed_rule_ablation.py
- src/volume_anchor_stratified_control.py
- src/volume_anchor_exit_walkforward.py
- src/volume_anchor_adverse_walkforward.py
- src/volume_anchor_failure_filter_walkforward.py

## Immediate next research task
Do NOT ask for permission. Continue autonomously.

Test the **volume trajectory from re-entry -> RSI recovery confirmation -> entry**.

Use fixed, pre-registered categories based only on information available before entry:
1. volume keeps increasing
2. volume remains elevated
3. volume sharply decreases
4. volume decreases then re-increases at entry

Recommended implementation:
- Anchor events on exact frozen 95-event denominator where possible.
- Use reentry vol_z20, confirmation-window volume z20 values, and entry vol_z20.
- Avoid any feature that uses future candles beyond the entry timestamp.
- Define categories before looking at returns.
- First run descriptive full-history path audit.
- Then run rolling walk-forward selection/validation with the same four splits:
  - 2020-22 -> 2023
  - 2020-23 -> 2024
  - 2020-24 -> 2025
  - 2020-25 -> 2026
- Cost 0.10% RT.
- Horizons 2/3/6/12.
- Do not optimize thresholds on validation/test.
- Do not promote any rule automatically.
- If samples are too small, report that explicitly and continue to the next independent diagnostic.

## Research philosophy
- Past data is sufficient for research; do not wait unnecessarily for future data.
- Future/Forward Shadow is for independent confirmation, not a reason to stop historical analysis.
- Preserve every prior result; never silently overwrite.
- Prefer independent validation over additional same-sample tuning.
- When a result looks strong, actively test whether it is a coverage artifact, overlap artifact, regime artifact, or small-sample artifact.
- Distinguish market reaction from tradable strategy P&L.
- Never claim proof from descriptive/bootstrap/same-sample results.
- Keep the final status HOLD until evidence supports a change.

## User interaction
User wants the work to continue autonomously after saying "進めて/続けて/お願い".
Do not repeatedly ask for approval.
Give concise milestone updates and concrete results.
The user is smartphone-centered and does not want unnecessary manual steps.
