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

## Latest research update — BB lower-band slope × volume anchor
### BB lower-band slope
A pre-registered structural feature was tested on the same frozen 95 events:
- Lower Bollinger Band movement over the 3 immediately preceding closed candles, normalized by ATR(14).
- Categories fixed before outcome inspection: falling <= -0.50 ATR; flat -0.50..0.50 ATR; rising >= 0.50 ATR.
- Counts: falling 73, flat 20, rising 2.
- Full-sample falling net averages after 0.10% RT cost: 2 +0.0968%, 3 +0.1382%, 6 -0.2428%, 12 +0.4282%.
- Rolling WF selected falling in all four splits.
- Validation averages for falling:
  - 2023: +0.311%, +0.251%, +0.287%, +1.280%
  - 2024: -0.159%, +0.625%, +0.394%, +0.542%
  - 2025: -0.441%, -0.324%, -0.831%, +0.591%
  - 2026: +1.288%, +1.450%, +0.933%, +1.956%
Interpretation: structurally interesting and more persistent than BB-depth/streak features, but not sufficient for promotion.

### BB lower-band slope × re-entry volume anchor
- volume anchor = reentry vol_z20 >= 1.0
- slope group = falling vs not_falling
Full historical:
- falling + volume anchor: n=26; avg net +0.707%, +0.994%, +0.390%, +1.486% at 2/3/6/12 bars.
- falling without volume anchor: n=47; -0.241%, -0.335%, -0.593%, -0.157%.
- not_falling + volume anchor: n=8; negative at all horizons.
- not_falling without anchor: n=14; negative at all horizons.

Rolling WF combo selection:
- All four training periods selected the same falling__vol1 combination.
- Validation:
  - 2023 n5: +0.265%, +0.336%, +0.210%, +2.636%
  - 2024 n7: -0.293%, +0.878%, +0.154%, -0.145%
  - 2025 n3: +0.618%, +0.125%, -2.359%, +0.233%
  - 2026 n3: +2.151%, +2.238%, +1.039%, +3.155%
- Weighted across 18 OOS events: 2 +0.421%, 3 +0.829%, 6 -0.102%, 12 +1.241%.
Important: yearly validation samples are only 3–7 events. Promising research candidate, not proof.

### Incremental check against volume anchor alone
- 2024 and 2025 all volume-anchor events were already falling, so the slope filter changes nothing.
- 2023 falling+anchor reduced n from 6 to 5 and lowered 2/3-bar average while improving 12-bar average.
- 2026 falling+anchor reduced n from 5 to 3 and improved all four horizons.
Conclusion: current evidence does not establish a consistent independent improvement over volume anchor alone.

### Current status
**HOLD / research-only.**
Do not deploy or treat the combo as a proven edge.

## Latest research update — BB lower-band slope decomposition
### Decomposition result
The falling lower-BB signal was decomposed into 3-bar pre-reentry BB midline slope and BB width slope, both ATR-normalized, with fixed ±0.50 ATR categories. Frozen denominator remained 95.

Full-sample results:
- mid down + width expanding: n28; 2/3/6/12 net averages -0.171%, -0.307%, -1.134%, -0.068%.
- mid flat + width expanding: n39; +0.383%, +0.511%, +0.710%, +1.141%.
- mid down + width contracting: n6; negative at all horizons.
This indicates the prior falling lower-BB signal is not simply a falling midline/trend signal. The most stable decomposition cell was midline flat + width expanding.

Rolling WF selected flat + expanding in all four splits:
- 2023: n9; +0.528%, +0.263%, +0.275%, +0.469%
- 2024: n3; -0.301%, +1.217%, +0.985%, +2.667%
- 2025: n6; -0.291%, -0.253%, -0.476%, +0.947%
- 2026: n5; +1.039%, +0.634%, +0.741%, +1.061%
Interpretation: more consistent than raw lower-BB slope, but samples remain small and 2025 short-horizon results were weak.

### Decomposition × volume anchor
A small pre-registered interaction with re-entry volume anchor was tested. All four rolling splits selected mid flat + width expanding + volume anchor. Validation counts were only 1–2 per year:
- 2023 n2: 2 +0.361%, 3 -0.014%, 6 -0.454%, 12 -0.040%
- 2024 n2: 2 +0.851%, 3 +2.640%, 6 +1.599%, 12 +2.684%
- 2025 n1: 2 +0.175%, 3 +0.340%, 6 +0.376%, 12 +3.600%
- 2026 n2: 2 +0.791%, 3 -0.258%, 6 -0.273%, 12 +0.948%
Too sparse to establish an independent interaction effect. Research lead only.

### Current status
**HOLD / research-only.** No deployment decision has changed.

