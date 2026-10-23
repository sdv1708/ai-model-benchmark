# Issue #23 acceptance evidence

Issue: [Prototype paired MMMU image transformations and measurements](https://github.com/sdv1708/ai-model-benchmark/issues/23).
Base: latest `main` pulled on 2026-10-23, commit
`b3c1902f948c4168b55e9e10975b78979542c3ee` (issue #22 merged).
Branch: `feature/issue-23-mmmu-paired-harness`.

The issue is learner-labelled. The user's explicit implement request authorized
assistant authorship. [The learning guide](../task2/ISSUE_23_GUIDE.md) supports
understanding and interview practice; synthetic tests must not be described as
real model experiments.

## Acceptance mapping

| Criterion | Implementation/evidence |
| --- | --- |
| Reproducible representative transformations | Seven fixed families at two severities; text regions and no-op applicability recorded. Synthetic chart, arrow diagram and small-text families demonstrate plumbing; real MMMU exports accepted through documented inventory. |
| Stable original/transformed identity | Sample/pair SHA-256 identities bind source provenance, question/options, all images, target, implementation/runtime and treatment; request/repeat IDs bind observations. CLI test rebuilds byte-identical outputs and preserves source bytes. |
| Accuracy drop, consistency, error categories | `paired_report` groups by approved transform/severity, shows both accuracy denominators, answer consistency, semantic/format/transport categories, coverage and fixed-denominator missing-outcome bounds. |
| No full-model conclusion without evidence | No endpoint executor; explicit synthetic/saved-record evidence kinds. Reports always deny population, full live-model and encoder-causal conclusions. Saved records are not independently authenticated. |
| Learner can explain pairing | Detailed child-sized examples, worked arithmetic, failure attribution, controls, rehearsable interview answers and exercises in the guide. Actual understanding requires learner practice. |

## Reproduce

From `task2/` with Python 3.12:

```powershell
uv sync --locked
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
uv run pytest --basetemp=.pytest-tmp/issue23-full
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Use fresh output/test destinations. The CLI also exposes `demo`, `build`, `plan`,
`report`; see [the exact contracts](../task2/MMMU_HARNESS.md).

## Observed synthetic demonstration

Run locally with the task2 Python 3.12.8 environment and Pillow 13.0.0:

- 3 unique synthetic questions, 38 pairs, 82 planned calls, 79 scripted responses.
- Color has no pixel effect on grayscale diagram/text, so four color variants
  are inapplicable. The report records them instead of pretending they degrade.
- Synthetic QA approves 32 pairs and labels six occlusions destructive controls.
  These are scripted reviewer fixtures, not real human annotations.
- Three strong-blur calls are deliberately missing. That group reports 3/6
  complete paired attempts and completion-loss bounds [0, 50] percentage points.
- The generated preview was visually inspected. It shows the seven operation
  families, fixed canvas and inapplicable saturation variants.

These are software execution facts, not observations of any model. No live
endpoint, full MMMU census, real-image panel selection or semantic study occurred.

## Verification

Targeted public-seam tests cover deterministic builds, all transformation
families, safe input/output failure, repeated and option images, answer-blind
plans, paired cancellation, format failures, missing outcomes, semantic QA
exclusion, tampered evidence rejection, inapplicability and open-answer parsing.

Final full-suite, type/format checks and independent review are recorded in
[the review record](issue-23-review.md).

Final result: **152 Task2 tests passed**, including 23 new harness tests; Ruff
lint/format and strict mypy passed. All 53 files from two complete fresh demos
were byte-identical. Both independent reviewers confirmed their two P2 findings
were resolved (unsupported image references and case-sensitive scientific units).
The supplied-message audit scanned 22 files / 660 rows and found only reasoning
and text content types, with no embedded image content.

## Limits and next experiment

The harness is a small offline prototype, not a native EvalScope pruner or the
entire issue #22 design. No-image, equivalent-text and fact-extraction controls,
source/label export audits, representative full-dataset selection, probability
weights, confidence intervals, power and release gates remain future work.
Recorded hashes establish internal consistency, not label truth or reviewer
authenticity. Exact bytes are reproducible in the same recorded runtime/codec
environment, not promised across arbitrary systems. Color-critical exports need
additional color-profile auditing. Consult the operating contract's primary
research links for transformation/API choices and attribution limitations.
