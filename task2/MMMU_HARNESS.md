# Image-pair harness reference

The harness builds controlled image variants and analyzes saved responses.
It never sends requests to a model endpoint.
Its demonstration uses synthetic images, scripted responses, and simulated semantic reviews.

## Demonstration

From `task2/`, run:

```powershell
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
```

Use a new destination directory.
The command creates inputs, an image bundle, a request plan, synthetic observations, a report, and a preview image.
`report-SYNTHETIC.json` identifies the evidence as synthetic.
The profile uses an invalid endpoint and a placeholder model.

## Input inventory

The input is UTF-8 JSON.
Image paths resolve relative to the inventory file and must remain inside that directory.
The following example defines the schema; it is not a real MMMU question:

```json
{
  "dataset": "MMMU/MMMU",
  "revision": "PINNED_DATASET_REVISION",
  "samples": [
    {
      "source_id": "SOURCE_QUESTION_ID",
      "subject": "SOURCE_SUBJECT",
      "split": "validation",
      "question": "Question containing <image 1>",
      "options": ["Option A", "Option B"],
      "accepted_answers": ["B"],
      "images": { "image_1": "images/source.png" },
      "target_slot": "image_1",
      "text_regions": [[0.1, 0.2, 0.9, 0.4]]
    }
  ]
}
```

Source IDs must be unique.
Question and option text can reference `<image 1>` through `<image 7>`.
Every reference must resolve, and every supplied image must have a reference.
Repeated references retain their positions.
Each sample has one target image slot.

Multiple-choice questions require 2 through 26 options and valid uppercase answer letters.
Open questions use an empty `options` array and explicit accepted answer strings.
The harness trusts supplied labels; it cannot authenticate them.

Text regions use normalized left, top, right, and bottom coordinates after image orientation.
The builder converts those values to integer pixel bounds.
Empty regions fail validation.
Missing text regions make text blur inapplicable.
The harness does not locate text automatically.

## Image normalization and variants

Each source image receives EXIF orientation, white alpha compositing, RGB conversion, and metadata removal.
The normalized PNG defines the original condition.
Animated and multipage sources are rejected.
Color profiles are not color-managed.

Every variant starts from the normalized original.
Only the target slot changes.
Question text, options, other image slots, and output canvas size remain fixed.

| Transform   | Mild setting                               | Strong setting                             |
| ----------- | ------------------------------------------ | ------------------------------------------ |
| Downsample  | Reduce dimensions to 75%, then restore.    | Reduce dimensions to 50%, then restore.    |
| Global blur | Gaussian radius 0.6 pixels.                | Gaussian radius 1.2 pixels.                |
| JPEG        | Quality 75.                                | Quality 40.                                |
| Occlusion   | Gray strip over the left 5% of width.      | Gray strip over the left 15% of width.     |
| Contrast    | Factor 0.75.                               | Factor 0.5.                                |
| Color       | Saturation factor 0.75.                    | Saturation factor 0.5.                     |
| Text blur   | Radius 0.6 pixels inside supplied regions. | Radius 1.2 pixels inside supplied regions. |

Downsampling uses LANCZOS in both directions.
JPEG uses 4:4:4 chroma and returns to PNG after decoding.
A treatment with no pixel change is marked inapplicable.
These settings are pilot choices, not validated semantic equivalence.
Occlusion can intentionally remove necessary evidence.

The manifest records source hashes, normalized hashes, output hashes, parameters, runtime versions, and implementation identity.
Pair identities bind those details to each sample and treatment.
The same supported environment and inputs produce repeatable bytes.
Different Python or codec environments can produce different bytes.
Pillow is pinned in the package lockfile.

## Semantic review

The builder writes `qa-template.json`.
A review record contains `pair_id`, `status`, `reviewers`, and `notes`.

