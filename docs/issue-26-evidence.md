# Issue #26: final documentation and written walkthrough

Authoritative issue: [#26](https://github.com/sdv1708/ai-model-benchmark/issues/26).
Read its body, empty comment thread, parent #1 and closed prerequisites #24/#25.
The explicit user implementation request overrides learner-labelled ownership;
the user also directs that video components may be skipped.

## Provenance and scope

Initial working trees were clean. Challenge main was pulled to
`7882d1623136727b28799b1405337456cd836650` and native EvalScope main to
`800119ff6870ca958f5d8459970f5fe75bfac305`, before creating
`feature/issue-26-task2-documentation` in each repository. Upstream base remains
`66f0945d145ce6c30de40253cd78144003c6f1fe`. Native main's runtime tree is identical
to the previous #21 implementation pin `5fd26289972f6d01b13ea95bb30481ebd103fa2d`.
This documentation issue introduces no runtime or selection-policy changes.
Optional TDD does not apply to editorial edits; existing public tests are reused.

## Acceptance mapping

| Issue requirement | Evidence / status |
| --- | --- |
| Pinned upstream SHA and required commands prominent | Both root READMEs; fork `TASK2_README.md`; challenge [final guide](../task2/ISSUE_26_GUIDE.md) |
| Clean clone can run relevant tests and reproduce analysis/comparison | Exact Python/dependency/runtime pins, native isolated-clone verification and challenge historical commands; results below |
| Walkthrough demonstrates integration and explains evidence | Seven-step written demonstration in both guides; native synthetic CLI demonstration; no recorded walkthrough |
| Trade-offs and limitations stated directly | Full-retention result, no live savings, retrospective-policy reuse, unknown judge variance, conditional GO, synthetic-only image harness and API causality limit |
| Accessible video link in checklist | **Unmet: skipped at user direction.** [Checklist](../SUBMISSION_CHECKLIST.md) explicitly records no URL/recording |

The issue is partially fulfilled against its original acceptance criteria because
video remains absent. No issue closure, remote publication, reviewer invitation,
deployment or submission-form action is performed. The native README is edited
in the actual EvalScope-derived repository, not only described in this submission.

## Research

- Actual source at native runtime pin: both pruned adapters, shared pruning
  helpers, smoke script, comparator, CLI and previous validation. Confirmed
  `--work-dir`, `--no-timestamp`, nested dataset arguments, retained-ratio meaning,
  frozen source population, weights, output identity checks and threshold semantics.
- Recorded [full scores](data/task2-full-scores.json),
  [selected operating points](data/task2-operating-selected.json) and
  [manifest](data/task2-operating-manifest.json): default grid, twenty seeds,
  illustrative thresholds 0.7 coding / 0.6 AA-LCR, defended 315/315 and 100/100.
- [Official EvalScope quick start](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html):
  evaluation and saved-output workflow. Pinned source controls exact commands.
- [Official MMMU README at the researched pin](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md):
  150 development + 900 validation + 10,500 test = 11,550; 30 subjects.
- [MMStar paper](https://arxiv.org/abs/2403.20330v2): motivates visual-dependence
  controls, not validation of this proposal's budgets or transformations.

Fresh verification and independent review results will be recorded below.
