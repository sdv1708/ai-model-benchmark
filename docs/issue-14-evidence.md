# Issue #14 acceptance evidence

Verified October 14, 2026, on `feature/issue-14-benchmark-reference`, based on
`main` commit `c50e6270a436e1fa1ddb54bf119a495296c776d5`.

## Acceptance coverage

| Issue requirement                                              | Evidence                                                                                                                                                                              |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All shipped files parse and joins are validated                | Real-data run validates all 56 JSONL files and 28 prediction/review pairs, including MMMU                                                                                             |
| Expected counts and unique indices are asserted                | Each Part A pair requires 315 coding or 100 AA-LCR rows; MMMU requires 30 per subject; duplicate indices, unmatched sets, and wrong models fail                                       |
| Full-model scores are reproducible from a documented command   | [Package README](../task2/README.md) gives installation and CLI commands; two complete runs produce identical report bytes                                                            |
| Benchmark, model, and sample identity are retained             | Samples include benchmark/model/subset/index, metric, metadata, both relative source paths, and one-based source lines                                                                |
| Graders, scores, aggregation, and uncertainty can be explained | [Interview guide](../task2/INTERVIEW_GUIDE.md) explains the implemented choices and supplies rehearsal questions; the learner should rehearse these to verify their own understanding |

## Commands and observed results

From `task2/`, using Python 3.12.8:

```powershell
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run benchmark-reference --data-root ../Evals --output-dir output/reference
uv run benchmark-reference --data-root ../Evals --output-dir output/repeat
```

- Locked dependency synchronization passed.
- Tests: **63 passed**, no skips or expected failures.
- Ruff lint and format checks passed; 11 Python files are formatted.
- Strict mypy passed for nine source/test files.
- Both real-data runs: **28 pairs, 56 files, 1,905 normalized scored records,
  six Part A summaries**.
- All 56 supplied inputs total **964,345,076 bytes**.
- The three corresponding outputs from the two runs are byte-identical; manifest
  output hashes match the actual sample and score reports.
- An independent standard-library calculation reading the six Part A review files
  directly reproduced every summary's sample count, successful count, and mean.
  This check does not call the pipeline's normalization or aggregation functions.

These checks ran on the existing Windows host and project environment; this is
not a claim of a fresh operating-system or remote reviewer installation. Restricted
sandbox temporary-directory behavior interfered with initial test execution;
the final complete suite succeeded with normal host access. Input files were not
changed, and no live inference or regrading occurred.

## Full reference results

| Benchmark        | Model        | Successful / total | Mean     | Percent |
| ---------------- | ------------ | ------------------ | -------- | ------- |
| AA-LCR           | gpt-oss-120b | 48 / 100           | 0.480000 | 48.00%  |
| AA-LCR           | kimi-k2.5    | 66 / 100           | 0.660000 | 66.00%  |
| AA-LCR           | minimax-m2.5 | 64 / 100           | 0.640000 | 64.00%  |
| LiveCodeBench v5 | gpt-oss-120b | 241 / 315          | 0.765079 | 76.51%  |
| LiveCodeBench v5 | kimi-k2.5    | 198 / 315          | 0.628571 | 62.86%  |
| LiveCodeBench v5 | minimax-m2.5 | 195 / 315          | 0.619048 | 61.90%  |

Exact machine-readable values are in [task2-full-scores.json](data/task2-full-scores.json).
The [source manifest](data/task2-manifest.json) contains all 56 input SHA-256 hashes,
validated counts, scoring rules, and analysis limits. Full normalized sample output
is generated locally rather than duplicating all sample metadata in Git.

Part A has 1,245 scored records: three models evaluated on 415 supplied tasks.
MMMU adds 660 distinct reference tasks with subject-scoped indices, for 1,905
scored records overall. The six full-score summaries deliberately exclude MMMU.

## Interpretation and limits

The reference is the equally weighted mean of the complete **supplied** grades.
Missing or malformed grades abort the run; they are not dropped or turned into
zero. The recorded binary coding metric is `pass`; long-context and MMMU use `acc`.

These values establish a reproducible recorded baseline. They do not quantify
future-task generalization, generation randomness, or judge nondeterminism. AA-LCR
has one stored judgment per answer; resampling these fixed grades cannot isolate
judge noise. No confidence intervals or pass@k estimates are invented.

The inventory is intentionally fixed to the supplied challenge layout. The 660 MMMU
records are not the full approximately 12,000-row dataset. Nontrivial pruning,
fidelity curves, leave-one-model-out analysis, and evalscope integration remain
separate later tickets.

Output files are individually replaced atomically, with a hashed manifest published
last. The bundle is not a multi-file transaction. Readers should verify its output
hashes and exit status. Inputs are assumed static, and one writer should use each
output directory; the implementation does not supply concurrent snapshot isolation.
