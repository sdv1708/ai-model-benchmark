# Handout A | Why this works

Technical decision brief | 23 October 2026 | Historical evidence + proposed multimodal study

## Part A | Preserve decisions before reducing questions

The objective is the smallest evaluation that preserves score, model ordering and customer-threshold decisions. Join predictions/reviews by identity; replay 1,245 recorded grades across three models on 315 LiveCodeBench v5 and 100 AA-LCR questions. Coding candidates stratify by historical pass count or response pattern; AA-LCR candidates cross input length with historical difficulty, or length with document count. Cover every occupied stratum, allocate remaining slots proportionally, and use seeded hash priorities within strata. Estimate the score as **sum_h (N_h/N) mean_h**, restoring population proportions. Uniform-random, easiest-only and hardest-only methods are comparison baselines, never selectable defaults. [1]

## Validation | What would make a smaller set sufficient?

Fit selection on two reference models and evaluate the excluded third; rotate all three. For pair ordering, exclude both compared models before selection. Test 10/20/30/50/100% retention over 20 seeds. The retrospective, illustrative policy requires worst-fold MAE <=3 percentage points (pp), maximum error <=8 pp, seed SD <=3 pp, mean interval width <=20 pp, score/pair coverage >=95%, pair/threshold point agreement >=95%, pair/threshold decisiveness >=80%, and zero observed wrong decisive comparisons/decisions. Thresholds are illustrative: coding 70%, AA-LCR 60%. Use conservative 95% finite-pool intervals; a threshold-straddling interval means **inconclusive**. Every fold must pass; pooled means cannot rescue failures. [1]

## Measured result | Retain 315/315 coding and 100/100 AA-LCR

**0% pruned is the defended default.** At 158 coding questions, difficulty stratification has 1.83 pp worst-fold MAE, but the weakest pair preserves ordering only 60% of the time, with 0% interval decisiveness. At 50 AA-LCR questions, length+difficulty has 2.90 pp pooled MAE but 3.16 pp worst-fold MAE, failing the 3 pp gate. No smaller tested candidate passes all gates. This is the smallest passing tested size, not proof against untested ratios. Census removes subset error for these recorded grades, not judge or deployment uncertainty. Native pruners/comparison live in the pinned EvalScope fork; a 12-to-3 synthetic comparison with zero score difference still returned an inconclusive subset decision. That fixture proves plumbing, not compression savings. [1,2]

## Part B | Stress the visual path, with controls

Inventory pinned full MMMU: 11,550 questions/30 subjects, not just 660 supplied rows. Calibrate on development/validation; propose 360 subject/difficulty-stratified test questions for weighted estimation plus 120 additional coverage-selected diagnostics, reported separately. These budgets require feasibility/power checks. Cover tiny text, dense charts, thin diagrams, spatial detail, clutter, color and domain imagery. Pair originals with downsampling, blur, JPEG, occlusion, contrast/color and text-region blur; two reviewers must confirm label preservation. Through OpenAI-compatible image requests, fix prompts/model/detail/settings, repeat and interleave conditions, and retain hashed requests/responses. Compare paired accuracy drop, answer consistency and failure types; keep missing outcomes unknown and report bounds. Add no-image, equivalent-factual-text and visual-fact extraction controls to distinguish perception from reasoning. Black-box evidence identifies visual-path sensitivity; encoder causality requires changing only the encoder. The existing 38-pair/82-call-plan demo is synthetic; no live-model conclusion exists. [3,4]

## Assumptions and what would change

Assume valid joins/grades, stable strata and some difficulty transfer; three models cannot establish fourth-model generalization or customer-distribution coverage. The policy was chosen after earlier results; search reuses evidence. AA-LCR has no repeated judgments: judge variance is unknown. No measured latency, billing or production savings. **More data:** untouched model families, customer tasks and document-set holdouts. **Live endpoint:** freeze policy, validate full versus subset on a fresh model, repeat generation/regrading, human-audit judge bias, measure cost and run real visual controls. **More time:** test intermediate sizes, calibrate power, audit duplicates/coverage, then freeze independent confirmation. [1-4]

Evidence: [1] [Part A policy and curves](../docs/issue-17-evidence.md); [2] [Native comparison evidence](../docs/issue-21-evidence.md); [3] [MMMU design](MMMU_PROBE_DESIGN.md); [4] [Paired harness contract](MMMU_HARNESS.md). These linked records contain commands, hashes, limitations and primary research.
