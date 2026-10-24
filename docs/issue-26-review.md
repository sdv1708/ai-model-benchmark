# Issue #26: independent two-axis review

Challenge fixed point: `7882d1623136727b28799b1405337456cd836650`;
initial documentation commit: `74011a50331423f268fe183f7e1a62b3f3529118`.
Native fixed point: `800119ff6870ca958f5d8459970f5fe75bfac305`;
initial documentation commit: `cadba2f439c69fc3c0720965fcfecdcb83b4214f`.

Review commands in each repository:

```powershell
git diff main...HEAD
git log main..HEAD --oneline
```

Both local main refs remain at the fixed points above. The user-invoked
implement skill requires the code-review skill's independent parallel Standards
and Spec agents. Neither reviewer edited files. Verification was still running
during initial review; provisional evidence paragraphs were explicitly excluded
and replaced with measured results before final handoff.

## Standards

**No actionable Standards findings in either repository.**

The documentation follows the applicable root `AGENTS.md` instructions and
neighboring guide/evidence conventions. Native generated benchmark pages,
registry metadata and runtime sources are untouched. Challenge domain instructions
explicitly allow absent `CONTEXT.md` and ADRs.

The guides distinguish historical evidence, synthetic demonstrations and proposed
experiments. They explicitly record that video, publication, reviewer access and
submission remain incomplete, without claiming all acceptance criteria are met.

No actionable Fowler baseline smells were identified. Repeated setup instructions
serve independently usable repository entrypoints; extracting them would weaken
that purpose. Tooling-enforced issues were excluded from the standards report.

## Spec

**Two findings repaired, independently confirmed resolved: one initial P2 and one
follow-up runbook correction.**

For the requirement that the walkthrough demonstrate integration, the initial
guides incorrectly pointed to `evalscope/benchmarks/pruning_smoke/` as shared
production implementation. Both production adapters actually inherit
`ReferencePruningAdapter` from `evalscope/benchmarks/_reference_pruning/adapter.py`,
with shared selection in adjacent `selection.py`. Both guides were corrected.
The Spec reviewer rechecked imports and source and confirmed the repair.

Otherwise, no material Spec findings. The reviewer checked pinned SHAs,
historical scores, 0.7/0.6 policy thresholds, retained counts, CLI flag semantics,
comparator fields/bounds/exit codes, weighting, limitations, handout links and
multimodal attribution. The skipped recording is an explicit user-authorized
scope adjustment; the original video criterion remains transparently unmet.

Fresh-clone verification additionally found that Windows' default CRLF checkout
fails the native LF formatter. The guides now use
`git clone -c core.autocrlf=false ...`, preserving the setting in the new local
repository for subsequent pinned checkouts. The reviewer endorsed that form;
fresh-clone formatter checking passed after re-checkout with LF endings.

During clean-clone repairs, the reviewer also caught a misleading instruction
to clear the process provider key before CI-lite. The test actually reads
`dotenv_values('.env')`. The final recipe checks that no local `.env` exists,
and explains why that is necessary to guarantee the mock path. The isolated
clone has no `.env`; no user environment file was removed or edited. The reviewer
confirmed this correction and the optional scikit-learn/pytest-parent instructions.

Standards: **0 findings**. Spec: **2 repaired, 0 unresolved** (initial worst: P2).
The original
video criterion remains unmet at the owner's direction, separate from review defects.
