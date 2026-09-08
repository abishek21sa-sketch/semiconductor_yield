# Methodology

**Evidence boundary:** same as the top-level `README.md` -- real SECOM fab sensor data, the published SMT2020 semiconductor-fab benchmark (two of its four archetypes), and the real WM-811K wafer-defect-map dataset; simulation/optimization results derived from those, not validated against a named real plant.

This document goes one level deeper than the README's pipeline-stage table and the in-app `/methodology` page's summary cards: the actual formulas, decision variables, and constraints, in the same honest-disclosure voice already established elsewhere in this repo. Nothing below is invented for this document -- every formula, parameter, and stated caveat is pulled from the module docstrings/comments in `pipeline/*.py` (file references given throughout so you can check). If this doc and a module's own docstring ever disagree, the code is the source of truth.

## Contents

1. [Yield-risk classifier (SECOM)](#1-yield-risk-classifier-secom)
2. [Classical semiconductor yield theory](#2-classical-semiconductor-yield-theory)
3. [SPC monitoring](#3-spc-monitoring)
4. [Queueing theory: Little's Law and Kingman G/G/m](#4-queueing-theory-littles-law-and-kingman-ggm)
5. [Stochastic discrete-event simulation](#5-stochastic-discrete-event-simulation)
6. [MILP 1: single-week release-mix optimization](#6-milp-1-single-week-release-mix-optimization)
7. [MILP 2: two-stage stochastic multi-period capacity plan](#7-milp-2-two-stage-stochastic-multi-period-capacity-plan)
8. [MILP 3: bottleneck batch-formation + dispatch scheduler](#8-milp-3-bottleneck-batch-formation--dispatch-scheduler)
9. [Wafer defect CNN](#9-wafer-defect-cnn)
10. [Hand-engineered baseline classifier](#10-hand-engineered-baseline-classifier)
11. [Cross-pipeline integration and archetype comparison](#11-cross-pipeline-integration-and-archetype-comparison)
12. [Impact summary composition](#12-impact-summary-composition)

---

## 1. Yield-risk classifier (SECOM)

Source: `pipeline/yield_model.py`.

**Data.** 1567 real production lots, 590 real anonymized process-sensor columns, a real pass/fail label, real timestamps (UCI ML Repository #179). Cleaning drops sensor columns with >45% missing values and any column with (numerically) zero variance -- both counts (`dropped_missing`, `dropped_constant`) are reported in the API response, not silently discarded.

**Model.** `RandomForestClassifier` (400 trees, `min_samples_leaf=2`, `class_weight="balanced_subsample"`, `random_state=42`) inside an sklearn `Pipeline` with a median `SimpleImputer` ahead of it (SECOM has real missing sensor readings, not values to guess at with a model-based imputer here).

**Cross-validation.** `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` combined with `cross_val_predict(..., method="predict_proba")`. This produces **out-of-fold** predicted probabilities: every lot's prediction comes from a model that never saw that lot during training, for all 1567 lots -- so the reported ROC-AUC/PR-AUC are honest generalization estimates, not fit-then-score-on-the-same-data leakage. A second RF is then fit on the *full* dataset (`rf_full = rf.fit(Xc, y)`) purely to extract feature importances for the "top sensors" ranking -- that fit is never used for the reported metrics themselves.

**Metrics.** ROC-AUC and PR-AUC (average precision) over the out-of-fold probabilities, plus two named operating points:
- `default_0.5`: precision/recall/confusion counts at threshold 0.5.
- `recall_ge_50pct`: the highest-precision threshold (scanned along the PR curve) subject to recall &ge; 0.5 -- a plausible "catch at least half of real failures" operating point for a triage use case, not just the default midpoint.

Majority-class accuracy (`1 - n_fails/n_lots`) is also reported explicitly, specifically so it can be compared against ROC-AUC/PR-AUC rather than a bare accuracy number, since SECOM's real fail rate is low enough (documented on the in-app Methodology page as ~6.6%) that accuracy alone would be misleading.

**Feature ranking.** The top 15 sensors by RF feature importance are returned; the single top sensor drives the SPC chart (§3).

## 2. Classical semiconductor yield theory

Source: `pipeline/yield_model.py` (bottom section) -- standard textbook formulas, not fit to data, exposed at `/api/yield/theory` so a visitor can vary defect density / die area / clustering interactively.

| Model | Formula | Notes |
|---|---|---|
| Poisson | `Y = exp(-D0 * A)` | Simplest classical model; assumes defects are uniformly distributed across the wafer. Under-predicts yield for large die because it ignores clustering. |
| Murphy | `Y = ((1 - exp(-D0*A)) / (D0*A))^2` | Standard textbook correction for defect clustering. |
| Negative binomial (Seeds/NBD) | `Y = (1 + D0*A/alpha)^(-alpha)` | `alpha` is a clustering parameter (lower = more clustered); the module notes alpha in the 1-5 range is typical for real fab defect data. As `alpha -> infinity` this converges to the Poisson model exactly (fewer, more independent defects) -- verified in `tests/test_yield_theory.py`. |

`D0` = defect density per cm&sup2;, `A` = die area in cm&sup2;.

## 3. SPC monitoring

Source: `pipeline/yield_model.py`'s `run_full_analysis()`.

A classic 3-sigma Shewhart control chart is computed on the single most important sensor from the RF ranking above (§1), using only **passing** lots to establish the baseline (`pass_vals = sensor_vals[df["fail"] == 0]`) -- the control limits describe "in-control" process behavior, not a mix of good and bad lots:

```
mu  = mean(sensor value | lot passed)
sigma = std(sensor value | lot passed)
UCL = mu + 3*sigma
LCL = mu - 3*sigma
```

A lot is flagged out-of-band with a strict inequality (`value < LCL or value > UCL`) -- a point exactly on a control limit is conventionally still "in control" in Shewhart charting, and this module's boundary convention matches that. The same boundary applies to the separate `top5_oob_signal` block, which checks the top-5 sensors (not just the single top one) for any out-of-band reading and reports how often that coincides with a real failure vs. a real pass (`fail_oob_rate` / `pass_oob_rate`) -- a rough signal-quality check on whether "out of band" is actually predictive here, not just a chart decoration.

## 4. Queueing theory: Little's Law and Kingman G/G/m

Source: `pipeline/capacity.py`. Closed-form 1961 results (Little; Kingman's VUT equation) -- exact/approximate by mathematical construction, not fit to any data, which is why they're covered by exact unit tests rather than cross-validation.

**Little's Law:**

```
L = lambda * W    =>    W = L / lambda
```

`littles_law_cycle_time(wip, throughput)` returns `wip / throughput`; `littles_law_wip(throughput, cycle_time)` is the inverse. Zero throughput returns `+inf` cycle time rather than raising or silently returning zero.

**Kingman's G/G/m approximation** for expected queueing wait time:

```
Wq ~= ( (ca^2 + cs^2) / 2 ) * ( u^(sqrt(2*(m+1)) - 1) / (1 - u) ) * (service_time / m)
```

- `ca2`, `cs2`: squared coefficients of variation of interarrival / service times.
- `m`: number of parallel machines in the station group.
- `u` (utilization, rho): must be in `(0, 1)`; `u >= 1` returns `+inf` (an unstable queue has no finite expected wait), `u <= 0` returns `0`.

At `m=1, ca2=cs2=1` (the M/M/1 special case) this reduces exactly to `Wq = (rho/(1-rho)) * service_time` -- `tests/test_capacity.py::test_kingman_matches_exact_mm1_formula` checks this to `rel_tol=1e-9`, not approximately.

**Default parameter choices**, stated in `station_utilization()`'s docstring rather than hidden: `cs2=0.25` reflects the SMT2020 benchmark's own processing-time spread (`PTIME2 ~= 5%` of `PTIME`, i.e. a tight, near-deterministic service process consistent with automated fab tools); `ca2=1.0` assumes Poisson-ish lot releases, a conservative default (CONWIP release in the simulation layer, §5, tightens real interarrival variability below this).

`station_utilization()` computes, per real SMT2020 station group: load (from real route processing times x release rate), effective capacity (`n_tools * availability`, where `availability = MTTF / (MTTF + MTTR)` from the benchmark's real reliability data), utilization, and the Kingman wait time above -- then ranks stations by utilization to name the bottleneck. `Delay_*` groups are excluded from bottleneck ranking (they're the benchmark's transport/queue-time placeholders, not physical tool capacity).

## 5. Stochastic discrete-event simulation

Source: `pipeline/fab_twin.py`. A SimPy digital twin of the real reentrant fab, not a closed-form approximation like §4.

- Each real station group is a `simpy.PreemptiveResource` sized to its real tool count.
- Each individual tool independently cycles up/down on the benchmark's real **exponential** MTBF/MTTR: `env.timeout(expovariate(1/MTBF))` until failure, then a low-priority "self request" preempts whatever lot is running and holds the resource for `expovariate(1/MTTR)` -- the standard SimPy machine-breakdown idiom. A preempted lot resumes with its leftover processing time on `simpy.Interrupt`, it does not restart from scratch.
- Lots follow their product's real ordered route (`fab_data.load_route`), with per-step processing time drawn `uniform(mean - spread, mean + spread)` from the benchmark's own `PTIME`/`PTIME2` columns.
- Two independent levers per scenario: **dispatch rule** (FIFO; SPT -- shortest processing time next; CR -- Critical Ratio, `(due_date - now) / remaining_work`) and **release control** (uncontrolled "push" release at a mean interarrival time, vs. CONWIP -- a fixed number of in-process lot "slots" that caps total WIP).
- Due dates use one fixed convention throughout the app (also reused by `bottleneck_scheduler.py`, §8): `due = release_time + flow_allowance * raw_route_time` (default `flow_allowance=3.0`).
- Reported steady-state metrics (mean/P50/P95 cycle time) exclude a stated warm-up window (`warmup_min`, default 5 simulated days) to reduce ramp-up bias -- explicitly a **transient snapshot over a fixed window**, not a proven converged steady state; under an overloaded scenario (utilization > 1) the queue is genuinely unstable and no steady state exists to converge to.
- `monte_carlo_policy_comparison()` runs each policy across multiple random seeds ("replications") and additionally reports a CVaR-style tail-risk statistic: the mean of the worst 20% of per-replication P95 cycle times -- a coarse tail-risk summary, not a formally derived Conditional Value-at-Risk over a fitted distribution.

## 6. MILP 1: single-week release-mix optimization

Source: `pipeline/release_optimizer.py`. Small on purpose (~10 variables, one integer per product) -- fits inside Gurobi's bundled free tier, unlike MILP 2 and MILP 3 below.

**Decision:** `x[route]` (integer) = lots of that product to release this period.

**Objective:** maximize `sum(weight[route] * x[route])` (weighted throughput; equal weights by default).

**Constraints:**
- Per real station group: `sum(x[route] * route_processing_time[route, group]) <= n_tools * availability * period_minutes` (real capacity, from `fab_data.load_station_groups()`).
- Per product: `min_release[route] <= x[route] <= demand_ceiling[route]`, where `min_release` is a stated minimum-fill-rate floor (default 2% of real weekly demand per product). This floor exists because real demand in this benchmark (~390 lots/week across 10 products) vastly exceeds what the real bottleneck (Diffusion) can supply -- without it the optimizer would degenerately dump all capacity into whichever single product is cheapest on the bottleneck rather than serving all 10.

## 7. MILP 2: two-stage stochastic multi-period capacity plan

Source: `pipeline/capacity_plan.py`. Deliberately large (thousands of variables) -- past Gurobi's free 2000-variable/2000-constraint limit, reported explicitly (`n_variables`, `n_constraints`, `exceeds_gurobi_free_tier`) so that claim is provable, not just asserted. At the default scale (10 products, 26 weeks, 10 Monte Carlo scenarios) this is **3,380 variables / 5,990 constraints**.

**Stage 1 (here-and-now):** `release[route, week]` (integer, 0-100 lots/week) -- decided before uncertainty resolves.

**Uncertainty / scenario generation (`_sample_weekly_capacity`, a sample-average approximation, SAA):** for every (station, tool, week, scenario), the number of real breakdown events is drawn `~ Poisson(week_minutes / MTBF)`, then total downtime is drawn `~ Gamma(N, scale=MTTR)` -- the exact distribution of the sum of `N` i.i.d. `Exp(MTTR)` repair durations (a standard compound-Poisson/renewal-process treatment), capped at one week's worth of minutes. This is a **fixed-window approximation**: a failure that starts near a week boundary is not carried into the next week -- a stated simplification, not hidden.

**Stage 2 (recourse):** `shortfall[station, week, scenario]` (continuous &ge; 0) -- if a scenario's realized capacity falls short of what stage 1 committed to, the shortfall is covered at a penalty cost (representing real overtime/expediting) rather than making the model infeasible. Overtime is capped, not unlimited: `shortfall <= overtime_cap_fraction * capacity` (default 20%), so the model can't "pay" its way to unbounded capacity through a cheap-enough penalty.

**Constraints:**
- Cumulative minimum-fill floor per product, over the whole horizon (not per-week): `sum_w(release[r,w] * yield_rate) >= min_fill_rate * weekly_demand[r] * weeks`.
- Backlog recursion per product: `backlog[r,0] = demand[r] - release[r,0]*yield_rate`; `backlog[r,w] = backlog[r,w-1] + demand[r] - release[r,w]*yield_rate`.
- Capacity per (station, week, scenario): `load - shortfall <= capacity`, plus the overtime cap above.

**`yield_rate` parameter:** converts raw released lots into real good units delivered; it does **not** relax the capacity constraints (a lot that later fails still consumed real fab capacity on its way through). Default `1.0` reproduces the original no-yield-loss model exactly. When set to the real calibrated SECOM yield rate (see §11), it's used as a stated cross-dataset planning assumption, not a claim the two fabs are the same line.

**Objective:** minimize `backlog_cost + shortfall_cost`, where `shortfall_cost` is normalized by each station's own average real per-lot load (converting machine-minutes to lot-equivalents) so the two cost terms share the same "lots" currency and the penalty weights are directly comparable, then averaged over scenarios (`/n_scenarios`).

## 8. MILP 3: bottleneck batch-formation + dispatch scheduler

Source: `pipeline/bottleneck_scheduler.py`. A tractable, exact complement to full-fab scheduling: an exact time-indexed formulation across the benchmark's full ~4,000 real reentrant steps for 10 products would need on the order of **180,000 variables** -- intractable, and the reason `fab_twin.py`'s simulation (§5) exists for full-line analysis instead. This module instead solves, exactly, the rolling real-operations problem: given a realistic snapshot of lots queued at the two real bottleneck station groups (Diffusion, Dry_Etch), find the optimal batch/sequencing decision *right now* (Theory-of-Constraints-style bottleneck dispatching).

**Two sub-models, because they're genuinely different decisions:**

**(a) Batch formation (Diffusion only) -- bin packing.** Real diffusion furnaces process a *batch* of lots together, bounded by the benchmark's own real `BATCHMN`/`BATCHMX` wafer-count limits per route step. Decision: `z[job, slot]` (binary, job assigned to batch slot) and `used[slot]` (binary). Constraints: every job assigned to exactly one slot (`sum_slot z[j,slot] = 1`); a used slot's total pieces must fall within `[BATCHMN, BATCHMX]` (`bmin*used[b] <= sum_j pieces[j]*z[j,b] <= bmax*used[b]`); `z[j,b] <= used[b]`; symmetry-breaking (`used[b] >= used[b+1]`) to help solve speed. Objective: minimize the number of batches used. **This sub-model has no minimum-volume escape hatch** -- if the real queued volume can't reach a route's real `BATCHMN` at all (e.g. a single lot far below the minimum batch size), the model correctly reports infeasible rather than fabricating an under-sized batch that violates the real constraint (see `tests/test_bottleneck_scheduler.py`'s edge-case test).

**(b) Time-indexed parallel-machine scheduling (both stations).** Once batches (Diffusion) and individual jobs (Dry_Etch) exist, each gets a start time on an hourly grid (`x[job, hour]`, binary). Constraints: exactly one start bucket per job; a job/batch can't start before its members have actually arrived (`x[j,t]=0` for `t` before arrival); at most `n_machines` jobs/batches active in any given hour (10 real furnaces for Diffusion, 21 real dry-etch tools for Dry_Etch). `tardiness[j] >= completion_bucket - due_bucket` (continuous, &ge; 0). Objective: minimize total weighted tardiness against real due dates (same convention as §5: `release + flow_allowance * raw_route_time`, but at 96-hour dispatch-horizon granularity, so a *local* per-operation due-date floor is used instead -- a modest multiple of that operation's own processing time -- since the full end-to-end route due date never binds at this short a horizon).

Both sub-models report their variable/constraint counts even when Gurobi refuses to build them without a license, using an analytically-computed upper bound (`expected_max_vars`) rather than reading it off a model that was never successfully built -- same honesty pattern as MILP 2.

## 9. Wafer defect CNN

Source: `pipeline/wafer_data.py`, `pipeline/wafer_cnn.py`.

**Data preparation.** Of WM-811K's 811,457 real wafer maps, 172,950 are human-labeled into 9 real classes (8 defect patterns + "none"). Each variable-size real wafer map is resized to a fixed 64x64 using **nearest-neighbor** interpolation (`order=0`) -- deliberately, because the underlying values are categorical (`0`=no die, `1`=pass, `2`=fail); linear/cubic interpolation would invent nonsense intermediate values between discrete categories never present in the real data. The resized map is then encoded as 2 channels -- a die-present mask and a fail mask -- rather than feeding the raw `{0,1,2}` ordinals directly to a CNN, which would falsely imply `fail(2) > pass(1) > absent(0)` as a magnitude relationship.

**Train/val/test split.** A class-stratified 80/10/10 split computed by this app (`stratified_split`, seed 13), not WM-811K's own published `trianTestLabel` field -- that field is real but isn't class-stratified and skews ~69% Test / 31% Training, not a standard ML split. The training set additionally caps the dominant "none" class to 25,000 of its real 117,944 training examples (every other class keeps every real example); validation and test are never rebalanced, so reported metrics reflect the real, un-rebalanced class distribution. Both choices are stated in code, not silently substituted.

**Model.** A small CNN (`WaferCNN`): 3 conv blocks (`Conv-BatchNorm-ReLU-MaxPool`, channels 2&rarr;16&rarr;32&rarr;64, spatial 64&rarr;8) followed by 2 fully-connected layers (~640K parameters total) -- small enough to train on CPU in real time at this resolution.

**Loss.** `CrossEntropyLoss` with per-class weights `= total_count / (n_classes * class_count)` (inverse-frequency weighting) against the real ~1000:1 class imbalance (147,431 "none" vs. 149 "Near-full").

**Augmentation -- a stated negative result, not a guess.** Random 90-degree rotation/flip is physically valid for a wafer map (no inherent "up") but a full run measurably *hurt* this model (test macro-F1 74.4% &rarr; 71.6%), and specifically made the weakest class (Scratch) worse (F1 0.19 &rarr; 0.14), not better as hypothesized -- a real scratch defect likely has a preferred orientation tied to handling/transport mechanics, so randomizing it teaches the wrong spatial cue. `augment=False` is therefore the default, with the negative result left in the code and available (`augment=True`) rather than deleted.

**Evaluation.** Macro-F1 and per-class precision/recall/support (not raw accuracy, for the same class-imbalance reason as §1), plus a full confusion matrix. Model selection across epochs uses the best **validation** macro-F1 (`best_val_f1`), with final metrics reported on the held-out **test** split only after that selection is fixed.

**Explainability.** Grad-CAM (Selvaraju et al. 2017) is computed from the trained model's own gradients (hooked at `model.features[10]`, the last conv block's 16x16 post-ReLU activation -- chosen over the coarser 8x8 post-maxpool output as more useful for a visual overlay) for each sample in the served sample gallery, so a viewer can see which real pixels actually drove a given prediction, not just the predicted label.

## 10. Hand-engineered baseline classifier

Source: `pipeline/wafer_baseline.py`. Exists to answer "does the CNN's spatial modeling earn its complexity" -- trained/evaluated on the **exact same** real train/val/test split as the CNN (via the shared `wafer_data.prepare_training_split`), so the macro-F1 gap between the two is a genuine apples-to-apples comparison, not an artifact of two different splits.

Six hand-engineered features per real wafer map, computed from its die/fail masks: `fail_density` (fraction of real die that failed), `centroid_radius` (normalized radial distance of the failure centroid from wafer center), `radial_std` (spread of failure radii), `edge_fraction` (fraction of failures beyond 80% of the wafer radius), `n_components_norm` (connected-component count of the fail mask, normalized by fail count), `largest_component_fraction` (size of the largest connected fail region as a fraction of total fails). These feed a class-weighted `RandomForestClassifier` (300 trees), evaluated with the identical confusion-matrix/macro-F1 code path as the CNN (`wafer_cnn._confusion_matrix` / `_precision_recall_f1`, imported directly, not reimplemented) for a genuinely comparable number.

## 11. Cross-pipeline integration and archetype comparison

Source: `api/main.py`'s `_compute_integration()`, `pipeline/quality_risk.py`, `pipeline/archetype_comparison.py`.

**Yield-adjusted capacity plan.** The real calibrated SECOM yield rate (§1) is passed into MILP 2 (§7) as the `yield_rate` planning parameter, comparing the unadjusted vs. yield-adjusted 26-week backlog. SECOM and the SMT2020 fab are stated explicitly, everywhere this is used, to be **different real fabs** -- this is a representative real-world planning assumption (how a real fab plans when it doesn't yet have its own line's yield data), not a claim of identity between the two.

**Quality-risk mapping.** `pipeline/quality_risk.py` maps each of the 8 real WM-811K defect *patterns* onto the SMT2020 station group conventionally associated with that pattern *category* in yield-engineering practice (e.g. "Scratch" &rarr; `Litho_Met`, handling/transport damage; "Random" &rarr; `Implant`, particle contamination) -- an explicit, stated heuristic mapping from domain literature, **not** derived co-occurrence data between the two unrelated real datasets. The result is a second, distinct lens next to the capacity bottleneck: "where defects likely originate" vs. "where the fab is busiest" -- in this app's real data, those are different stations (Wet_Etch vs. Diffusion), which is itself a real, checkable finding neither dataset shows alone.

**Archetype comparison (LVHM vs. HVLM).** Both are real, published SMT2020 configurations sharing the *exact same* 106-tool real inventory and even reusing two real route files verbatim (`route_3.txt`, `route_4.txt` are byte-identical between the two archetype folders) -- the real difference is demand concentration: LVHM spreads ~390 real lots/week across 10 products, HVLM concentrates the same ~390 lots/week onto 2. For a fair comparison (not an artifact of picking two different release paces), both are evaluated at the **same total system release rate** -- only the number of products sharing that rate differs, mirroring the real demand-concentration difference between the archetypes' own `order.txt` files. `same_bottleneck_station`, `bottleneck_utilization_delta`, and `bottleneck_wait_delta_fraction` (using the Kingman wait time from §4) are computed fresh from both archetypes' real topology/route/demand files each call, nothing precomputed or asserted in advance.

## 12. Impact summary composition

Source: `pipeline/impact_summary.py`. This module performs **no new solver calls** and introduces no new fabricated math or unit economics -- it's a pure composition of numbers every other stage above already computed, tying them into one headline narrative. The one genuinely *derived* (not just re-read) number is:

**`defect_catch_rate`:** of all real test-set wafers with an actual defect (`true label != "none"`), what fraction did the CNN flag as having *some* defect (`predicted label != "none"`, regardless of which specific type)? Computed directly from the CNN's own real confusion matrix:

```
true_defect_total = sum(cm[i][j] for i != none_idx, all j)
caught            = sum(cm[i][j] for i != none_idx, j != none_idx)
defect_catch_rate = caught / true_defect_total
```

This is the operationally relevant number for a triage/rework-routing use case ("did we catch that something's wrong"), distinct from macro-F1 (§9), which weights getting the *exact* class right equally across classes.