## Immediate next research task
1. Stop adding arbitrary BB filters. Structural evidence now points to midline roughly flat + BB width expanding, with volume shock potentially concentrating it.
2. Test redundancy with existing ATR/BB-width state features using matched/stratified controls rather than another threshold sweep.
3. Compare the regime against the existing volume-anchor signal on identical event IDs, including incremental OOS coverage.
4. If it survives, perform one final compact pre-registered rule using only pre-entry information.
5. Continue Forward Shadow in parallel; do not use future observations to tune the frozen historical rule.


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

## Latest research update — BB decomposition redundancy / matched controls
### Independence audit
The frozen 95-event denominator was preserved. The target regime is fixed as pre-reentry BB midline slope flat (-0.50..0.50 ATR) AND BB width slope expanding (>=0.50 ATR); volume anchor remains re-entry vol_z20 >= 1.0.
- target regime: 39/95
- volume anchor: 34/95
- overlap: 13/95

Within the target regime:
- volume-anchor events (n=13): net averages +1.169%, +1.421%, +1.689%, +2.487% at 2/3/6/12h.
- target without volume anchor (n=26): -0.009%, +0.057%, +0.221%, +0.468%.
This reinforces that volume shock is a major concentration variable.

### Matched controls
Using identical event IDs and fixed pre-entry strata:
- year x ATR-bin matched target-vs-control weighted differences: +0.382%, +0.527%, +1.724%, +1.368% at 2/3/6/12h.
- year x BB-width-bin: +0.592%, +1.015%, +1.989%, +2.050%.
- year x ATR-bin x volume-anchor: -0.058%, +0.365%, +1.682%, +1.677%.
- year x BB-width-bin x volume-anchor: +0.295%, +0.585%, +1.740%, +1.656%.
Interpretation: the decomposition regime is not explained away by ATR/BB-width state alone. Even within the volume-anchor subset, a positive residual difference remains at 6/12h. However, this is still observational matched-control evidence, not independent OOS proof.

### OOS coverage
The fixed target+volume combination remains sparse:
- 2023: 2 events
- 2024: 2 events
- 2025: 1 event
- 2026: 2 events
Therefore the apparent incremental effect cannot yet be treated as a stable deployable edge.

### Current interpretation
The research focus should now move away from arbitrary BB threshold additions. The evidence currently supports a structural hypothesis:
**a lower-BB re-entry occurring while the BB midline is relatively flat, BB width is expanding, and re-entry volume is unusually elevated may describe a distinct rebound regime.**
This remains a hypothesis until an independent forward/OOS sample accumulates enough events.

### Next task
1. Keep the fixed historical rule frozen; do not tune thresholds from these results.
2. Continue Forward Shadow using the existing frozen setup.
3. Run one compact pre-registered OOS/forward monitor for the structural regime, but do not promote it to live trading.
4. If independent evidence remains sparse, stop adding technical filters and move to an independent feature family rather than further BB decomposition.

## Latest independent feature research — Taker Buy Ratio
A separate feature family was tested from Binance Spot kline fields: taker-buy base volume / total base volume at the re-entry candle, plus its change versus the preceding 3-candle aggregate. Fixed semantic states were pre-registered: buy >=55%, sell <=45%, neutral otherwise; improving = +5 percentage points or more versus the preceding 3-candle aggregate.

Results on the same frozen 95 events:
- buy state: n=6; net averages -0.047%, -0.042%, -0.288%, +0.036% at 2/3/6/12h.
- improving state: n=20; +0.347%, +0.419%, +0.272%, +0.926%.
- anchor + improving: n=5; +1.095%, +1.088%, +0.593%, +0.713%.
The simple buy-ratio level is not useful by itself; the change/improvement state is more interesting.

Rolling OOS coverage for improving:
- 2023 n2: 2 -0.123%, 3 -0.088%, 6 -1.138%, 12 +0.890%
- 2024 n2: 2 +1.477%, 3 +1.623%, 6 +1.896%, 12 -0.549%
- 2025 n8: 2 -0.575%, 3 -0.419%, 6 +0.081%, 12 +0.836%
- 2026 n4: 2 +1.003%, 3 +1.302%, 6 +1.396%, 12 +2.755%
Interpretation: promising as an independent feature hypothesis, especially at 12h, but not stable enough and not sufficiently independent-OOS validated for promotion.

Current research direction:
- Keep BB structural hypothesis fixed rather than adding more BB thresholds.
- Continue testing Taker Buy Ratio improvement as an independent feature and its incremental contribution to the volume/BB regime.
- If the interaction remains sparse, move to forward monitoring rather than further historical threshold mining.
- Status remains HOLD / research-only.


## Latest research update — Taker Buy Ratio incremental contribution audit
The Taker Buy Ratio improvement feature was tested for incremental contribution against the existing volume anchor and BB structural regime, using the same frozen 95 event IDs and no threshold search.

