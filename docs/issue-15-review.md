# Issue #15 two-axis code review

Reviewed `git diff main...HEAD` from fixed base
`fb6671daa9274c1b65be58cd39c18a923797dc35`, with separate parallel standards and
spec reviewers as required by the implementation skill.

Commits reviewed:

- `ed10e00` — Evaluate reference-only LiveCodeBench pruning candidates (#15)
- `75ad145` — Make pruning audit portable and share report safeguards

## Standards

No hard violations of documented repository standards were found. The first review
identified cross-checkout source-hash sensitivity (equivalent LF/CRLF source) and an
optional duplicated-code smell in report destination guards and atomic replacement.

Both are resolved in `75ad145`. Source fingerprints normalize CRLF to LF consistently
in report generation, regression assertions, and the independent auditor; raw input
and output hashes remain byte-exact. Both pipelines share `validate_output_location`
and `write_atomic`. The existing reference pipeline retains its default output names;
pruning explicitly supplies its five filenames. Atomic replacement and temporary
file cleanup remain intact. Follow-up review found no regressions or additional
documented-standard violations.

**Unresolved findings: 0.**

## Spec

No actionable requirement gaps, material scope creep, or incorrect behavior were
found. Both candidates use defensible historical coverage features, run across five
retention ratios and twenty seeds, and produce unique, reproducible, auditable
selections. Held-out grades are excluded before selection; population weights correct
disproportionate allocation; baselines remain comparisons; ordering uses common
subsets with tie-aware calculations.

Statistical limitations are accurately disclosed: ranking includes fitted reference
models, three folds provide limited transfer evidence, seed dispersion is descriptive,
and no production retention ratio is certified. The follow-up commit introduced no
spec regressions. Evalscope integration remains later project work.

**Unresolved findings: 0.**

Final review: **Standards 0 unresolved; Spec 0 unresolved.** No outstanding worst
finding within either axis. See [verification evidence](issue-15-evidence.md).

## Substantial revision review

The user then requested a more substantial implementation. Commit `2e29f9a`
adds exact finite-pool confidence intervals, independent pair-transfer evaluation,
optional threshold decisions with abstention, and extended audits and documentation.
The same two axes independently reviewed `git diff main...HEAD`, focusing on
`git diff d9ad8b2...HEAD` for this revision.

### Standards

No actionable findings. No documented-standard violations or material design smells
were identified. Hypergeometric inversion uses inclusive tail comparisons and exact
rational failure budgets; the strata/directional Bonferroni allocation is conservative.
Census intervals collapse correctly, pair selection excludes both targets, and
decision-summary denominators include abstentions.

The reviewer independently enumerated **11,700 finite-population coverage cases**:
population sizes 1–25, every sample size and population success count, at failure
budgets 0.05 and 0.5. Every computed interval met nominal coverage. This additional
review check is separate from the 102 automated tests.

Source fingerprints retain LF normalization and input/output fingerprints remain
byte-exact. The independent auditor's linear inversion deliberately differs from
production binary search. Explicit score and pair orchestration is justified by
their different holdout boundaries and results.

**Unresolved standards findings: 0.**

### Spec

No missing/partial requirements, incorrect behavior, or material scope creep found.
Both targets are removed before paired fitting. Confidence budgets are distributed
across strata and directional discordances without requiring independence. Original
selector, baseline, multi-ratio, reproducibility and auditability requirements remain
satisfied; the additional work strengthens score/ordering fidelity.

Claims remain qualified: exactness concerns finite-pool tail inversion under the
stated sampling design; fixed hash priorities approximate that design; coverage is
not simultaneous over a searched run panel. The guide separates reference-assisted
ordering from pair transfer, discloses the single remaining reference, and reports
abstention alongside decision errors.

**Unresolved spec findings: 0.**

Substantial-revision review: **Standards 0 unresolved; Spec 0 unresolved.** No
outstanding worst finding in either axis.