| Status                | Meaning                                                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------- |
| `pending`             | No confirmed review exists. Missing review records also remain pending.                        |
| `labels_preserved`    | The review declares preserved task evidence, with two distinct reviewer names and a rationale. |
| `destructive_control` | The treatment intentionally removes necessary evidence.                                        |
| `invalid`             | The export or semantic interpretation is unusable.                                             |

Only `labels_preserved` pairs enter robustness summaries.
Review states remain visible in individual pair results.
The software cannot prove that named reviewers inspected an image.
Synthetic reviews do not establish human validation.

## Build and plan commands

From `task2/`, build a bundle:

```powershell
uv run mmmu-pairs build --input my-inputs/input.json --output-dir output/my-bundle
```

Create a provider profile with this schema:

```json
{
  "endpoint": "https://example.invalid/v1/chat/completions",
  "model": "PINNED_MODEL_ID",
  "detail": "high",
  "generation": { "temperature": 0, "max_completion_tokens": 1024 }
}
```

Export the request plan:

```powershell
uv run mmmu-pairs plan --bundle output/my-bundle --profile profile.json --output output/my-plan.json
```

Planning validates all image checksums.
It exports ordered text and base64 PNG parts in fresh conversations.
Accepted answers, explanations, and review states do not enter the request body.
Plans use `stream: false` and two repeats by default.
A deterministic schedule interleaves planned calls.

Profiles require exactly `endpoint`, `model`, `detail`, and `generation`.
Generation settings require exactly one of `max_tokens` and `max_completion_tokens`.
Optional settings include `temperature`, `top_p`, and provider `seed`.
A provider runner must validate endpoint support separately.
Authentication does not belong in profiles or plans.
No provider runner is included here.

## Saved response contract

The response file binds observations to the exact plan bytes:

```json
{
  "evidence_kind": "saved_endpoint_records",
  "plan_sha256": "SHA256_OF_PLAN_BYTES",
  "attempts": [
    {
      "attempt_id": "ATTEMPT_ID_FROM_PLAN",
      "request_sha256": "REQUEST_HASH_FROM_PLAN",
      "status": "completed",
      "finish_reason": "stop",
      "raw_answer": "ANSWER: B",
      "response_id": "PROVIDER_RESPONSE_ID",
      "resolved_model": "PROVIDER_MODEL_ID"
    }
  ]
}
```

Synthetic fixtures use `evidence_kind: synthetic`.
Completed endpoint observations require response and model identity.
Other statuses include `http_error`, `timeout`, `truncated`, and `rejected`.
They represent unknown outcomes.
Omitted attempts remain missing.
Unknown, duplicate, or mismatched identities fail validation.

## Report command and scoring

From `task2/`, run:

```powershell
uv run mmmu-pairs report --bundle output/my-bundle --plan output/my-plan.json --responses saved-responses.json --qa reviewed-qa.json --output output/my-report.json
```

The reporter verifies images and reconstructs the planned requests.
The strict answer parser requires one `ANSWER: <value>` line.
Multiple-choice answers must use valid uppercase letters without additional explanation.
Open answers preserve case and collapse whitespace before exact accepted-string matching.
Alternative numeric or unit forms need explicit accepted strings.

A completed malformed answer scores zero.
A missing, truncated, or transport-failed attempt stays unknown.
Both paired accuracies use the same complete attempt denominator:

```text
original_accuracy = correct originals / complete paired attempts
transformed_accuracy = correct variants / complete paired attempts
accuracy_drop_pp = 100 * (original_accuracy - transformed_accuracy)
answer_consistency = equal parsed answers / pairs with both answers parsed
```

Answer consistency can remain high when both answers are wrong.
Shared originals and repeat attempts do not provide independent questions.
The report therefore avoids one pooled accuracy across all transformations.

Missing-attempt bounds assign extreme outcomes to unresolved attempts.
They describe completion uncertainty, not confidence intervals or population uncertainty.
Reports retain false values for full-model, population, and encoder-causality claims.
The [research design](MMMU_PROBE_DESIGN.md) defines the additional evidence those claims would need.
