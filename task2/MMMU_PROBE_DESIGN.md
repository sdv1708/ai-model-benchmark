# Full-dataset MMMU visual-path probe (issue #22)

Status: **researched proposal, not an implemented or validated pruner**. No new
multimodal inference, image transformations, probe selection or human oracle
annotation was performed. The proposed budgets and gates below are starting
requirements to validate, not measured accuracy or savings. This completes the
design scope of [issue #22](https://github.com/sdv1708/ai-model-benchmark/issues/22).
The runnable Part A adapters remain in the private EvalScope fork.

## 1. Decision and identification limit

Ask whether a candidate's **visual input path** preserves task-relevant information
at an acceptable cost. A high MMMU answer score alone cannot answer this: success
also requires subject knowledge, reasoning and answer formatting. Conversely,
some questions can be answered from text or memorized associations without seeing.
[MMStar](https://arxiv.org/abs/2403.20330v2) documents this problem;
[MMMU-Pro](https://arxiv.org/abs/2409.02813v3) explicitly filters text-answerable
items. Those motivate controls; this proposal still samples **original MMMU**, not
MMMU-Pro or MMStar.

Through an OpenAI-compatible API we observe images in and answers out. We cannot
inspect embeddings, attention, the projector or internal resize operations.
Controlled failures can implicate perception, preprocessing or multimodal fusion;
they cannot uniquely identify a broken encoder. An encoder-specific causal claim
needs an engineering intervention that changes only the encoder while holding
the language model, projector, preprocessor and serving configuration fixed.
If those components change together, report a system regression.

## 2. Population: approximately 12K is not 660

The official [dataset card at the researched revision](https://huggingface.co/datasets/MMMU/MMMU/blob/876ce5cb130f7f7e290ce4d9984357737d4db5cf/README.md)
declares 30 subject configurations. Summing its split counts gives:

| Pool                          | Questions | Role in this plan                                 |
| ----------------------------- | --------: | ------------------------------------------------- |
| Development                   |       150 | Prompt/annotation calibration only                |
| Validation                    |       900 | Design pilot, transformation and parser debugging |
| Test                          |    10,500 | Frozen confirmatory sampling frame                |
| All splits                    |    11,550 | Full MMMU inventory, the brief's approximate 12K  |
| Supplied historical reference |       660 | One model, 22 subjects, validation IDs only       |

Inventory **all splits and all 30 subjects**, then select the confirmatory probe
from test. A test estimate targets those 10,500 questions, not all 11,550. Do not
mix calibration rows into its denominator. A future all-split descriptive estimate
would need split-specific samples and weights and would lose the clean holdout.

The supplied prediction inventory contains 613 multiple-choice and 47 open
questions, with 209 Easy, 304 Medium and 147 Hard tags. Its 27 observed image-type
labels overlap: a question can have several. These are **reference-only counts**,
not the full dataset's proportions. Missing subjects are Math,
Mechanical_Engineering, Music, Pharmacy, Physics, Psychology, Public_Health and
Sociology. A probe calibrated only on those references would miss entire domains.
The [inventory audit](../docs/data/mmmu-inventory-audit.json) records file hashes,
subject counts and the official revision. Card counts were verified as metadata;
we did not scan full-dataset Parquet rows or decode its images.

The [official repository at its researched revision](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/README.md)
announces released test answers. Its
[test answer mapping](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/mmmu/answer_dict_test.json)
has 10,500 entries, each keyed by source ID with `question_type` and `ground_truth`.
Do not assume a dataset mirror has those released answers. Join the separate
mapping by **source ID**, check question type and complete coverage, and pin its
bytes. Never send answers or explanations to the candidate model. Public test
answers also increase contamination risk: this is a held-out experiment for our
design, not proof the model never trained on the questions.

## 3. Build an answer-blind inventory before selecting

Freeze HF revision `876ce5cb130f7f7e290ce4d9984357737d4db5cf`, the answer mapping
revision above, adapter/evaluator commits and a versioned annotation rubric.
Parse string-encoded `img_type` and `options` safely; reject malformed records.
For every question keep subject, subfield, split, ID, difficulty, question type,
ordered text/image references and image count. Preserve images in options as well
as the question, including repeated references and up to seven image fields.

Build a manifest with encoded-image SHA-256, decoded dimensions, color mode,
orientation, question/options hash, annotation provenance and missing-field flags.
Detect duplicate IDs and image/question hashes. Group near-duplicate diagrams or
questions for the pilot/test leakage audit; publish collisions and remove test
groups exposed by pilot calibration **before** sampling. If this changes the
frame, recompute `N`, all group counts and budgets; stop calling it the unchanged
10,500-question test frame. Keep duplicate-image groups for clustered sensitivity
analysis, even when they represent distinct legitimate questions.

Use the source's difficulty as a **reasoning-demand tag**, never as a measured
encoder difficulty. Add model-independent visual tags: small text, dense chart,
thin lines, spatial relations, clutter, color dependence, specialized symbols and
multi-image comparison. Dimensions, edge density and OCR character size are
screening proxies, not truth. Annotators inspect ambiguous tags without candidate
answers or scores; record disagreement and adjudication. Audit a seeded 10% of
annotations twice. If a tag is missing, retain an explicit Unknown group.

Map native image labels to seven reporting families: text/tables/screenshots;
plots/charts; diagrams/geometry/graphs; maps/blueprints; natural/art imagery;
medical/microscopic imagery; scientific notation/structures/music. Keep every
native label alongside this mapping. Novel labels remain Unknown until mapped;
do not silently collapse missing coverage into Other. Record subfields and all
six disciplines; broad family coverage cannot substitute for subject coverage.

## 4. Two panels with different jobs

### Panel R: a population estimate, initially 360 unique test questions

Start with 12 per subject. Within each subject, stratify on the source difficulty
tag (including Unknown), give each nonempty difficulty cell `min(2, N_h)` rows,
then allocate the remaining subject budget proportional to residual cell sizes
using largest remainders, stable lexical tie-breaking and caps at `N_h`. If the
minimum exceeds 12, raise that subject budget before selection and publish the
new total. If a subject has fewer than 12 eligible rows, take its census; never
invent rows or silently shift the estimand. All `n_h` are fixed before outcomes.

Sample without replacement **within each cell** using a frozen PRNG algorithm,
seed and sorted source IDs; save IDs and `pi_i = n_h/N_h`. This is a stratified
design with subject/difficulty coverage and unequal population weights, not the
forbidden whole-pool uniform-random baseline. Randomness only chooses members of
the declared cells. No historical model scores affect selection. Never redraw
until a convenient result or image balance appears: that changes probabilities.

Report family, native image label, subfield, question-type, multi-image and visual
tag margins for R. Subjects/difficulty are its mutually exclusive sampling cells;
image tags are overlapping diagnostics. Use Panel S to fill representation gaps
without distorting R's sampling design.

### Panel S: diagnostic coverage, initially 120 additional unique questions

From the remaining eligible test questions, use constrained maximum coverage
over the answer-blind tags. Start with at least four per subject and prioritize
uncovered/rare categories. Required **union R+S** targets are:

- Every native image label and every subfield present in the frozen frame at
  least once; target three distinct questions per native label where available.
- Every one of the eight stress axes below has at least 12 applicable questions,
  preferably across at least three subjects; publish structural exceptions.
- At least 30 multi-image and 30 open-answer questions where available; cover
  each populated broad image family and each difficulty tag.

Select the candidate with greatest weighted unmet-quota reduction per estimated
annotation/API cost, rarest unmet category first; break ties by SHA-256 of
`rubric_version | seed | source_id`. Do not hand-pick impressive examples or
select the easiest/hardest by the supplied model's grades. Use a solver or an
explicit feasibility audit to check that greedy failure is not mistaken for
impossibility. The 120-row budget is **not proven feasible**. Increase S in
predeclared 30-row blocks up to 240 if needed; beyond that, report infeasible
coverage and revise the design before model calls. Never silently waive a quota.

S deliberately overrepresents visual stress. Publish its diagnostic results
separately; it has no probability weights for estimating full MMMU accuracy.
Report rare cells with their actual denominators; 12 examples identify a screen,
not a precise subgroup estimate. One native label per question is not guaranteed.

## 5. Stress tests and semantic checks

Every selected question receives one preregistered applicable primary stress axis
and two severity levels. Multiple tags may be reported, but do not count one
question as independent evidence for several axes. Transform the target image
only, keep the other images fixed and record the target slot. Assignment is
answer-blind and balanced to meet the axis quotas. Existing specialized imagery
supplies domain coverage; transformations need not manufacture medical facts.

| Axis           | Mild / stronger intervention to pilot                                                                 | What to score and check                                                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Resolution     | Downsample to 75% / 50% of each dimension, then restore canvas with fixed resampler                   | Can small features still be extracted? Record actual pixels and provider detail; verify essential facts remain human-readable.                                 |
| Text/OCR       | Light / stronger blur on text-bearing regions using fixed, saved masks                                | Character/number transcription, including minus signs, subscripts and units; do not treat erased text as an encoder error.                                     |
| Charts         | Two levels of compression or thinning on dense chart images                                           | Axis/legend/series reading and a marked data value; preserve scale and series identity.                                                                        |
| Diagrams       | Two levels of resampling on line/arrow diagrams                                                       | Node labels, arrow direction and connectivity; verify no connection disappears.                                                                                |
| Spatial detail | Fixed padding reduces occupied canvas to 85% / 70%                                                    | Left/right, adjacency and small-object facts; preserve all content and coordinates via an explicit transform.                                                  |
| Clutter        | Add a fixed neutral border pattern outside the original at two densities, same canvas layout in both  | Relevant-object selection; no overlay on evidence. Include matched plain-border control during pilot to measure layout effects.                                |
| Color          | Fixed saturation reduction to 75% / 50%                                                               | Legend/color distinctions. Keep required categories distinguishable; grayscale that destroys the only cue is a negative control, not a scored invariance test. |
| Domain imagery | Two strengths of fixed JPEG recompression on medical, microscopy, chemical, blueprint or music images | Specialist symbols, morphology, bonds or notes; expert verifies no label-relevant feature was removed.                                                         |

Percentages and operations are **pilot settings**, not established perceptual
equivalence. Save transform parameters, masks, library/version, encoded bytes and
checksums. Apply orientation consistently; keep originals unmodified. Two human
reviewers, with specialist review for domain content, check fact preservation
without model outputs. Before selection freeze the list of eligible transforms
per question. A selected image failing later QA becomes a recorded invalid pair;
do not replace it based on the model's answer. Report missing-pair counts and
sensitivity bounds, or collect corrected evidence under a new protocol version.
Purposefully destructive controls may verify visual dependence but must be
separated from label-preserving robustness claims.

## 6. Six conditions per question, two attempts per condition

All calls use independent conversations. Prompts, choice ordering, model version,
provider settings and output budgets are fixed within a paired comparison.
Shuffle execution order with a saved schedule to reduce time/serving confounds.

| Condition          | Input / requested output                                                                             | Purpose                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| O: original        | Unmodified images + question/options; final answer                                                   | End-to-end baseline                                                            |
| N: no image        | Same text/options, image references replaced by neutral slot markers; final answer                   | Text shortcut, prior knowledge or leakage screen                               |
| E: equivalent text | Same task, all image information replaced at its slot by reviewed factual descriptions; final answer | Bypass visual extraction while retaining the reasoning task                    |
| P1                 | Mild label-preserving transform + same task; final answer                                            | First sensitivity point                                                        |
| P2                 | Stronger label-preserving transform + same task; final answer                                        | Second sensitivity point                                                       |
| V: visual facts    | Original images + fixed, non-leading factual extraction questions; structured short facts            | Direct OCR/chart/spatial/symbol evidence, scored against an independent rubric |

Two annotators create E and the V rubric from the image, blinded to candidate
outputs and the official final answer; adjudicate independently. Include all
facts needed for reasoning, not the solution, a chosen option or a leading
summary. Describe every image option with equal detail and unchanged ordering.
Do not use the tested model's OCR as the oracle. If equivalent text cannot
faithfully describe an image, mark E unavailable and report its coverage; do not
pretend a caption is a complete substitute. Create neutral factual descriptions
even when the image itself displays answer-like text; do not add deductions.

Interpret a pattern, not a single binary verdict:

- O wrong, E right, N wrong and V wrong: evidence consistent with a visual-path
  bottleneck; E's prompt modality is still a confound.
- O and E wrong: knowledge/reasoning, oracle inadequacy or combined failure is
  unresolved; a failed oracle control does not exonerate the encoder.
- O right, N right: weak evidence of image necessity; report separately, do not
  remove it from R after seeing outcomes or infer contamination from one guess.
- O right, P2 wrong with human-preserved facts: robustness concern on this pair;
  compare P1 and V, repeats and a fixed baseline system before claiming regression.
- V right, O wrong: extraction succeeded for those facts; later reasoning/fusion
  may fail, and the rubric may omit another necessary visual fact.

Two attempts screen generation instability; they do not measure rare failures
well. Repeated calls, transforms and facts are clustered inside a question, not
new independent benchmark samples.

## 7. OpenAI-compatible interaction and evidence contract

Use `POST {base_url}/chat/completions` with `base_url` ending in `/v1`; negotiate
the provider's actual route in preflight. Bearer authentication stays in an
environment secret and is never written to manifests. The
[official vision guide](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
documents text/image content parts and data URLs. Compatibility does **not**
guarantee identical image resizing, token accounting or supported settings.

Conceptual request shape, **not a runnable command** (replace placeholders and
materialize ordered question/options content; include every referenced image):

```json
{
  "model": "PINNED_PROVIDER_MODEL_ID",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "QUESTION_AND_OPTIONS_BEFORE_IMAGE_1" },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,ENCODED_BYTES",
            "detail": "high"
          }
        },
        {
          "type": "text",
          "text": "REMAINING_TEXT_AND_FINAL_ANSWER_INSTRUCTION"
        }
      ]
    }
  ],
  "temperature": 0,
  "max_completion_tokens": 1024,
  "stream": false
}
```

Preflight checks vision, multiple images, both question types, supported detail,
sampling settings and output-cap field. This template assumes those settings
are supported. If the provider requires `max_tokens` instead, lock that explicit
profile and its meaning; if it rejects temperature or detail, record the actual
supported profile before starting. Never silently retry with altered semantics.
Use the same profile for baseline and candidate. A separate high/low-detail
experiment changes preprocessing and must be named separately. No portable
assumption about a provider's internal image-token formula is made.

The [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
defines token caps and response usage; a completion cap can include reasoning
tokens. Calibrate enough headroom on validation. Treat truncation separately.
Set a seed only if supported and record returned fingerprint/version if present;
neither temperature zero nor a seed is a determinism guarantee. Disable tools,
retrieval and conversation history. For O/N/E/P, request `ANSWER: <letter>` or
`ANSWER: <value>` without requiring a reasoning transcript. V requests only its
rubric's named facts; tool-free text JSON can be validated locally without
depending on provider structured-output support.

Save one attempt record per `(source_id, panel, condition, repeat, system)` with:

- Dataset, label, selection, prompt, transform, oracle, rubric and scorer hashes;
  source split/subject, `N_h`, `n_h`, inclusion probability for R and image order.
- Requested/resolved model, endpoint host, supported generation profile,
  request hash, execution time/order, response ID and backend fingerprint if exposed.
- Raw answer, parsed answer/facts, rubric results, finish reason, HTTP/error
  status, retry history, wall time and returned usage including cache details.
- Billed cost from actual provider prices dated at execution, if known; otherwise
  cost is unknown. Do not record credentials or infer missing usage as zero.

Use nonstreaming wall-clock latency with fixed concurrency and warmup policy;
it is not time-to-first-token. Cache by the entire protocol identity, including
image bytes and repeat ID. Preserve retries; transport retries are not new
samples. Retry only transient failures with bounded backoff (at most two retries),
never answer-based retries. Log timeouts, rejected images and truncations as
unevaluable; report reliability separately. An ordinary completed but malformed
final answer is a scored format failure (zero) under the frozen parser. Never
guess a random option for malformed output. Do not drop failed rows and quietly
renormalize: show coverage and worst/best completion bounds for missing outcomes.

Score MC letters against the joined answer, and open answers with a pinned
normalization/accepted-answer policy checked against the
[official scoring source](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/mmmu/utils/eval_utils.py).
Its MC parser contains a random fallback; this diagnostic contract deliberately
rejects that fallback and is **not leaderboard-equivalent**. Publish this scoring
difference. V uses a separate exact/numeric-tolerance fact rubric. Prefer
deterministic scoring; if expert judgment is necessary, publish agreement,
adjudication and any unmeasured judgment uncertainty. No free-text LLM judge is
assumed or silently substituted.

## 8. Metrics, uncertainty and release decision

For question `i`, condition `c`, average its two attempt grades into `y_ic`.
R's estimate is `A_c = sum_h (N_h/N) * mean_h(y_ic)` where `N` is the frozen
eligible test-frame count. A selected question's weight is `N_h/(N*n_h)`.
Report a subject-macro average separately; unequal test subject sizes mean it
is a different estimand. S supplies unweighted diagnostics only.

Report weighted O accuracy, image gain `A_O - A_N`, oracle gap `A_E - A_O`, and
paired degradation `D_k = A_O - A_Pk` for each valid severity. A negative D is
possible. Report rescue rate `P(E correct | O wrong)` with its actual denominator,
visual-fact accuracy and per-axis/subject/family margins. For rescue rate, pair
the same repeat positions and count E-correct attempts among O-wrong attempts;
use R weights for both numerator and denominator, and cluster uncertainty by
question. Conditional rates use complete paired attempts and are descriptive if
oracle/transform QA is incomplete;
missingness and eligible counts must accompany every table. Do not replace the
population estimate by an estimate conditional on N failing.

For a fixed-baseline comparison, use the **same selected questions and conditions**
on baseline B and candidate C. Define:

```text
visual-regression contrast = (A_E,C - A_O,C) - (A_E,B - A_O,B)
stress-regression contrast = (A_O,C - A_P2,C) - (A_O,B - A_P2,B)
```

Positive values flag a larger oracle gap or stress loss in C. Also compare E
accuracy and V facts; if reasoning ability changed, encoder attribution remains
confounded. Evaluate contrasts per relevant axis as well as overall: opposite
regressions can cancel in a global mean.

For fully observed R, use design-based stratified finite-population uncertainty
on **per-question paired differences**, including the `1-n_h/N_h` correction.
Noncensus cells need at least two observations; otherwise expand before a
confirmatory claim. Estimate variance as
`sum_h (N_h/N)^2 * (1-n_h/N_h) * s_h^2/n_h`. It quantifies sampling uncertainty
for the realized question outcomes; repeat variability and human/serving errors
remain separate. Use an explicitly documented small-sample method, not a claim
of exact normal coverage. Repeated images require a duplicate-group sensitivity
analysis; deterministic S has no design-based confidence interval. For overlapping
image-tag margins, show denominators and conservative uncertainty, not disjoint
stratum weights. Sparse cells should remain inconclusive.

Do a pilot precision/power calculation using paired discordance and the number
of simultaneous gates before freezing the budget. Three-point regression gates
may need far more than 360 population questions or 12 axis examples. If the
available budget cannot distinguish an unacceptable regression with the agreed
power, narrow the claim or expand before confirmation; coverage alone is not
statistical sufficiency. For missing scores, bound each missing attempt in
`[0,1]` using its original R weight and propagate those worst/best values into
the paired contrasts; never apply the complete-data variance formula to a
quietly renormalized incomplete panel.

Before test calls, agree customer capability minima, maximum acceptable stress
loss, visual-regression tolerance and maximum failure/cost budgets. For example,
an **illustrative**, not customer-supplied, release policy could require original
accuracy at least 70%, stress loss at most 5 percentage points and no greater
than 3-point baseline-relative visual regression on critical axes. A GO requires
all prespecified lower/upper bounds to clear the relevant minima/maxima, sufficient
coverage, valid controls and acceptable reliability. A bound entirely violating
a required gate supports NO GO; overlapping bounds or missing evidence mean
inconclusive and expansion/full evaluation. Use simultaneous bounds (e.g.
Bonferroni across the declared gates); do not cherry-pick a favorable axis.

Choose the final budget on validation/independent calibration systems, then make
one confirmatory test decision. No repeatedly peeking at test and expanding until
it passes. A new fixed confirmation frame or preregistered sequential inference
is needed for repeated inferential looks. Even GO is conditional evidence about
this workload/protocol, not certification of an internal encoder or production.

## 9. Budget, integration and next experiment

Nominally R=360 and S=120 means **480 unique test questions**, 4.57% of 10,500.
Six conditions times two attempts means **5,760 calls per system**, plus at most
30 separately logged preflight calls. Two systems double the main calls to
11,520. If S grows to 240, 600 unique questions require 7,200 calls per system.
The full 10,500-question evaluation with the **same** six-condition/two-attempt
protocol would require 126,000 calls per system. A one-pass original-only full
run needs 10,500: these are different deliverables. Question reduction is not
measured dollar, token or latency savings; include annotation and pilot costs,
retries and provider-dependent image costs. No dollar saving is established here.

A future implementation belongs **inside EvalScope**, extending `MMMUAdapter`
and the existing `VisionLanguageAdapter`/`load_subset` flow, not a parallel runner.
Keep the original adapter available. Register a separately named probe with
versioned selection/condition metadata, reuse native API/cache/report machinery,
and add public adapter/CLI tests using tiny local images and scripted responses.
These are future implementation steps, not commands that already exist.

At upstream commit `66f0945d145ce6c30de40253cd78144003c6f1fe`, the
[MMMU adapter](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/benchmarks/mmmu/mmmu_adapter.py)
defaults to validation, points to ModelScope with an HF fallback pinned to a
different revision, and still describes test answers as withheld. The proposal
must explicitly override source/revision/split and join the released answers;
running the default `mmmu` benchmark is not a full-test probe. Compare manifests
before interpreting scores. The current Part A `compare_runs` contract does not
implement six-condition MMMU diagnostics, so do not route these outputs through
it as if they were supported today.

Next: download and census the pinned full inventory, check released-label joins,
annotate/QA tags and controls, solve coverage feasibility, measure pilot cost,
freeze selection/settings/gates, then run the confirmatory probe on independent
systems. Until then the defensible result is a concrete experimental design with
explicit uncertainties, not a demonstrated smallest sufficient subset.
