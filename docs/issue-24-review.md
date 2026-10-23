# Issue #24: independent two-axis review

Fixed point: freshly pulled main
`0e49b9a4c6671450a7d83563a4cfa3772be3c9bd`.
Reviewed implementation: `8d34ba4 Write one-page technical Handout A for issue #24`.

```powershell
git diff 0e49b9a4c6671450a7d83563a4cfa3772be3c9bd...HEAD
git log 0e49b9a4c6671450a7d83563a4cfa3772be3c9bd..HEAD --oneline
```

The user-invoked implement skill requires the code-review skill, which requires
two independent parallel reviewers. The following reports are lightly cleaned
from their final responses. Neither reviewer edited the implementation. The
subsequent documentation commit records this review and final evidence only.

## Standards

**0 actionable findings.**

Reviewed the complete diff using `AGENTS.md`, domain and issue-tracker
conventions, `task2/pyproject.toml`, existing evidence/guide documents and the
existing documentation script. No root `CONTEXT.md` or ADRs exist.

The change follows the repository's documentation conventions: linked acceptance
evidence, reproducible commands, explicit experimental limitations and a separate
learner guide. The renderer keeps canonical content in Markdown, isolates
documentation dependencies and validates staged output before replacing the PDF.

No documented-standard breaches or actionable baseline code smells were
identified. Tooling-enforced style/type checks were excluded from this review.

## Spec

**0 findings.**

- Part A rationale: decision preservation, structured selection, population
  weighting and model-exclusion validation answer the approach/problem prompt.
- Defended size: 0% pruning, exact counts and measured failures match committed
  policy/curves; the minimum claim is explicitly restricted to tested sizes.
- Part B: full-MMMU population/diagnostic panels, targeted transformations,
  semantic review and controls answer the visual-probe prompt. Visual-path
  sensitivity is correctly distinguished from encoder-only causality.
- Assumptions: transfer, judge noise, retrospective policy, customer-distribution
  and cost limits are explicit.
- More resources: data, live endpoints and time each have concrete next steps.

Historical measurements, synthetic integration checks, assumptions and proposed
budgets remain distinct. The guide supplies calculations and rehearsal without
claiming additional experiments. Its scope is authorized by the user's detailed
interview-preparation request and does not inflate the one-page submission or
change benchmark behavior.

## Verification

See [acceptance evidence](issue-24-evidence.md) for the complete record:
152 Task 2 tests, Ruff lint/format, strict Mypy, three independent fresh-replay
auditors, canonical text/PDF equality, one-page render inspection and PDF binary
integrity. No implementation changes were required after independent review.

Total findings: Standards **0**, Spec **0**; neither axis has an unresolved issue.
