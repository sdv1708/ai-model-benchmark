# Issue #21 two-axis review

Fixed native base: `9698587429f23a28daed3f341ca8b97aa5b1d28b`.
Challenge base: `12070a1` (latest fetched main before creating the issue branch).
The implement skill invoked independent parallel Standards and Spec reviewers.
The first implementation commit was `69d63d72`; repair review also inspected
the working-tree diff. Reviewers did not edit implementation files.

## Standards

The reviewer found no definite documented-standard violations. The change stays
within issue scope, preserves the native benchmark/judge architecture, uses
Pydantic models for the loader's cross-module result, and tests the user-confirmed
public CLI boundary with local evidence.

One optional **Primitive Obsession** observation concerns
`Question.trace: Optional[dict[str, Any]]`: keeping the validated `Trace` model
would preserve typed provenance across the module boundary. This is a maintenance
recommendation rather than a demonstrated correctness defect. The current code
validates traces before storing them and uses a Pydantic `SavedRun` contract.
It is recorded as an accepted maintenance tradeoff, not a hard violation.

Final Standards disposition: **0 hard violations; 1 optional maintenance observation**.

## Spec

The first review found four compatibility problems:

1. Cross-model ordering grouped only by benchmark/subset labels. Models could
   use different complete populations or judge protocols. Full input identities
   and generation/judge/scoring protocols now match before ordering is emitted.
2. Coding input identity omitted the hidden grading cases in `evaluation_sample`.
   Those cases now participate in the input hash, so grading-source drift fails.
3. Original AA-LCR mean reports counted repeated attempts while the loader expected
   unique questions. Validation now respects aggregation-specific counts, and
   output still separates unique questions from attempts.
4. Exact review means could differ from valid multi-subset report scores by more
   than one rounding step. Report validation now mirrors Native rounding at the
   subset/category/metric boundaries; comparison output retains exact review means.

The new public CLI tests first reproduced the ordering, hidden-test and rounding
failures, then passed after their fixes. The reviewer independently ran all seven
repair-specific cases: **7 passed**. The base AA-LCR repeated-run case also passes.

The follow-up review confirmed all four findings resolved and no material scope
creep or further correctness issue. Counts, weighted estimation, conservative
completion bounds, warnings, subprocess tests and documented smoke workflow
otherwise implement the requested behavior.

Final Spec disposition: **0 unresolved actionable findings**.

Standards: 0 hard violations, 1 optional maintenance observation; Spec: 0 unresolved.
