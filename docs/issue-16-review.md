# Issue #16 two-axis review

Fixed base: `39a14597eee63d8e8063f500d7c58be880be1193`, fetched from main.
The implementation skill requested independent, parallel standards and spec
reviews of `git diff 39a14597eee63d8e8063f500d7c58be880be1193...HEAD`.

Implementation commits reviewed:

- `c71ef69` — Evaluate AA-LCR pruning candidates and judge sensitivity (#16).
- `2ce63cb` — Keep comparison baselines out of candidate registrations (#16).

## Standards

No documented-standard violations were found in AGENTS.md, domain/issue-tracker
conventions or the project configuration.

The initial review identified one P2 correctness defect in the newly configurable
public evaluation APIs: registering a reserved comparison-baseline name as a
candidate could duplicate runs and label that baseline as a candidate. It also
identified duplicated registration/dispatch logic as a possible design smell.

Commit `2ce63cb` resolves both. One validated `StudyStrategy` registry serves score
and pair evaluation, rejects empty/unnamed/duplicate/baseline-overlapping candidate
registrations, and fixes baseline roles as `comparison_baseline`. The manifest
fingerprints the shared module. Four regression configurations failed before the
fix and passed afterward; the reviewer independently ran all 15 focused API tests.

Follow-up review found no remaining actionable standards or maintainability
findings against the fixed base. **Unresolved findings: 0.**

## Spec

No missing/partial requirements, material scope creep, or incorrect implementation
of the issue's requirements were found.

Both candidates are nontrivial and evaluated at five retention levels. Input
length and source metadata form algorithmic strata, with target outcomes excluded
before fitting. Population weights, common-subset ranking, and independent pair
holdouts support the fidelity claims. Shared evaluator/report configuration is
justified by the additional benchmark.

Judge variance and flip rates correctly remain null without repeat reviews.
Conditional flip envelopes, full-score tipping counts and widened design intervals
are described with their assumptions. Reference refitting, future-task transfer,
semantic coverage and true judge accuracy are not claimed. The guide explains
why the feature signals may generalize and where evidence is insufficient.

Follow-up review confirmed that the registration fix introduces no spec regressions
and leaves default selection, weighting, holdouts and interpretation intact.
**Unresolved findings: 0.**

Final review: **Standards 0 unresolved; Spec 0 unresolved.** Neither axis has an
outstanding worst finding. Final validation: 119 tests pass, lint/format/type checks
pass, independent raw-data audit passes, and all eleven full-run outputs reproduce
byte-identically. See [acceptance evidence](issue-16-evidence.md).
