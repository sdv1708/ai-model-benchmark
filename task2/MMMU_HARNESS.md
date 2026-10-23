# Paired image prototype: operating contract (issue #23)

Status: **implemented offline prototype; no new endpoint evidence**. This turns
part of the [issue #22 design](MMMU_PROBE_DESIGN.md) into reproducible artifacts
and measurements. It does not select a benchmark subset or register an EvalScope
pruner. The final native probe still belongs in EvalScope. This prototype is
not a replacement benchmark runner.

The supplied 660 prediction/review records do not contain original question
images. We do not reconstruct them from model answers. The demo uses **three
synthetic visual families**, which test machinery only. Real MMMU work requires
exporting original questions/images and audited labels into the contract below.
No full-dataset download, census, human study or model inference was performed.

## Run the synthetic demonstration

From `task2/`, with Python 3.12 and uv:

```powershell
uv sync --locked
uv run python tools/demo_mmmu_pairs.py --output-dir output/mmmu-demo
```

Choose a **fresh destination** each time. Output includes inputs, a bundle,
`profile.json`, `plan.json`, `responses-SYNTHETIC.json`, `qa-SYNTHETIC.json`,
`report-SYNTHETIC.json` and `preview-SYNTHETIC.png`. No endpoint is called.
Responses and reviewer names are scripted fixtures, not model or human evidence.
The bundle's genuine `qa-template.json` stays pending.

Expected: 3 questions, 38 pairs, 82 planned calls, 79 scripted responses. Color
changes are skipped on the two grayscale images. Six occlusions are scripted
destructive controls, excluded from robustness summaries. Three strong-blur
responses are deliberately missing. These counts do not measure a model.

Individual commands:

```powershell
uv run mmmu-pairs demo --output-dir output/my-inputs
uv run mmmu-pairs build --input output/my-inputs/input.json --output-dir output/my-bundle
uv run mmmu-pairs plan --bundle output/my-bundle --profile output/mmmu-demo/profile.json --output output/my-plan.json
```

The demo profile uses an invalid endpoint and a scripted placeholder model.
For future experiments supply a tested provider profile; `plan` still only
exports JSON. Inference, authentication, retries and billing are out of scope.

## Inventory schema

Provide UTF-8 JSON. Image paths resolve relative to the inventory file and must
stay within its directory. Use native `<image 1>` ... `<image 7>` references in
questions/options. Every image must be referenced and every reference must
resolve. Repeated references and images inside options retain their positions.

```json
{
  "dataset": "MMMU/MMMU",
  "revision": "876ce5cb130f7f7e290ce4d9984357737d4db5cf",
  "samples": [{
    "source_id": "SOURCE_ID_FROM_PINNED_DATASET",
    "subject": "SOURCE_SUBJECT",
    "split": "validation",
    "question": "Original question containing <image 1>",
    "options": ["Original option A", "Original option B"],
    "accepted_answers": ["B"],
    "images": {"image_1": "images/source.png"},
    "target_slot": "image_1",
    "text_regions": [[0.1, 0.2, 0.9, 0.4]]
  }]
}
```

This is a schema illustration, **not a real MMMU question/label**. Each source ID
must be unique. For open questions use `options: []` and explicit accepted strings.
For MC use 2..26 options and valid uppercase answer letters. There is one target
slot per sample. Text rectangles are normalized left/top/right/bottom coordinates
in the **oriented** target image, converted by flooring to integer pixels. Empty
pixel rectangles are rejected. Missing regions make text blur inapplicable.
No OCR or automatic mask discovery is implemented.

Use development/validation for calibration. Confirmatory test work requires the
full inventory, released-answer join, sampling/coverage checks and provenance in
issue #22. The harness trusts supplied labels and cannot authenticate them. The
three synthetic families do not represent all 30 MMMU subjects or its population.
Choose actual visual families without candidate answers/scores. Do not confuse
manually chosen prototype examples with a justified benchmark pruner.

## Pixel operations and identity

Common normalization is EXIF orientation, alpha over white, RGB conversion and
metadata-free PNG. It defines the original condition; preserve source bytes
separately. Animated/multipage sources are rejected. Color profiles are not
color-managed: audit color-critical images. Every treatment starts from the
same normalized original, never another treatment. Only the target slot changes;
all repeated occurrences of it change together. Other images and text stay fixed.

| Operation | Mild | Strong | Required interpretation |
| --- | --- | --- | --- |
| Downsample | 75% dimensions, restore | 50%, restore | LANCZOS both ways; record intermediate size |
| Global blur | Gaussian radius 0.6 px | 1.2 px | Check necessary features remain readable |
| JPEG | Quality 75 | Quality 40 | 4:4:4 chroma, no optimization, decode back to PNG |
| Occlusion | Gray left strip, 5% width | 15% width | Exact rectangle; may destroy evidence |
| Contrast | Factor 0.75 | Factor 0.5 | Check necessary text/boundaries |
| Color | Saturation 0.75 | Saturation 0.5 | Preserve essential color distinctions |
| Text blur | Radius 0.6 px in saved regions | 1.2 px | Outside-region pixels unchanged |

All output canvases and containers stay fixed. Re-decoding JPEG to PNG preserves
compression artifacts while reducing format-dependent API confounds. No crop is
implemented: deterministic occlusion satisfies the crop-or-occlusion criterion.
These are pilot settings, not proven perceptual equivalence. No pixel change is
recorded as inapplicable. The demo's broad masks illustrate plumbing, not expert
text-region annotations. Text blur is a legibility treatment, not an OCR score.

The manifest records source-byte and canonical-image SHA-256, sizes, exact
parameters/masks, dataset revision, Python/Pillow/JPEG/zlib versions and the
transformation-module hash. Sample identity binds question/options, labels,
slot mapping, provenance, implementation and runtime. Pair identity additionally
binds transformation and output bytes. Images have content-addressed paths.
Same inputs/environment produce byte-identical bundles. Changed content or
protocol identity changes IDs. Hashes prove consistency, not truth/authenticity.

Pillow **13.0.0** is pinned with artifact hashes in `uv.lock`. Byte identity
across different Python/OS/codec builds is not promised; compare runtime and
hashes. Builds validate and stage before publishing; existing destinations are
refused. Planning/reporting verify every image checksum before use.

## Semantic QA

Copy `qa-template.json` and inspect full-size original/transformed images without
candidate outputs. Check signs, thin lines, labels, colors and option images;
use specialists for domain content. Each record has `pair_id`, `status`,
`reviewers` and `notes`. Allowed states:

- `pending`: no confirmed semantic review; missing records also count as pending.
- `labels_preserved`: at least two distinct reviewer strings and a nonempty
  rationale. Only these pairs enter robustness summaries.
- `destructive_control`: intentional evidence destruction, excluded from
  invariance claims.
- `invalid`: unusable export/treatment or unresolved semantics.

All states remain visible in per-pair output; unknown/duplicate QA IDs fail.
Software cannot prove that named humans inspected images. The synthetic demo
explicitly simulates this gate and is not human validation. Do not replace pairs
after seeing model failures or reuse synthetic QA as genuine review.

## Future endpoint profile and evidence contract

Profiles contain exactly `endpoint`, `model`, `detail`, `generation`:

```json
{
  "endpoint": "https://YOUR_PROVIDER/v1/chat/completions",
  "model": "PINNED_PROVIDER_MODEL",
  "detail": "high",
  "generation": {"temperature": 0, "max_completion_tokens": 1024}
}
```

Preflight provider support separately. Choose exactly one of `max_tokens` and
`max_completion_tokens`; no silent fallback. Optional generation fields are
`temperature`, `top_p`, and supported provider `seed`. Authentication stays out
of profiles/plans, in environment secrets consumed by a future runner.

Plans contain fresh user-message conversations, ordered text/base64 PNG image
parts, explicit image detail and `stream: false`. Accepted answers, explanations
and QA are never inserted into messages. Each original and variant gets two
attempts by default. The original is reused for all its transform comparisons
at the matching repeat index. The saved hash-based schedule interleaves calls
using default schedule seed 23. This is distinct from provider generation seed;
neither that seed nor temperature zero guarantees model determinism.

Calls carry `attempt_id`, `condition_id`, `sample_id`, zero-based `repeat`,
`request_sha256`, `body`. Save observations in this form:

```json
{
  "evidence_kind": "saved_endpoint_records",
  "plan_sha256": "SHA256_OF_EXACT_PLAN_FILE_BYTES",
  "attempts": [{
    "attempt_id": "FROM_PLAN",
    "request_sha256": "FROM_PLAN",
    "status": "completed",
    "finish_reason": "stop",
    "raw_answer": "ANSWER: B",
    "response_id": "PROVIDER_RESPONSE_ID",
    "resolved_model": "PROVIDER_REPORTED_MODEL"
  }]
}
```

Use `evidence_kind: synthetic` for fixtures. Completed endpoint observations
require response/model identity. Noncompleted states are `http_error`, `timeout`,
`truncated`, `rejected`; all are unknown outcomes. Omitted attempts are missing.
Duplicate, unknown, mismatched-request/plan IDs fail. The reporter regenerates
the plan to catch changes in prompts/images/settings. It flags multiple returned
model IDs but cannot prove serving behavior is unchanged or authenticate records.

A future runner must also retain times/order, usage, finish reasons, backend
fingerprints, raw responses/errors and retry history. These extra fields may be
saved with attempts; this prototype does not analyze them. Keep concurrency and
generation settings fixed. Never retry based on correctness; retries belong to
the same logical attempt and are not independent samples.

```powershell
uv run mmmu-pairs report --bundle output/my-bundle --plan output/my-plan.json --responses saved-responses.json --qa reviewed-qa.json --output output/my-report.json
```

## Scoring, denominators and limits

The strict parser requires one `ANSWER: <value>` line. MC uses exact uppercase
valid letters, no extra punctuation/explanation. Open answers case-fold and
collapse whitespace, then match explicit accepted strings exactly. Numeric/unit
equivalents need explicit accepted forms. No random fallback, semantic judge or
leaderboard-equivalence claim. Malformed completed answers score zero; missing
and transport/truncated attempts stay unknown.

For each QA-approved transform/severity, both accuracies use the same complete
paired attempts, including completed format failures as zero:

```text
original_accuracy    = correct originals / complete paired attempts
transformed_accuracy = correct transforms / complete paired attempts
accuracy_drop_pp     = 100 * (original_accuracy - transformed_accuracy)
answer_consistency  = equal parsed answers / pairs with both answers parsed
```

Consistency has its own denominator and can be high when both answers are wrong.
Negative drop means improvement on these observations. Categories are exclusive:
`missing_or_transport`, then `format_failure`, then semantic `stable_correct`,
`regression`, `improvement`, `stable_wrong`, `changed_wrong`. Component scores
remain visible even when the exclusive category is format failure.

Report counts include unique questions, planned/complete pairs, QA and
inapplicability. There is no across-transform pooled accuracy: shared originals,
repeats and different eligibility sets would make it misleading. All groups
are unweighted prototype diagnostics, not full-MMMU or Panel R estimates.

Bounds keep every QA-approved planned attempt in the denominator: replace each
missing original by 0/1 and each missing transform by 1/0 for the smallest/largest
possible signed difference; average and multiply by 100. These are completion
bounds, **not confidence intervals**. A complete report can have zero-width
completion bounds and still enormous population uncertainty. Repeats/duplicate
images remain clustered by question. No sampling interval, power calculation,
sampling weights or go/no-go release threshold is implemented here.

Every report sets `full_live_model_conclusion`, `population_estimate` and
`encoder_causal_claim` to false, even with saved endpoint records. Endpoint
evidence is not independently verified. Stronger claims still need the issue
#22 controls, selection/coverage checks, two-system contrasts and uncertainty.

## Research checked 2026-10-23

- [Pillow resize](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize)
  and [Gaussian blur](https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html#PIL.ImageFilter.GaussianBlur)
  define the filtering operations; settings here are prototype choices.
- [Pillow enhancement](https://pillow.readthedocs.io/en/stable/reference/ImageEnhance.html)
  and [JPEG options](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg)
  informed fixed contrast/saturation/chroma/quality parameters.
- [EXIF transpose](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose)
  informed common image orientation.
- [Official OpenAI vision guide](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
  supports base64 image content; image detail remains model-dependent and needs
  provider preflight.
- [MMStar](https://arxiv.org/abs/2403.20330) motivates visual-dependence controls;
  those controls are not executed here.
- [Pinned MMMU and framework research](MMMU_PROBE_DESIGN.md) remains the full
  experimental design authority. Research and metadata are not endpoint results.
