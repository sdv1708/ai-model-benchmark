# Issue #19 two-axis review

Reviewed challenge changes with `git diff origin/main...HEAD`, fixed main
`5a73f6bac224d7f5743b77f3b38f61060a7c66c7`, and native changes against private
main `66f0945d145ce6c30de40253cd78144003c6f1fe`. Native main does not contain
the prerequisite issue #18 extension, so reviewers additionally isolated issue #19
with `git diff 152d811484e0c3ad3d9329af9befb73e961d8872...HEAD`.

The implementation skill required two independent review agents. Standards sources
included both repositories' AGENTS.md, native CONTRIBUTING.md, source style/config
and import contracts, and the skill's Fowler smell baseline. The Spec reviewer read
issue #19, the full Task 2 brief and the validated analysis selector/operating point.

## Standards

The earlier documentation-process finding is resolved by attempting
configuration-dependent statistics, preserving unavailable statistics instead of
publishing a false zero, and completing real Chinese translation through upstream
tools. The adapter description explains the required reference configuration,
corrects generic `limit` examples, and provides a runnable offline example.

The ModelAPI exclusion fix follows existing contracts and has a focused regression
test. No actionable code-standard violations or meaningful baseline smells remain.
Guides and validation evidence were refreshed to reflect the actual translation
calls, final test count and unavailable generic default statistics.

**Standards: 0 remaining findings.**

## Spec

The review initially found target leakage when a public `ModelAPI` object used a
custom display ID. Such objects expose `model_name`, while Model wrappers expose
`name`; only the latter was resolved. The acceptance requirement that selected
IDs match validated held-out analysis requires excluding the evaluated model's
grades before strata are constructed.

The adapter now resolves both supported object forms. The new custom-display
regression failed before the fix and passed afterward. The independent reviewer
reran it and the existing string-model/order/exclusion test: **2 passed**.

No additional missing requirements or material scope creep were found.
Full-retention defaults, experimental smaller ratios, the 315-versus-880 population
distinction, and external provider/Docker limitations are explicitly documented.

**Spec: 0 remaining findings; initial P2 finding fixed.**

Final validation after the code fix: **123 relevant native tests**, including 32
feature tests and upstream CI-lite; **129 challenge Task 2 tests**; **1,200 native
parity cases**; **315 unique public-source matches**; Ruff/Mypy; five import
contracts; all applicable feature hooks. Repository-wide hooks retain only the
pre-existing Windows symlink-placeholder EOF limitation.

Final review totals: Standards **0**, Spec **0**; no outstanding severity in either axis.
