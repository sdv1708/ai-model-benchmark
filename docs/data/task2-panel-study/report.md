# Reference-panel study of frozen policy v1

This study (issue #77) runs policy `threshold-policy@v1` with the public models as the reference panel, on 315 and 1,055 LiveCodeBench questions. The targets are the 28 public models from 9 developer groups. For each target, the references are the public models outside the developer group of the target. The selector reads no grade of the target and no grade of its developer group. The strata are the reference pass rate, cut into 4 groups of near-equal size. Each model gets 1,000 decisions at each of 61 thresholds from 0.30 to 0.90, and 2,000 new subsets for the coverage check. A question passes when pass@1 is 50 or more. The secondary rule is pass@1 equal to 100. The full-set score uses the same rule as the probe.

## Result

**The 315-question arm passed all 3 pass criteria of the policy.** At the primary threshold 0.70, a probe of 63 of 315 questions made 40.3% of 28,000 decisions. Wrong decisions: 10. The mean expected cost was 0.678 of the questions. Across all thresholds, the probe made 70.7% of 1,708,000 decisions. Wrong decisions: 130. The mean expected cost was 0.434 of the questions.

**The 1,055-question arm passed all 3 pass criteria of the policy.** At the primary threshold 0.70, a probe of 211 of 1,055 questions made 82.7% of 28,000 decisions. Wrong decisions: 1. The mean expected cost was 0.338 of the questions. Across all thresholds, the probe made 84.1% of 1,708,000 decisions. Wrong decisions: 103. The mean expected cost was 0.327 of the questions.

| Arm | Criterion | Rule | Worst or mean value | Limit | Outside the limit | Mark |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 315 questions | Wrong-decision rate | For each model and threshold, the wrong-decision rate across the 1,000 seeds is at most 0.071. This is the pass rule of #60. | 0.0080 | 0.071 | 0 of 1708 | PASS |
| 315 questions | Coverage | For each model, the interval holds the full-set score in at least 0.935 of the 2,000 subsets at the policy stage-1 size. | 0.9740 | 0.935 | 0 of 28 | PASS |
| 315 questions | Mean expected cost | At the primary threshold, the mean expected cost across the models is below 1.0 of a full run. | 0.6762 | 1 | one mean | PASS |
| 1,055 questions | Wrong-decision rate | For each model and threshold, the wrong-decision rate across the 1,000 seeds is at most 0.071. This is the pass rule of #60. | 0.0080 | 0.071 | 0 of 1708 | PASS |
| 1,055 questions | Coverage | For each model, the interval holds the full-set score in at least 0.935 of the 2,000 subsets at the policy stage-1 size. | 0.9795 | 0.935 | 0 of 28 | PASS |
| 1,055 questions | Mean expected cost | At the primary threshold, the mean expected cost across the models is below 1.0 of a full run. | 0.3385 | 1 | one mean | PASS |

The marks use 4 groups and the primary grade rule. The cost value of the 315-question arm is the mean token estimate from the saved answers of the 3 reference models, as in #63. The cost value of the 1,055-question arm is in questions. The public file has no token counts, so this arm has no token cost. A cost in questions and a cost in tokens give the same mark, because both are 1.0 only when every decision escalates.

## The 315-question arm

The table puts three results side by side. The 3-model result is the record of #63. This study did not run it again. The random probe makes the decisions of the recorded random probe again, for each model, threshold, and grade rule. The two runs therefore used the same targets and the same questions.

| Scope | Probe | GO / NO GO / ESCALATE | Decided at stage 1 | Wrong | Highest wrong rate | Cost, questions | Cost, tokens | Lowest coverage | Mean interval width |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Threshold 0.70 | 3-model strata (#63) | 2,385 / 8,977 / 16,638 | 40.6% | 28 of 28,000 | 0.0080 | 0.675 | 0.674 | 0.9500 | 0.1962 |
| Threshold 0.70 | public-panel strata | 2,111 / 9,162 / 16,727 | 40.3% | 10 of 28,000 | 0.0040 | 0.678 | 0.676 | 0.9740 | 0.1965 |
| Threshold 0.70 | random probe | 2,673 / 9,161 / 16,166 | 42.3% | 84 of 28,000 | 0.0220 | 0.662 | 0.661 | not measured | not measured |
| All thresholds | 3-model strata (#63) | 651,056 / 557,580 / 499,364 | 70.8% | 601 of 1,708,000 | 0.0140 | 0.434 | 0.433 | 0.9500 | 0.1962 |
| All thresholds | public-panel strata | 649,313 / 558,487 / 500,200 | 70.7% | 130 of 1,708,000 | 0.0080 | 0.434 | 0.432 | 0.9740 | 0.1965 |
| All thresholds | random probe | 641,630 / 540,019 / 526,351 | 69.2% | 1,645 of 1,708,000 | 0.0270 | 0.447 | 0.446 | not measured | not measured |

### The larger reference panel

- Threshold 0.70: with the public-panel strata, the share decided at stage 1 is 0.3 percentage points lower (40.3% against 40.6%). Wrong decisions: 10 against 28 of 28,000. Mean cost in questions: 0.678 against 0.675.
- All thresholds: with the public-panel strata, the share decided at stage 1 is the same to 0.1 percentage points (70.7% against 70.8%). Wrong decisions: 130 against 601 of 1,708,000. Mean cost in questions: 0.434 against 0.434.

### The random probe

- Threshold 0.70, against the 3-model strata (#63): the random probe decides 42.3% at stage 1, against 40.6% (more). It makes 84 wrong decisions of 28,000, against 28 (more). **The random probe is equal or better on decided share.**
- Threshold 0.70, against the public-panel strata: the random probe decides 42.3% at stage 1, against 40.3% (more). It makes 84 wrong decisions of 28,000, against 10 (more). **The random probe is equal or better on decided share.**
- All thresholds, against the 3-model strata (#63): the random probe decides 69.2% at stage 1, against 70.8% (fewer). It makes 1,645 wrong decisions of 1,708,000, against 601 (more). The random probe is worse on both measures.
- All thresholds, against the public-panel strata: the random probe decides 69.2% at stage 1, against 70.7% (fewer). It makes 1,645 wrong decisions of 1,708,000, against 130 (more). The random probe is worse on both measures.

## The 1,055-question arm

This arm uses every public question and a probe of 211 questions, the stage-1 fraction of the policy. The public file has no token counts, so the cost of this arm is in questions.

| Scope | Probe | GO / NO GO / ESCALATE | Decided at stage 1 | Wrong | Highest wrong rate | Cost, questions | Lowest coverage | Mean interval width |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Threshold 0.70 | public-panel strata | 15,300 / 7,853 / 4,847 | 82.7% | 1 of 28,000 | 0.0010 | 0.338 | 0.9795 | 0.1016 |
| Threshold 0.70 | random probe | 14,969 / 7,730 / 5,301 | 81.1% | 25 of 28,000 | 0.0110 | 0.351 | not measured | not measured |
| All thresholds | public-panel strata | 980,179 / 456,321 / 271,500 | 84.1% | 103 of 1,708,000 | 0.0080 | 0.327 | 0.9795 | 0.1016 |
| All thresholds | random probe | 979,392 / 447,918 / 280,690 | 83.6% | 1,070 of 1,708,000 | 0.0300 | 0.331 | not measured | not measured |

### The random probe

- Threshold 0.70, against the public-panel strata: the random probe decides 81.1% at stage 1, against 82.7% (fewer). It makes 25 wrong decisions of 28,000, against 1 (more). The random probe is worse on both measures.
- All thresholds, against the public-panel strata: the random probe decides 83.6% at stage 1, against 84.1% (fewer). It makes 1,070 wrong decisions of 1,708,000, against 103 (more). The random probe is worse on both measures.

## Share decided at stage 1 by distance

The distance is the distance of the full-set score from the threshold. The table uses every combination of model and threshold, with 4 groups and the primary grade rule. A column with a probe name gives the share decided at stage 1. `distance.csv` gives the same shares in steps of 0.01, for each side of the threshold. The distance ranges are a layout choice, and no mark uses them.

| Distance from the threshold | 315: cells | 315: 3-model strata (#63) | 315: public-panel strata | 315: random probe | 1,055: cells | 1,055: public-panel strata | 1,055: random probe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 to below 0.02 | 101 | 2.1% | 0.6% | 4.0% | 108 | 2.1% | 6.2% |
| 0.02 to below 0.05 | 153 | 6.8% | 3.3% | 9.1% | 160 | 23.1% | 26.1% |
| 0.05 to below 0.10 | 248 | 29.1% | 25.4% | 28.3% | 235 | 82.0% | 75.1% |
| 0.10 to below 0.15 | 236 | 70.9% | 74.4% | 63.8% | 197 | 99.8% | 98.8% |
| 0.15 to below 0.20 | 206 | 93.9% | 97.0% | 88.6% | 175 | 100.0% | 100.0% |
| 0.20 or more | 764 | 99.9% | 100.0% | 99.5% | 833 | 100.0% | 100.0% |

d95 is a distance from the threshold. At d95 and at every larger distance, the probe makes at least 95% of the decisions. d95 is the smallest such distance. The simulated row uses the 3-model strata at one threshold. A real row at one threshold has one point for each model, so it is coarse. The value "none" means that the side has no model, or that its farthest model does not reach 95%.

| d95 | Below the threshold | At or above the threshold | Both sides |
| --- | ---: | ---: | ---: |
| Simulated (#60), 315 questions, threshold 0.70 | 0.180 | 0.160 | 0.180 |
| 315 questions, 3-model strata (#63), threshold 0.70 | 0.310 | none | none |
| 315 questions, 3-model strata (#63), all thresholds | 0.195 | 0.188 | 0.195 |
| 315 questions, public-panel strata, threshold 0.70 | 0.163 | none | none |
| 315 questions, public-panel strata, all thresholds | 0.175 | 0.173 | 0.175 |
| 315 questions, random probe, threshold 0.70 | 0.310 | none | none |
| 315 questions, random probe, all thresholds | 0.207 | 0.208 | 0.208 |
| 1,055 questions, public-panel strata, threshold 0.70 | 0.106 | 0.101 | 0.106 |
| 1,055 questions, public-panel strata, all thresholds | 0.096 | 0.095 | 0.096 |
| 1,055 questions, random probe, threshold 0.70 | 0.205 | 0.101 | 0.205 |
| 1,055 questions, random probe, all thresholds | 0.116 | 0.106 | 0.116 |

### Where the random probe decides as much or more

Each line names the ranges in which the share of the random probe is equal or larger.

- 315 questions, against the 3-model strata (#63): 0.00 to below 0.02, 0.02 to below 0.05.
- 315 questions, against the public-panel strata: 0.00 to below 0.02, 0.02 to below 0.05, 0.05 to below 0.10.
- 1,055 questions, against the public-panel strata: 0.00 to below 0.02, 0.02 to below 0.05, 0.20 or more.

## Secondary results

### 8 groups and the secondary grade rule

The first row of each arm is the result above. Each other row changes one value. The grade rule applies to the reference models and to the targets. The secondary rows have no pass or fail mark.

| Questions | Grade rule | Groups | Decided at 0.70 | Random probe at 0.70 | Wrong at 0.70 | Random wrong at 0.70 | Decided, all thresholds | Wrong, all thresholds | Highest wrong rate | Lowest coverage | Cells above the wrong-rate limit | Models below the coverage limit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 315 | primary | 4 | 40.3% | 42.3% | 10 | 84 | 70.7% | 130 | 0.0080 | 0.9740 | 0 | 0 |
| 315 | primary | 8 | 37.4% | 42.3% | 10 | 84 | 70.5% | 85 | 0.0150 | 0.9815 | 0 | 0 |
| 315 | secondary | 4 | 49.2% | 48.9% | 9 | 84 | 72.1% | 122 | 0.0080 | 0.9780 | 0 | 0 |
| 1,055 | primary | 4 | 82.7% | 81.1% | 1 | 25 | 84.1% | 103 | 0.0080 | 0.9795 | 0 | 0 |
| 1,055 | primary | 8 | 82.0% | 81.1% | 0 | 25 | 83.9% | 47 | 0.0050 | 0.9870 | 0 | 0 |
| 1,055 | secondary | 4 | 74.1% | 72.5% | 3 | 28 | 84.7% | 110 | 0.0090 | 0.9780 | 0 | 0 |

The random probe against each secondary row:

- 315 questions, primary grade rule, 8 groups, threshold 0.70: the random probe decides 42.3% against 37.4%, with 84 wrong decisions against 10. **The random probe is equal or better on decided share.**
- 315 questions, primary grade rule, 8 groups, all thresholds: the random probe decides 69.2% against 70.5%, with 1,645 wrong decisions against 85. The random probe is worse on both measures.
- 315 questions, secondary grade rule, 4 groups, threshold 0.70: the random probe decides 48.9% against 49.2%, with 84 wrong decisions against 9. The random probe is worse on both measures.
- 315 questions, secondary grade rule, 4 groups, all thresholds: the random probe decides 70.5% against 72.1%, with 1,537 wrong decisions against 122. The random probe is worse on both measures.
- 1,055 questions, primary grade rule, 8 groups, threshold 0.70: the random probe decides 81.1% against 82.0%, with 25 wrong decisions against 0. The random probe is worse on both measures.
- 1,055 questions, primary grade rule, 8 groups, all thresholds: the random probe decides 83.6% against 83.9%, with 1,070 wrong decisions against 47. The random probe is worse on both measures.
- 1,055 questions, secondary grade rule, 4 groups, threshold 0.70: the random probe decides 72.5% against 74.1%, with 28 wrong decisions against 3. The random probe is worse on both measures.
- 1,055 questions, secondary grade rule, 4 groups, all thresholds: the random probe decides 84.1% against 84.7%, with 999 wrong decisions against 110. The random probe is worse on both measures.

### Indifference zone

A wrong decision counts only when the full-set score is the zone or more from the threshold. The counts use the public-panel strata and all thresholds.

- 315 questions: 130 wrong decisions with a zone of 0, 22 wrong decisions with a zone of 0.02.
- 1,055 questions: 103 wrong decisions with a zone of 0, 3 wrong decisions with a zone of 0.02.

## Results for each model

The decided shares and the cost are at the primary threshold 0.70. The cost, the highest wrong rate of all thresholds, and the coverage are of the public-panel strata. `cells.csv` gives every threshold.

### 315 questions

| Model | Developer | Reference models | Full score | Decided, 3-model strata (#63) | Decided, public-panel strata | Decided, random probe | Cost, questions | Highest wrong rate | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O4-Mini (High) | OpenAI | 18 | 0.838 | 88.7% | 89.2% | 79.0% | 0.286 | 0.006 | 0.9840 |
| O3 (High) | OpenAI | 18 | 0.781 | 31.4% | 34.0% | 33.6% | 0.728 | 0.005 | 0.9905 |
| O4-Mini (Medium) | OpenAI | 18 | 0.771 | 21.9% | 22.4% | 25.2% | 0.821 | 0.007 | 0.9920 |
| DeepSeek-R1-0528 | DeepSeek | 26 | 0.768 | 22.0% | 18.9% | 27.3% | 0.849 | 0.002 | 0.9985 |
| EXAONE-4.0-32B | LG | 27 | 0.768 | 22.3% | 17.2% | 25.9% | 0.862 | 0.000 | 0.9995 |
| OpenReasoning-Nemotron-32B | NVIDIA | 26 | 0.759 | 16.3% | 6.6% | 19.9% | 0.947 | 0.000 | 1.0000 |
| Gemini-2.5-Pro-05-06 | Google | 24 | 0.756 | 12.2% | 9.5% | 17.1% | 0.924 | 0.000 | 0.9930 |
| Gemini-2.5-Pro-06-05 | Google | 24 | 0.743 | 8.1% | 4.9% | 13.5% | 0.961 | 0.001 | 0.9985 |
| OpenCodeReasoning-Nemotron-1.1-32B | NVIDIA | 26 | 0.743 | 8.7% | 4.1% | 12.3% | 0.967 | 0.000 | 0.9995 |
| Qwen3-235B-A22B | Alibaba | 27 | 0.717 | 3.2% | 0.7% | 4.9% | 0.994 | 0.000 | 0.9985 |
| Grok-3-Mini (High) | xAI | 27 | 0.705 | 3.0% | 3.2% | 4.9% | 0.974 | 0.008 | 0.9740 |
| O3-Mini-2025-01-31 (High) | OpenAI | 18 | 0.705 | 0.9% | 1.0% | 4.9% | 0.992 | 0.004 | 0.9985 |
| XBai-o4-medium | Developer of XBai-o4-medium | 27 | 0.695 | 1.8% | 0.4% | 4.4% | 0.997 | 0.002 | 0.9975 |
| O3-Mini-2025-01-31 (Med) | OpenAI | 18 | 0.683 | 1.6% | 1.2% | 5.9% | 0.990 | 0.000 | 0.9965 |
| O4-Mini (Low) | OpenAI | 18 | 0.683 | 2.3% | 0.4% | 5.2% | 0.997 | 0.002 | 0.9995 |
| Gemini-2.5-Flash-05-20 | Google | 24 | 0.654 | 9.8% | 8.6% | 13.9% | 0.931 | 0.000 | 0.9985 |
| Gemini-2.5-Flash-04-17 | Google | 24 | 0.648 | 11.7% | 10.1% | 16.8% | 0.919 | 0.000 | 0.9970 |
| O3-Mini-2025-01-31 (Low) | OpenAI | 18 | 0.625 | 23.3% | 25.7% | 27.1% | 0.794 | 0.001 | 0.9990 |
| Claude-Opus-4 (Thinking) | Anthropic | 22 | 0.619 | 30.4% | 35.4% | 34.0% | 0.717 | 0.000 | 0.9995 |
| Claude-Sonnet-4 (Thinking) | Anthropic | 22 | 0.613 | 33.7% | 39.5% | 35.5% | 0.684 | 0.001 | 0.9965 |
| Claude-Opus-4 | Anthropic | 22 | 0.537 | 90.6% | 96.8% | 84.7% | 0.226 | 0.001 | 0.9940 |
| Claude-Sonnet-4 | Anthropic | 22 | 0.527 | 92.3% | 97.5% | 87.4% | 0.220 | 0.004 | 0.9960 |
| Claude-3.5-Sonnet-20241022 | Anthropic | 22 | 0.390 | 100.0% | 100.0% | 100.0% | 0.200 | 0.003 | 0.9925 |
| DeepSeek-V3 | DeepSeek | 26 | 0.356 | 100.0% | 100.0% | 100.0% | 0.200 | 0.003 | 0.9990 |
| GPT-4O-2024-08-06 | OpenAI | 18 | 0.308 | 100.0% | 100.0% | 100.0% | 0.200 | 0.002 | 0.9970 |
| GPT-4-Turbo-2024-04-09 | OpenAI | 18 | 0.298 | 100.0% | 100.0% | 100.0% | 0.200 | 0.000 | 0.9995 |
| GPT-4O-mini-2024-07-18 | OpenAI | 18 | 0.273 | 100.0% | 100.0% | 100.0% | 0.200 | 0.000 | 0.9975 |
| Claude-3-Haiku | Anthropic | 22 | 0.175 | 100.0% | 100.0% | 100.0% | 0.200 | 0.000 | 0.9920 |

### 1,055 questions

| Model | Developer | Reference models | Full score | Decided, public-panel strata | Decided, random probe | Cost, questions | Highest wrong rate | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O4-Mini (High) | OpenAI | 18 | 0.873 | 100.0% | 100.0% | 0.200 | 0.006 | 0.9795 |
| DeepSeek-R1-0528 | DeepSeek | 26 | 0.854 | 100.0% | 100.0% | 0.200 | 0.000 | 0.9960 |
| O3 (High) | OpenAI | 18 | 0.847 | 100.0% | 100.0% | 0.200 | 0.008 | 0.9880 |
| O4-Mini (Medium) | OpenAI | 18 | 0.845 | 100.0% | 100.0% | 0.200 | 0.003 | 0.9825 |
| Gemini-2.5-Pro-06-05 | Google | 24 | 0.843 | 100.0% | 100.0% | 0.200 | 0.002 | 0.9935 |
| EXAONE-4.0-32B | LG | 27 | 0.840 | 100.0% | 100.0% | 0.200 | 0.002 | 0.9930 |
| OpenReasoning-Nemotron-32B | NVIDIA | 26 | 0.837 | 100.0% | 100.0% | 0.200 | 0.003 | 0.9950 |
| Gemini-2.5-Pro-05-06 | Google | 24 | 0.827 | 100.0% | 100.0% | 0.200 | 0.006 | 0.9950 |
| OpenCodeReasoning-Nemotron-1.1-32B | NVIDIA | 26 | 0.817 | 100.0% | 99.8% | 0.200 | 0.001 | 0.9985 |
| Qwen3-235B-A22B | Alibaba | 27 | 0.804 | 100.0% | 97.3% | 0.200 | 0.003 | 0.9985 |
| XBai-o4-medium | Developer of XBai-o4-medium | 27 | 0.801 | 100.0% | 97.0% | 0.200 | 0.001 | 0.9965 |
| Grok-3-Mini (High) | xAI | 27 | 0.781 | 90.0% | 85.2% | 0.280 | 0.005 | 0.9870 |
| O3-Mini-2025-01-31 (High) | OpenAI | 18 | 0.777 | 90.7% | 82.2% | 0.274 | 0.004 | 0.9850 |
| O4-Mini (Low) | OpenAI | 18 | 0.774 | 86.9% | 76.2% | 0.305 | 0.003 | 0.9935 |
| Gemini-2.5-Flash-05-20 | Google | 24 | 0.762 | 69.7% | 61.3% | 0.442 | 0.001 | 0.9940 |
| O3-Mini-2025-01-31 (Med) | OpenAI | 18 | 0.754 | 49.0% | 48.2% | 0.608 | 0.001 | 0.9910 |
| Gemini-2.5-Flash-04-17 | Google | 24 | 0.751 | 42.6% | 42.9% | 0.659 | 0.001 | 0.9950 |
| O3-Mini-2025-01-31 (Low) | OpenAI | 18 | 0.706 | 0.9% | 4.3% | 0.993 | 0.002 | 0.9965 |
| Claude-Opus-4 (Thinking) | Anthropic | 22 | 0.704 | 0.3% | 4.0% | 0.998 | 0.000 | 0.9950 |
| Claude-Sonnet-4 (Thinking) | Anthropic | 22 | 0.685 | 1.5% | 5.8% | 0.988 | 0.002 | 0.9970 |
| Claude-Opus-4 | Anthropic | 22 | 0.624 | 84.3% | 71.6% | 0.326 | 0.002 | 0.9965 |
| Claude-Sonnet-4 | Anthropic | 22 | 0.594 | 99.4% | 94.1% | 0.205 | 0.001 | 0.9965 |
| DeepSeek-V3 | DeepSeek | 26 | 0.495 | 100.0% | 100.0% | 0.200 | 0.002 | 0.9930 |
| Claude-3.5-Sonnet-20241022 | Anthropic | 22 | 0.492 | 100.0% | 100.0% | 0.200 | 0.005 | 0.9940 |
| GPT-4O-2024-08-06 | OpenAI | 18 | 0.380 | 100.0% | 100.0% | 0.200 | 0.002 | 0.9960 |
| GPT-4-Turbo-2024-04-09 | OpenAI | 18 | 0.377 | 100.0% | 100.0% | 0.200 | 0.003 | 0.9955 |
| GPT-4O-mini-2024-07-18 | OpenAI | 18 | 0.351 | 100.0% | 100.0% | 0.200 | 0.002 | 0.9955 |
| Claude-3-Haiku | Anthropic | 22 | 0.229 | 100.0% | 100.0% | 0.200 | 0.000 | 0.9905 |

## Limits

- The 28 models come from 9 developer groups, and they are not independent. Some models are the same base model at different reasoning settings. A developer group is also no proof of independence: a model can start from a base model or from outputs of another developer.
- The 1,000 decisions of one model at one threshold reuse the same grades. They measure the question selection only. They do not measure a new answer from the model.
- Policy v1 fixed the developer groups, the group counts, the probe sizes, the grade rules, the thresholds, and the seeds. Nobody had computed a score or a decision of a public model then. The authors knew the result of #63 on the same models before they wrote the code of this study.
- The policy leaves two points open, and this code chooses them. The first point is the split of questions with the same reference pass rate. This code splits them by question index: the panel index for the mapped questions, and the position in identifier order for the full question set. The second point is the grade rule of the references. This code uses one rule for the references and for the targets. Neither choice uses a grade of a target.
- The public-panel strata differ from the 3-model strata in more than the number of models. The public grades of the references come from the same harness as the grades of the targets. The 3-model strata come from the EvalScope grades, and they have unequal sizes.
- The stratified probe uses the stratified_wilson interval. The random probe uses the pooled_exact_hypergeometric interval, as policy v1 fixes. A difference between the two probes is therefore a difference of the questions and of the interval together.
- The full question set holds the mapped questions. The two arms are therefore not independent. They also differ in the probe size, the questions, and the full score of each model.
- The thresholds reuse the same models and probes, so the cells of one model are not independent.
- The strata use the grades of other public models on every question. A new benchmark has no such grades before someone runs a panel of models on it.

## Disclosures

The policy text is a quote from the frozen file. The notes are the notes of the #63 report, and they do not change the policy.

1. Policy text: "The author saw a scratch replay on the 3 reference models before this freeze. The rules choose every tuned value from simulated results only. This choice reduces the bias from that replay, but it does not remove it. The simulated models start from the grades of the same 3 reference models."
   Note: In this text, "the author" means the repository owner and the AI agents that worked for the owner. A session record of 29 October 2026 shows that an agent made a script for a scratch threshold replay. The script no longer exists, so this report cannot check what it read. The owner did not confirm this disclosure from memory.
2. Policy text: "Before this freeze, the author read these facts from the public panel: the file shape, the model names, and the count of each pass@1 value. The author also read the question dates, difficulty labels, and platforms, and the release_date field. Nobody computed a score or a decision of a public model."
   Note: The public loader (#75) parsed and range-checked every pass@1 value in memory before the freeze. Only model names and question metadata came out of the loader. The owner confirmed this disclosure with this note on 23 November 2026.
3. Policy text: "The ordering criterion of the pruned-set test changed after the author saw the 3-model results. The criterion now applies only to model pairs with a full-set gap of 0.10 or more. The author fixed this change before anyone read a public grade."
   Note: Before the freeze, the author read the count of each pass@1 value, as disclosure 2 says. Nobody computed a score, interval, or decision of a public model. The owner confirmed this disclosure with this note on 23 November 2026.

## Provenance

- Policy: `threshold-policy@v1`, SHA-256 `2b9e1d771567788ad4ee9213ab09484b7d0dce81c884782d949d5dde2814f1a8`.
- Command: `threshold-panel-study --policy policies/threshold-v1.json --output-dir ../docs/data/task2-panel-study`.
- Commit: `b7df36b2c7ba78e3c0e857608fa023f9462b1482`.
- git HEAD and the start marker recorded no earlier run of this study.
- Source of the public grades: LiveCodeBench, <https://livecodebench.github.io/performances_generation.json>, SHA-256 `17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1`. The source states no license, so the raw file is not in the repository. The outputs hold derived values for each model only.

Input hashes (SHA-256):

- `threshold-v1.json`: `2b9e1d771567788ad4ee9213ab09484b7d0dce81c884782d949d5dde2814f1a8`
- `replay manifest.json`: `ed3c5bacb4b6b62695ee3b5e87d0b3f44e1b4deb4204f4f76da831b7fdc808d0`
- `lcb-reference-panel.json`: `e328aac064023db8ba3fa2b5ab423ff057c966d0733c4f52b63201dc35bdf83c`
- `lcb-public-mapping.json`: `fe59fae621c4a514e5f72838cb140a091f02926752436ba2b2d5bb62aa2a0e75`
- `Part 1/predictions/live_code_bench_v5__gpt-oss-120b.jsonl`: `251ba80edb5df9500476f64c7440ecc6bff71060fbb107da23e1f5b8ac42f692`
- `Part 1/predictions/live_code_bench_v5__kimi-k2.5.jsonl`: `5d63df790fd81d34033b3d27735f3025438c0a0ebb3374bbcb70b302ae19726f`
- `Part 1/predictions/live_code_bench_v5__minimax-m2.5.jsonl`: `cdbd7b6fbd0e5f6d3d7fe028fef68cb2c6177bdf7c4245de9aa20b369099054f`
- `performances_generation.json`: `17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1`

The output hashes are in `manifest.json`.
