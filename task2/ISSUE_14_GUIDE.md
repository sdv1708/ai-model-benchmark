# Issue #14: original implementation order

The implementation is now complete. This document preserves the original learning
sequence and acceptance checkpoints. Its TODO references describe the former
scaffold; use [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) for the finished design and
[README.md](README.md) for runnable commands and results.

Branch: `feature/issue-14-benchmark-reference`, created from local `main` at
`c50e6270a436e1fa1ddb54bf119a495296c776d5`.

Read `models.py` first. The dataclasses establish the shapes passed between stages;
you can adjust them if a discovered source requirement warrants it. Source line
numbers are one-based file positions, while indices identify samples. MMMU indices
restart per subject, so full identity is benchmark/model/subset/index.

## 1. Inventory the files — `inputs.discover_pairs`

- Inspect filenames under `Evals/Part 1` and `Evals/MMMU`.
- Match predictions and reviews using filename and relative directory identity.
- Part A: two benchmarks x three models = six pairs. Expected counts are 315
  for LiveCodeBench and 100 for AA-LCR; metric names are `pass` and `acc`.
- MMMU: 22 subject pairs x 30 samples. Set `include_in_reference=False`.
- Require all expected files; reject missing partners and unexpected inputs.
- Return stable order. Add inventory fixtures covering missing/orphan files.

Checkpoint: 28 pairs cover all 56 shipped JSONL files. A missing dataset cannot
silently look like a successful empty run. This is supplied-data validation;
don't turn these file counts into claims about upstream dataset releases.

## 2. Parse JSONL — `inputs.read_jsonl`

- Stream records with Python's standard `json` module.
- Attach path and line number. Validate each line is a JSON object.
- Detect LFS pointers and reject malformed/non-standard JSON and blank records.
- Raise `AnalysisError` with source context rather than swallowing exceptions.

Run `uv run pytest tests/test_reference.py -k reader`. Remove matching xfail
decorators as behaviors become implemented; add an LFS-pointer fixture.

Checkpoint: reordered records keep their original source lines.

## 3. Validate identity and joins — `inputs.index_rows`, then `inputs.join_rows`

- Detect duplicate indices before building the index lookup.
- Validate integer, nonnegative indices and expected counts.
- Require identical prediction/review index sets and the expected model identity.
- Return pairs sorted by index, independently of source row order.
- Add wrong-count, boolean-index, wrong-model, and missing-partner tests.

Checkpoint: equal row counts with different index sets fail. Never join by line
position: GPT-OSS AA-LCR starts at prediction index 73 and review index 71.

## 4. Extract normalized samples — `analysis.normalize_sample`, then `analyze_pair`

- Inspect both review schemas. Scores live at
  `sample_score.score.value[metric]`, not directly on `sample_score`.
- Check `main_score_name`. Require finite numeric binary scores for this data;
  reject booleans, absent metrics, and malformed nested objects.
- Validate matching identity and preserve both source locations.
- Inspect `model_output.error`; surface generation errors explicitly.
- Keep available sample and judge metadata. Document metadata conflict handling.
- Add AA-LCR, missing-score, invalid-score, and generation-error fixtures.

Checkpoint: the shuffled two-sample test yields index 0 => 1 and index 1 => 0.
The stored `messages` need not include original prompts; coding metadata is empty.
Don't invent problem difficulty, original prompts, or missing grades.

## 5. Aggregate — `analysis.aggregate_samples`

- Group by benchmark/model/subset/metric, checking identity uniqueness.
- Count all samples, sum scores, divide by count, and sort summaries consistently.
- Keep coding and long-context results separate; use a 0..1 output score scale.
- Add mixed-model/benchmark grouping, duplicate, empty, and invalid-score cases.

Checkpoint: `[1, 0, 1, 1]` yields count 4, sum 3, mean 0.75.
Missing data must fail validation rather than changing the denominator.

## 6. Serialize reports — `reporting.write_outputs`

- Implement the three output files described in README.md.
- Use stable record/key ordering, explicit UTF-8, and input-relative source paths.
- Hash every source file with SHA-256 and include validated row counts.
- State equal weighting, stored-output scope, and judge-noise limitations.
- Add a report test: two runs over the same fixture produce byte-identical files.

Checkpoint: another reader can trace a score to benchmark/model/subset/index,
both input files, and the corresponding line numbers. Do not export full model
answer text when only scores and metadata are needed for later selection.

## 7. Connect the CLI — `cli.run_analysis`

- Discover and analyze every pair, including MMMU validation.
- Aggregate only pairs with `include_in_reference=True` into full_scores.json.
- Validate all inputs before writing results; protect input paths from output writes.
- Replace the scaffold-only unfinished-CLI test with success/failure fixture cases.
- Run the README analysis command twice and compare output bytes/hashes.

Checkpoint: 1,245 Part A scored records (3 x (315 + 100)), six Part A summaries,
and 660 separately identified MMMU reference records in the complete sample output.
Totals are 1,905 normalized samples, not 1,905 unique benchmark questions.

## 8. Finish acceptance evidence and explain the result

- Remove every strict xfail and resolve every learner TODO; run pytest, Ruff,
  formatting, and mypy. Review missing cases listed above; starter tests are not
  complete acceptance coverage.
- Run against the real data and document the six observed scores and input hashes.
- Demonstrate the documented command from a fresh environment.
- Explain prediction vs review, graders, binary scores, equal-weight means,
  missing-data handling, sample identity, and reproducibility.
- Explain that the recorded full mean is exact for the provided artifacts.
  Generalization to new tasks, new generations, and repeated judging is uncertain.
  Bootstrap over fixed grades cannot estimate judge nondeterminism; don't report
  an invented confidence interval. Statistical validation follows in issues 16-17.

Issue #14 is complete when its five acceptance criteria have concrete evidence.
Pruning starts in #15/#16; evalscope integration starts with #18. No pruner or
live inference is needed to finish this issue.
