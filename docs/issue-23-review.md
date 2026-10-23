# Issue #23 independent review and final verification

Reviewed against `main` at `b3c1902f948c4168b55e9e10975b78979542c3ee`.
Diff: `git diff main...HEAD`. Implementation commit `828c22b`; review repairs
`3c472de`. Two independent subagents performed Standards and Spec review as
required by the implement/code-review skills, then rechecked their findings.

## Standards

No documented coding-standard violations found in AGENTS.md/domain guidance.
No actionable baseline code smells. One P2 behavioral-contract finding:

> Unsupported numbered image references could pass the exact-reference check.
> The original regex only recognized image slots 1..7, so `<image 8>` could be
> retained as literal text instead of rejected. Recognize numbered placeholders
> broadly and reject unsupported values before publishing.

Resolved in `3c472de`. A public CLI regression first failed, then passed after
the validation repair; it verifies no bundle is published. Reviewer re-inspected
the current patch/tests and confirmed no remaining actionable concerns. This
was an operating-contract issue, not an AGENTS.md style violation.

## Spec

The bounded offline prototype satisfies the seven transformation families,
stable pairing, future request plans, paired measurements and honest evidence
limits. No additional missing requirement or material scope creep found.
One P2 measurement-correctness finding:

> Global case folding made `-12 MV` match accepted `-12 mV`, concealing a real
> scientific-unit error. This could inflate accuracy/consistency and mislabel
> transformed failures as stable correct. Preserve case and require explicit
> accepted alternatives.

Resolved in `3c472de`. Open scoring now collapses whitespace only. A public
paired-report test first reproduced the bug, then verified a 100-point loss and
regression categories for `mV` versus `MV`. Documentation and the existing parser
test were corrected. The reviewer independently ran both relevant open-answer
tests: **2 passed**, with no remaining Spec concerns.

Review totals: Standards 1 P2 resolved, 0 remaining; Spec 1 P2 resolved, 0 remaining.

## Final verification, 2026-10-23

Task2 environment: Windows, Python 3.12.8, Pillow 13.0.0, locked uv environment.

| Check | Result |
| --- | --- |
| `uv sync --locked` | Passed; installed CLI exposed all four commands |
| Full Task2 pytest suite | **152 passed in 50.08s**, including 23 new harness tests |
| `ruff check .` | Passed |
| `ruff format --check .` | 55 files already formatted |
| `mypy` | Passed, 40 source files |
| Two fresh complete synthetic demos | All **53 artifacts byte-identical** across runs |
| Demo size | 3 questions, 38 pairs, 82 planned calls, 79 scripted responses |
| Visual inspection | Generated contact sheet inspected; operations and no-op variants visible |
| Supplied-image audit | All 22 prediction files / 660 rows scanned; saved message content types only reasoning/text, no embedded image content |
| `git diff --check` | Passed |

The full suite ran once after code repairs. Subsequent edits only record these
results. No backend/frontend behavior changed. No endpoint or actual human
semantic study was run; no model accuracy, savings or encoder attribution is
established. See [acceptance evidence](issue-23-evidence.md), the
[operating contract](../task2/MMMU_HARNESS.md) and
[learning guide](../task2/ISSUE_23_GUIDE.md).
