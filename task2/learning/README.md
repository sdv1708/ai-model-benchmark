# Benchmark learning walkthrough

Open [benchmark-walkthrough.html](benchmark-walkthrough.html) in a browser. A
double-click is enough: there is no server, installation, API key, model call, or
judge call. The editable source is
[benchmark-walkthrough.fragment.html](benchmark-walkthrough.fragment.html); the
standalone page contains that source and the presentation styles it needs.

This is a simplified teaching example with **eight synthetic questions**, two
input-length groups, and two invented models. Its numbers are not measured
AA-LCR results. It illustrates sampling and weighting, but does not implement the
full candidate methods, confidence intervals, or model-holdout protocols.

## Work through the example

1. Inspect the full recorded grades and calculate the two full scores yourself.
2. Select a subset while the grades are hidden. Selection uses question IDs and
   length groups, never the target grades.
3. Compare the raw and population-weighted estimates. The short and long groups
   have different sizes, so equal numbers of sampled questions can need unequal
   weights. Predict the full score before proceeding.
4. Reveal the full grades and check the estimate's error and model ordering.
   Change the subset, then retain all eight questions and observe what happens.
5. Change hypothetical judge grades while keeping the answers fixed. Observe
   the difference between selecting different questions and receiving different
   grades. These changes are sensitivity scenarios, not measured judge noise.

## Study the tickets in this order

| Ticket                                                                 | Question it answers                                                    | Reading                                                   |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------- |
| [#14](https://github.com/sdv1708/ai-model-quality-challenge/issues/14) | Where do trustworthy full scores come from?                            | [Reference guide](../INTERVIEW_GUIDE.md)                  |
| [#15](https://github.com/sdv1708/ai-model-quality-challenge/issues/15) | How do selection, weights and held-out evaluation work?                | [Coding-pruning guide](../ISSUE_15_GUIDE.md)              |
| [#16](https://github.com/sdv1708/ai-model-quality-challenge/issues/16) | How do long-context metadata and judge uncertainty change the problem? | [AA-LCR guide](../ISSUE_16_GUIDE.md)                      |
| [#17](https://github.com/sdv1708/ai-model-quality-challenge/issues/17) | What evidence justifies a particular subset size?                      | Define acceptable errors and examine the fidelity curves. |

Then study [#18](https://github.com/sdv1708/ai-model-quality-challenge/issues/18)
for the evalscope baseline,
[#19](https://github.com/sdv1708/ai-model-quality-challenge/issues/19) and
[#20](https://github.com/sdv1708/ai-model-quality-challenge/issues/20) for framework
integration, and [#21](https://github.com/sdv1708/ai-model-quality-challenge/issues/21)
for comparing full and pruned runs. The multimodal branch, #22 and #23, is a later
topic rather than a prerequisite for understanding this example.

## Connect the example to real evidence

The [AA-LCR guide](../ISSUE_16_GUIDE.md) documents the commands that generate the
actual study's scores, selections, weights, uncertainty intervals, coverage and
judge-sensitivity reports. The teaching page does not load those reports.

Offline replay checks a subset against already stored full-run grades. It does
not establish reliability on a new model or measure repeated judge behavior.
The available AA-LCR evidence contains one judgment per answer. No production
retention ratio is certified by this walkthrough or by the current study.
