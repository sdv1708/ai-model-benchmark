# Issue #17: final two-axis review

Fixed point: `92a25332c6aa74540b2931bde5922f5e1b6c34fd` (latest main at start).
Initial implementation: `bd4416f`. Reviewed comparison:
`git diff 92a25332c6aa74540b2931bde5922f5e1b6c34fd...HEAD`, plus the
subsequent interval-completeness fix in the working tree. Reviewers were separate
parallel agents, and independently confirmed that fix before completion.

## Standards

One P2 documented-contract violation was found: available-interval summaries
could omit a missing bound and still pass the complete-uncertainty policy.
The policy comparison now requires `interval_count == run_count` in every
score and pair fold before coverage/width gates can pass. Twenty-seed synthetic
tests remove a single score or pair bound and demonstrate rejection of the
affected candidate. Both tests failed before the fix and passed afterward.

Final reviewer: “Hard documented violations: None remaining. Actionable judgment
smells: None.” Sources included AGENTS.md, docs/agents, task2 configuration and
guides. Existing auditor duplication was retained for independent verification.

**Unresolved Standards findings: 0.** No outstanding worst finding.

## Spec

The specification reviewer independently reproduced the same missing-interval
failure and confirmed its resolution. No missing deliverables or material scope
creep were found. The implementation separates excluded-model errors from
reference-assisted diagnostics, gates every model/pair/threshold separately,
excludes baseline promotion, and qualifies policy reuse, judge uncertainty and
the tested-grid fallback.

Both score and pair panels in the CLI are constructed from the same validated
raw score dictionary at nominal 95% confidence. The public comparison function's
panel checks are not a general provenance verifier for arbitrary externally
assembled run objects; use the raw-data CLI and manifest auditors for evidence.

**Unresolved Spec findings: 0.** No outstanding worst finding.

## Final validation

- **129 tests pass** in the complete Task 2 suite (35.61 seconds).
- Ruff lint passes; all **36 Python files** meet formatting checks.
- Strict mypy passes for **29 source/test/tool files**.
- `uv sync --locked` installs the new command; installed `--help` works.
- Coding auditor independently validates **1,500 score and 1,500 pair runs**.
- AA-LCR auditor independently validates **1,500 score and 1,500 pair runs**.
- New auditor independently reconstructs all **50 fidelity points**, gates,
  selected points and hashes without importing pipeline code.
- Final console-entry and module-entry runs in different output directories
  produce **all 22 reports byte-identically**, including manifests.
- Compact curves preserve original bytes. The selected-point extract records
  the complete source report's SHA-256, which matches the root manifest.

Final result: **Standards 0 unresolved; Spec 0 unresolved.** The conservative
illustrative policy retains 315 coding tasks and 100 AA-LCR tasks as full recorded
references. No smaller tested point passes; no production compression, fresh-model
generalization or resolution of judge uncertainty is certified.
