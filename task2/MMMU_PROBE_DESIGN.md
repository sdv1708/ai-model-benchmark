# MMMU visual-path study proposal

This document defines a proposed study of task-relevant visual information.
The full study has not run.
The implemented [image-pair harness](MMMU_HARNESS.md) supports a limited offline prototype.
Synthetic demonstration results do not establish model quality or benchmark compression.

## Research question

The study asks whether a model preserves necessary image information while answering multimodal questions.
A high answer score alone cannot identify visual understanding.
A model can answer some questions through text cues or prior knowledge.
An incorrect answer can also result from reasoning or formatting failures.

A model API exposes images as inputs and answers as outputs.
It does not expose the encoder, projector, attention, or internal resizing behavior.
An observed regression can implicate the visual input path, but cannot isolate an encoder defect.
An encoder-specific causal claim requires an intervention that changes only that encoder.

## Population and source identity

The researched dataset revision is `876ce5cb130f7f7e290ce4d9984357737d4db5cf` for `MMMU/MMMU`.
The [dataset card at that revision](https://huggingface.co/datasets/MMMU/MMMU/blob/876ce5cb130f7f7e290ce4d9984357737d4db5cf/README.md) declares 30 subjects.
Its split counts give the following inventory:

| Split                         | Questions | Proposed role                                         |
| ----------------------------- | --------: | ----------------------------------------------------- |
| Development                   |       150 | Prompt and annotation calibration.                    |
| Validation                    |       900 | Design pilot and transformation debugging.            |
| Test                          |    10,500 | Frozen confirmatory sampling frame.                   |
| Total                         |    11,550 | Full declared inventory.                              |
| Supplied historical reference |       660 | Validation records from one model across 22 subjects. |

These are recorded metadata counts, not a claim that this project decoded every source image.
The [inventory audit](../docs/data/mmmu-inventory-audit.json) records the supplied subset and source identity.
A test-split estimate would target 10,500 questions.
It would not automatically describe all 11,550 questions.

The supplied reference misses eight subjects.
It cannot define full-dataset coverage by itself.
The official repository's [released test answers](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/mmmu/answer_dict_test.json) require a separate source-ID join.
A future study must pin those bytes and verify complete question-type and label coverage.
Released answers must remain outside model requests.

## Inventory before selection

The proposed inventory would retain subject, subfield, split, source ID, difficulty, question type, and ordered image references.
It would preserve option images and repeated references as well as question images.
Each image would receive byte hashes, dimensions, orientation, and annotation provenance.

Duplicate IDs and exact duplicate content require explicit checks.
Related images and near-duplicate questions require grouping before pilot/test separation.
Any exclusion changes the sampling frame and its population counts.
The study must report those changes before selecting confirmatory questions.

Difficulty tags describe source annotations.
They do not measure visual difficulty for a new model.
Selection annotations must remain independent of candidate answers and candidate scores.

## Two distinct panels

The proposed estimation panel would support a weighted population estimate.
Its sampling frame, inclusion probabilities, and weighting rules would be fixed before confirmatory observations.
It would preserve subject coverage and relevant visual characteristics.

A separate diagnostic panel would cover specific visual failure modes.
It could deliberately include rare or difficult visual patterns.
Its unweighted diagnostic results would not become population accuracy estimates.

Budgets and stopping rules require pilot validation.
The implemented prototype does not select either full-dataset panel.
It provides image treatments and saved-response diagnostics only.

## Controls and treatments

Each selected question would keep an original image condition.
Controlled variants would change one intended visual property at a time.
The question, answer options, other image slots, and request settings would remain fixed.

| Dimension               | Proposed evidence                                         |
| ----------------------- | --------------------------------------------------------- |
| Resolution              | Downsampled and restored images with recorded dimensions. |
| Fine detail             | Blur treatments and thin-feature checks.                  |
| Compression             | Fixed JPEG quality with constant output canvas.           |
| Missing visual evidence | Explicit destructive occlusion controls.                  |
| Contrast                | Controlled contrast changes.                              |
| Color                   | Controlled saturation changes and color-critical checks.  |
| Text legibility         | Blur within reviewed text regions.                        |
| Visual dependence       | Text-only or other carefully specified controls.          |

The prototype implements the first seven treatment families.
Visual-dependence controls and full study sampling remain proposed.
A semantic review must establish whether each treatment preserves necessary evidence.
Destructive controls must remain separate from invariance claims.

The research literature motivates this distinction.
[MMStar](https://arxiv.org/abs/2403.20330v2) examines nonvisual cues in multimodal evaluation.
[MMMU-Pro](https://arxiv.org/abs/2409.02813v3) addresses text-answerable questions.
This proposal still targets original MMMU.

## Semantic review

Reviewers would inspect original and transformed images without candidate outputs.
They would check symbols, signs, labels, colors, fine boundaries, and option images.
Specialist content would require suitable domain review.
The record would retain reviewers, rationale, disagreements, and final status.

Pairs with unresolved meaning would remain pending or invalid.
Treatments that remove necessary evidence would become destructive controls.
The study would freeze eligible pairs before observing candidate correctness.
Replacing failures afterward would bias the result.

## Endpoint protocol

A future runner would pin endpoint, provider model ID, image detail, generation settings, and prompt format.
It would preserve ordered image slots and send fresh conversations.
Accepted answers, explanations, and semantic review states would remain outside requests.
The runner would interleave conditions through a saved schedule.

Records would retain request hashes, response identities, finish reasons, times, usage, raw errors, and retry history.
Retries would remain part of the same logical attempt.
Temperature zero and a provider seed would not establish determinism.
Provider support would require a separate preflight check.
The repository currently contains a plan exporter, not that live runner.

## Measurements and uncertainty

Primary observations would include original accuracy, transformed accuracy, paired accuracy drop, and valid-answer consistency.
Each metric would show its denominator and eligibility rules.
Missing attempts would remain visible.
Completion bounds would separate unknown observations from observed failures.

A population estimate would require sampling weights and intervals appropriate to its sampling design.
Repeated attempts and related questions require clustered treatment.
Shared originals prevent treating every transformation as an independent question.
A diagnostic panel would report its own coverage and failure categories separately.

Transport failures, malformed completed answers, and semantic regressions require separate labels.
Stable answers can still be consistently wrong.
High answer consistency alone cannot establish task accuracy.

## Cost and decision policy

A future study would retain token usage, image processing settings, latency, retry counts, and provider billing inputs.
Subset size alone does not determine cost.
Image detail, response length, and repeated attempts can change total usage.

Release thresholds would require explicit customer requirements and pilot validation.
The confirmatory policy would be frozen before its observations.
The study would preserve an inconclusive outcome when evidence cannot resolve a threshold.
No cost saving, release decision, or encoder-specific conclusion is established by the current synthetic harness.