Fixed definitions remained unchanged:
- improving = re-entry taker-buy ratio improved by >=5 percentage points versus the preceding 3-candle aggregate.
- volume anchor = re-entry vol_z20 >= 1.0.
- BB target = pre-reentry BB midline slope flat AND BB width slope expanding, using the already frozen +/-0.50 ATR boundaries.

### Incremental findings
Within year x volume-anchor strata, the improving-vs-non-improving differences were inconsistent:
- 2025 anchor: 2h -0.850%, 3h -0.469%, 6h +0.910%, 12h -4.736% (n=1 improving vs 2 controls).
- 2026 anchor: 2h -1.980%, 3h -0.829%, 6h +0.586%, 12h -1.883% (n=2 vs 3).
- 2022 anchor showed positive differences, but only n=1 improving vs 6 controls.
Thus no stable incremental advantage of Taker Buy Ratio improvement inside the volume-anchor regime is established.

Within the BB target + volume-anchor subset, coverage was even sparser:
- 2022: n=1 improving vs 3 controls, positive across all horizons.
- 2026: n=1 improving vs 1 control, positive across all horizons.
- 2023/2024/2025: no qualifying improving event inside the BB-target+anchor subset.
This is far too sparse for an OOS interaction claim.

### OOS fixed-condition coverage
- improving: 2023 n2, 2024 n2, 2025 n8, 2026 n4. Direction varies by year/horizon; 12h is positive in 2023, 2025, 2026 but negative in 2024.
- anchor + improving: 2025 n1 (+0.051%, -0.188%, -1.752%, -2.925%); 2026 n2 (+0.200%, +0.444%, +0.601%, +1.504%).
- BB target + anchor + improving: only 2026 n1 (+0.909%, +0.975%, +0.940%, +1.819%).

### Conclusion
Taker Buy Ratio improvement remains a plausible market-microstructure feature, but the incremental audit does **not** show a stable additional edge after conditioning on the existing volume/BB regime. Further threshold mining is not justified.

**Decision: HOLD / research-only.**
The historical technical-filter branch is now considered sufficiently explored for the current event definition. Continue Forward Shadow for independent confirmation, and if another historical branch is needed, prefer a genuinely independent feature family (for example derivatives positioning/flow) rather than additional BB/Taker thresholds.

### Research status
- Frozen event definition: unchanged.
- Frozen historical denominator: 95.
- Taker incremental audit: completed and saved.
- Forward Shadow: continuing independently.
- Live trading/deployment: not approved; status remains HOLD.


## Latest independent feature research — Futures Funding Rate
A separate derivatives feature was tested using Binance USDⓈ-M BTCUSDT funding-rate archives. The information boundary was corrected to use only the most recent funding settlement **strictly before** the frozen re-entry timestamp; same-timestamp funding observations are excluded to avoid lookahead ambiguity.

Fixed semantic states were used without threshold search:
- positive: funding >= +0.01%
- negative: funding <= -0.01%
- neutral: otherwise
- easing/tightening: change versus the immediately prior funding settlement of at least 0.01 percentage point in the corresponding direction.

### Full frozen-event result
Across the 95 events:
- positive n=42: 2/3/6/12h net averages -0.303%, -0.639%, -1.103%, -1.008%
- neutral n=51: +0.301%, +0.461%, +0.198%, +1.025%
- negative n=2: too sparse; mixed/negative overall
- easing n=6: mixed, with 6h negative and 12h slightly positive
- tightening n=4: negative across all horizons, but far too sparse for inference

The full-sample contrast suggests that elevated positive funding may coincide with a weaker rebound regime, while neutral funding is more favorable. This is a useful hypothesis, not a proven causal effect.

### OOS check
Fixed state coverage by validation year was sparse for most states:
- positive: 2023 n7, 2024 n6, 2025 n3, 2026 n1.
- positive-state OOS results changed materially by year: 2023 and 2024 were positive at most short horizons, 2025 was strongly negative, and 2026 was positive but n=1.
- negative/easing/tightening had zero qualifying events in the 2023-2026 validation periods under the fixed definitions.

### Conclusion
Funding Rate is a genuinely independent feature family and therefore more informative for the research program than adding further BB/Taker thresholds. However, the current fixed state test does **not** establish stable OOS edge. The interesting hypothesis is **positive funding may weaken the Spot rebound after the lower-BB re-entry**, but the validation sample is insufficient and regime-dependent.

**Decision: HOLD / research-only.**
Do not convert funding state into a live filter yet. Preserve the result and move toward a compact pre-registered interaction test only if it can be done without threshold mining; otherwise prioritize Forward Shadow and independent validation.
