# Issue #20 two-axis review

Fixed points: challenge `c0851e5cd73bb17403700032a5806fb9301ea187` and native
EvalScope `3e85032148a3e0024f33514ceb7f904dacbe048f`. Independent parallel
Standards and Spec reviewers inspected both implementations against these bases.
Follow-up reviews checked the repairs. No files were edited by reviewers.

## Standards

The native `AGENTS.md` requires judge-scored benchmark cases in
`tests/api/judge/test_migrated_adapters.py`. The original new feature file covered
those behaviors, but the cases were moved to the specified module and reuse its
existing scripted judge. An incidental encoding edit to an existing Unicode
fixture was identified and removed; the final diff only adds the intended cases.

The review judged the shared native selection/weighting adapter justified by
current LiveCodeBench and AA-LCR reuse. Registry, inheritance, metric identities
and import directions follow the documented architecture.

An optional Duplicated Code observation concerned the two challenge audit loops.
They remain benchmark-specific evidence scripts to avoid a generic runner for two
different source preparations. This is an accepted maintenance tradeoff, not a
documented standards violation or required fix.

Final Standards disposition: **0 unresolved actionable findings**.

## Spec

The initial documented CSV mirror path left token counts as strings. Strict
population metadata validation rejected those valid CSV fields. Record conversion
now accepts only ASCII decimal token strings and normalizes them to integers,
with a public native CSV regression.

Actual source loading also exposed four ZIP filename encoding errors, one with
decomposed Unicode. Exact CP437/NFD resolution and ambiguity rejection handle the
pinned archive without fuzzy matching. All 100 real pinned question contexts now
load through the documented native local-mirror path with no inference.

The reviewer confirmed the defended full-retention default, deterministic parity,
judge-noise disclosure, framework configuration tests, research provenance and
teaching guide satisfy the ticket. No material scope creep was found.

Final Spec disposition: **0 unresolved actionable findings**.

Standards: 0 unresolved; Spec: 0 unresolved. The final validation evidence records
the regression checks, real-source load and broader passing suites.
