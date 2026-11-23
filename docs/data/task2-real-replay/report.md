# Real replay of frozen policy v1

This is the preregistered test of policy `threshold-policy@v1` (issue #63). The targets are 28 public LiveCodeBench models from 9 developer groups. None of them is in the 3-model reference panel that gives the strata. Each model gets 1,000 decisions at each of 61 thresholds from 0.30 to 0.90. A question passes when pass@1 is 50 or more. The secondary rule is pass@1 equal to 100. The full-set score uses the same rule as the probe.

## Result

**The replay passed all 3 pass criteria of the policy.**

At the primary threshold 0.70, a probe of 63 of 315 questions made 40.6% of 28,000 decisions on 28 unseen models. The other decisions graded the full set. Wrong decisions: 28 of 28,000. The mean expected cost was 0.674 of a full run, as the mean token estimate. Across all thresholds, the probe made 70.8% of 1,708,000 decisions. Wrong decisions: 601 of 1,708,000. The mean expected cost was 0.433 of a full run.

| Criterion | Rule | Worst or mean value | Limit | Outside the limit | Mark |
| --- | --- | ---: | ---: | ---: | ---: |
| Wrong-decision rate | For each model and threshold, the wrong-decision rate across the 1,000 seeds is at most 0.071. This is the pass rule of #60. | 0.0140 | 0.071 | 0 of 1708 | PASS |
| Coverage | For each model, the interval holds the full-set score in at least 0.935 of the 2,000 subsets at the policy stage-1 size. | 0.9500 | 0.935 | 0 of 28 | PASS |
| Mean expected cost | At the primary threshold, the mean expected cost across the models is below 1.0 of a full run. | 0.6744 | 1 | one mean | PASS |

The cost criterion uses the mean token estimate. The cost in questions gives the same mark, because both costs are 1.0 only when every decision escalates.

## Stated comparisons

The policy gives these comparisons no pass or fail mark.

| Scope | Probe | Decided at stage 1 | Wrong | Highest wrong rate | Cost, questions | Cost, tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Threshold 0.70 | stratified | 40.6% | 28 of 28,000 | 0.0080 | 0.675 | 0.674 |
| Threshold 0.70 | random | 42.3% | 84 of 28,000 | 0.0220 | 0.662 | 0.661 |
| All thresholds | stratified | 70.8% | 601 of 1,708,000 | 0.0140 | 0.434 | 0.433 |
| All thresholds | random | 69.2% | 1,645 of 1,708,000 | 0.0270 | 0.447 | 0.446 |

A cost is a share of a full run. The token cost is the mean estimate.

### Real d95 against simulated d95

d95 is a distance from the threshold. At d95 and at every larger distance, the probe makes at least 95% of the decisions. d95 is the smallest such distance. A real d95 at one threshold has one point for each model, so it is coarse. The second real row uses every combination of model and threshold. A side with the value "none" has no model, or its farthest model does not reach 95%.

| d95 | Below the threshold | At or above the threshold | Both sides |
| --- | ---: | ---: | ---: |
| Simulated (#60) | 0.180 | 0.160 | 0.180 |
| Real, threshold 0.70 | 0.310 | none | none |
| Real, all thresholds | 0.195 | 0.188 | 0.195 |

## Results by distance

The table uses the stratified probe and every combination of model and threshold. The distance ranges are a layout choice of this report. The policy does not set them, and no mark uses them.

| Distance from the threshold | Cells | Decided at stage 1 | Wrong | Highest wrong rate | Cost, tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.00 to below 0.02 | 101 | 2.1% | 426 of 101,000 | 0.0140 | 0.983 |
| 0.02 to below 0.05 | 153 | 6.8% | 151 of 153,000 | 0.0060 | 0.946 |
| 0.05 to below 0.10 | 248 | 29.1% | 24 of 248,000 | 0.0020 | 0.767 |
| 0.10 to below 0.15 | 236 | 70.9% | 0 of 236,000 | 0.0000 | 0.431 |
| 0.15 to below 0.20 | 206 | 93.9% | 0 of 206,000 | 0.0000 | 0.247 |
| 0.20 or more | 764 | 99.9% | 0 of 764,000 | 0.0000 | 0.199 |

## Results for each model

The full score is the share of the mapped questions that pass under the grade rule. The mean pass@1 is on the scale 0 to 100, for the same questions. "Neither 0 nor 100" counts the results with another value. The decided share and the cost are at the primary threshold 0.70. The highest wrong rate is the worst of the thresholds. The secondary columns use the secondary grade rule.

| Model | Developer | Full score | Mean pass@1 | Neither 0 nor 100 | Decided at stage 1 | Highest wrong rate | Coverage | Cost | Secondary full score | Secondary decided | Secondary wrong rate | Secondary coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O4-Mini (High) | OpenAI | 0.838 | 83.81 | 0 | 88.7% | 0.005 | 0.9950 | 0.288 | 0.838 | 88.7% | 0.005 | 0.9950 |
| O3 (High) | OpenAI | 0.781 | 78.10 | 0 | 31.4% | 0.006 | 0.9915 | 0.746 | 0.781 | 31.4% | 0.006 | 0.9915 |
| O4-Mini (Medium) | OpenAI | 0.771 | 77.14 | 0 | 21.9% | 0.005 | 0.9930 | 0.821 | 0.771 | 21.9% | 0.005 | 0.9930 |
| DeepSeek-R1-0528 | DeepSeek | 0.768 | 75.43 | 99 | 22.0% | 0.006 | 0.9890 | 0.820 | 0.578 | 61.5% | 0.009 | 0.9860 |
| EXAONE-4.0-32B | LG | 0.768 | 72.30 | 58 | 22.3% | 0.004 | 0.9915 | 0.818 | 0.616 | 29.7% | 0.006 | 0.9810 |
| OpenReasoning-Nemotron-32B | NVIDIA | 0.759 | 72.70 | 97 | 16.3% | 0.005 | 0.9840 | 0.867 | 0.537 | 87.8% | 0.009 | 0.9805 |
| Gemini-2.5-Pro-05-06 | Google | 0.756 | 75.56 | 0 | 12.2% | 0.004 | 0.9870 | 0.901 | 0.756 | 12.2% | 0.004 | 0.9870 |
| Gemini-2.5-Pro-06-05 | Google | 0.743 | 74.29 | 0 | 8.1% | 0.002 | 0.9905 | 0.934 | 0.743 | 8.1% | 0.002 | 0.9905 |
| OpenCodeReasoning-Nemotron-1.1-32B | NVIDIA | 0.743 | 70.70 | 97 | 8.7% | 0.005 | 0.9890 | 0.929 | 0.517 | 92.3% | 0.020 | 0.9775 |
| Qwen3-235B-A22B | Alibaba | 0.717 | 71.75 | 0 | 3.2% | 0.011 | 0.9775 | 0.974 | 0.717 | 3.2% | 0.011 | 0.9775 |
| Grok-3-Mini (High) | xAI | 0.705 | 70.48 | 0 | 3.0% | 0.008 | 0.9605 | 0.976 | 0.705 | 3.0% | 0.008 | 0.9605 |
| O3-Mini-2025-01-31 (High) | OpenAI | 0.705 | 70.48 | 0 | 0.9% | 0.006 | 0.9900 | 0.993 | 0.705 | 0.9% | 0.006 | 0.9900 |
| XBai-o4-medium | Developer of XBai-o4-medium | 0.695 | 69.52 | 0 | 1.8% | 0.008 | 0.9860 | 0.986 | 0.695 | 1.8% | 0.008 | 0.9860 |
| O3-Mini-2025-01-31 (Med) | OpenAI | 0.683 | 68.25 | 0 | 1.6% | 0.005 | 0.9890 | 0.988 | 0.683 | 1.6% | 0.005 | 0.9890 |
| O4-Mini (Low) | OpenAI | 0.683 | 68.25 | 0 | 2.3% | 0.005 | 0.9860 | 0.982 | 0.683 | 2.3% | 0.005 | 0.9860 |
| Gemini-2.5-Flash-05-20 | Google | 0.654 | 65.40 | 0 | 9.8% | 0.007 | 0.9905 | 0.923 | 0.654 | 9.8% | 0.007 | 0.9905 |
| Gemini-2.5-Flash-04-17 | Google | 0.648 | 64.76 | 0 | 11.7% | 0.008 | 0.9765 | 0.908 | 0.648 | 11.7% | 0.008 | 0.9765 |
| O3-Mini-2025-01-31 (Low) | OpenAI | 0.625 | 62.54 | 0 | 23.3% | 0.007 | 0.9845 | 0.816 | 0.625 | 23.3% | 0.007 | 0.9845 |
| Claude-Opus-4 (Thinking) | Anthropic | 0.619 | 61.90 | 0 | 30.4% | 0.007 | 0.9890 | 0.759 | 0.619 | 30.4% | 0.007 | 0.9890 |
| Claude-Sonnet-4 (Thinking) | Anthropic | 0.613 | 61.27 | 0 | 33.7% | 0.004 | 0.9760 | 0.733 | 0.613 | 33.7% | 0.004 | 0.9760 |
| Claude-Opus-4 | Anthropic | 0.537 | 53.65 | 0 | 90.6% | 0.005 | 0.9845 | 0.275 | 0.537 | 90.6% | 0.005 | 0.9845 |
| Claude-Sonnet-4 | Anthropic | 0.527 | 52.70 | 0 | 92.3% | 0.008 | 0.9845 | 0.261 | 0.527 | 92.3% | 0.008 | 0.9845 |
| Claude-3.5-Sonnet-20241022 | Anthropic | 0.390 | 37.49 | 40 | 100.0% | 0.014 | 0.9720 | 0.198 | 0.302 | 100.0% | 0.014 | 0.9685 |
| DeepSeek-V3 | DeepSeek | 0.356 | 36.76 | 50 | 100.0% | 0.012 | 0.9810 | 0.198 | 0.305 | 100.0% | 0.013 | 0.9680 |
| GPT-4O-2024-08-06 | OpenAI | 0.308 | 30.70 | 59 | 100.0% | 0.011 | 0.9675 | 0.198 | 0.216 | 100.0% | 0.000 | 0.9750 |
| GPT-4-Turbo-2024-04-09 | OpenAI | 0.298 | 29.71 | 54 | 100.0% | 0.011 | 0.9775 | 0.198 | 0.206 | 100.0% | 0.000 | 0.9655 |
| GPT-4O-mini-2024-07-18 | OpenAI | 0.273 | 27.65 | 38 | 100.0% | 0.004 | 0.9500 | 0.198 | 0.229 | 100.0% | 0.000 | 0.9675 |
| Claude-3-Haiku | Anthropic | 0.175 | 17.11 | 31 | 100.0% | 0.000 | 0.9625 | 0.198 | 0.127 | 100.0% | 0.000 | 0.9525 |

## Secondary results

### Secondary grade rule

Under the secondary grade rule (pass@1 of 100), 0 cells are above the wrong-rate limit and 0 models are below the coverage limit. At the primary threshold, the probe made 47.8% of the decisions, with 28 wrong decisions, at 0.617 of the cost of a full run. These values have no pass or fail mark.

### Indifference zone

The indifference zone of the primary result is 0, so every wrong decision counts: 601 across all thresholds. With the secondary zone of 0.02, a wrong decision counts only when the full-set score is that distance or more from the threshold: 175 wrong decisions stay.

### The 3 reference models

The replay holds out each saved model in turn. The LiveCodeBench strata come from the other two models. The AA-LCR strata come from the question metadata. Each model gets one decision for each seed of the policy section, at the primary threshold of the benchmark.

| Benchmark | Held-out model | Threshold | Full score | Truth | GO / NO GO / ESCALATE | Wrong | Mean questions | Cost, tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LiveCodeBench | gpt-oss-120b | 0.70 | 0.765 | GO | 3 / 0 / 17 | 0 of 20 | 277.2 | 0.875 |
| LiveCodeBench | kimi-k2.5 | 0.70 | 0.629 | NO GO | 0 / 8 / 12 | 0 of 20 | 214.2 | 0.682 |
| LiveCodeBench | minimax-m2.5 | 0.70 | 0.619 | NO GO | 0 / 6 / 14 | 0 of 20 | 239.4 | 0.760 |
| AA-LCR | gpt-oss-120b | 0.60 | 0.480 | NO GO | 0 / 4 / 16 | 0 of 20 | 86.0 | 0.860 |
| AA-LCR | kimi-k2.5 | 0.60 | 0.660 | GO | 0 / 0 / 20 | 0 of 20 | 100.0 | 1.000 |
| AA-LCR | minimax-m2.5 | 0.60 | 0.640 | GO | 1 / 0 / 19 | 0 of 20 | 96.5 | 0.965 |

Limits of this replay:

- There are only 3 models.
- Disclosure 1 applies: the author saw a replay on these models before the freeze.
- The models are not independent of each other: they answer the same questions, and they give each other the strata.
- The models are not independent of the policy: the simulated models that chose v1 start from their grades.
- The decisions of one model reuse the same grades.
- The AA-LCR strata use the question metadata only. Each held-out AA-LCR model therefore gets the same probes.
- An LLM judge gave the AA-LCR grades one time for each answer. Nobody measured the judge noise.

## Limits

- The 28 models come from 9 developer groups, and they are not independent. Some models are the same base model at different reasoning settings.
- The 1,000 decisions of one model at one threshold reuse the same grades. They measure the question selection only. They do not measure a new answer from the model.
- The public grades come from the LiveCodeBench harness. The reference grades come from EvalScope. This difference does not affect the validity of the interval. It can lower the share decided at stage 1.
- The token cost is an estimate. It uses the saved answers of the 3 reference models, because the public file has no token count.
- The thresholds reuse the same models and probes, so the cells of one model are not independent.
- The result holds for these 315 LiveCodeBench questions. It is no evidence for another benchmark.

## Disclosures

The policy text is a quote from the frozen file. The notes belong to this report, and they do not change the policy.

1. Policy text: "The author saw a scratch replay on the 3 reference models before this freeze. The rules choose every tuned value from simulated results only. This choice reduces the bias from that replay, but it does not remove it. The simulated models start from the grades of the same 3 reference models."
   Note: In this text, "the author" means the repository owner and the AI agents that worked for the owner. A session record of 29 October 2026 shows that an agent made a script for a scratch threshold replay. The script no longer exists, so this report cannot check what it read. The owner did not confirm this disclosure from memory.
2. Policy text: "Before this freeze, the author read these facts from the public panel: the file shape, the model names, and the count of each pass@1 value. The author also read the question dates, difficulty labels, and platforms, and the release_date field. Nobody computed a score or a decision of a public model."
   Note: The public loader (#75) parsed and range-checked every pass@1 value in memory before the freeze. Only model names and question metadata came out of the loader. The owner confirmed this disclosure with this note on 23 November 2026.
3. Policy text: "The ordering criterion of the pruned-set test changed after the author saw the 3-model results. The criterion now applies only to model pairs with a full-set gap of 0.10 or more. The author fixed this change before anyone read a public grade."
   Note: Before the freeze, the author read the count of each pass@1 value, as disclosure 2 says. Nobody computed a score, interval, or decision of a public model. The owner confirmed this disclosure with this note on 23 November 2026.

## Provenance

- Policy: `threshold-policy@v1`, SHA-256 `2b9e1d771567788ad4ee9213ab09484b7d0dce81c884782d949d5dde2814f1a8`.
- Command: `threshold-decision --policy policies/threshold-v1.json --real-grades --output-dir ../docs/data/task2-real-replay`.
- Commit: `9a7ce058d0c98d02b2d347b457b7ba1bdb188a5b`.
- git HEAD and the start marker recorded no earlier replay of this policy.
- Source of the public grades: LiveCodeBench, <https://livecodebench.github.io/performances_generation.json>, SHA-256 `17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1`. The source states no license, so the raw file is not in the repository. The outputs hold derived values for each model only.

Input hashes (SHA-256):

- `threshold-v1.json`: `2b9e1d771567788ad4ee9213ab09484b7d0dce81c884782d949d5dde2814f1a8`
- `lcb-reference-panel.json`: `e328aac064023db8ba3fa2b5ab423ff057c966d0733c4f52b63201dc35bdf83c`
- `aa-lcr-reference-panel.json`: `06e76276c366112af5ee056ba6d2bcdab13521bfce85d4f9294ce5864075a4e6`
- `lcb-public-mapping.json`: `fe59fae621c4a514e5f72838cb140a091f02926752436ba2b2d5bb62aa2a0e75`
- `Part 1/predictions/live_code_bench_v5__gpt-oss-120b.jsonl`: `251ba80edb5df9500476f64c7440ecc6bff71060fbb107da23e1f5b8ac42f692`
- `Part 1/predictions/live_code_bench_v5__kimi-k2.5.jsonl`: `5d63df790fd81d34033b3d27735f3025438c0a0ebb3374bbcb70b302ae19726f`
- `Part 1/predictions/live_code_bench_v5__minimax-m2.5.jsonl`: `cdbd7b6fbd0e5f6d3d7fe028fef68cb2c6177bdf7c4245de9aa20b369099054f`
- `Part 1/predictions/aa_lcr__gpt-oss-120b.jsonl`: `034b57ded68f19e5d7837008dc5149eafa7529939ec513c1f1e873290dd1c1f9`
- `Part 1/predictions/aa_lcr__kimi-k2.5.jsonl`: `32bda99ec08f13633c06e6c51c88248316cf81c4f7f095163d33f18961a595b9`
- `Part 1/predictions/aa_lcr__minimax-m2.5.jsonl`: `1ab5aa0b351731c22d4e5a84a22e93d5f0edc2c1f947aea51285a8773d1c4c35`
- `performances_generation.json`: `17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1`

The output hashes are in `manifest.json`.
