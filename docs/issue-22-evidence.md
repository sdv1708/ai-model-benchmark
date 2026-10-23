# Issue #22 acceptance and research evidence

## Scope and provenance

Issue: [Design the full-dataset MMMU image-encoder probe](https://github.com/sdv1708/ai-model-benchmark/issues/22).
Parent spec: [Task 2, Part B](../Task2_Model_Quality.md). The issue requests a
proposal; the parent explicitly permits Part B as a written design. The user's
explicit implementation request authorized assistant authorship of this
learner-labelled work. No experiment result is attributed to the learner.

Fetched `origin/main` and fast-forwarded local `main` from `12070a1` to
`96922eb2e00cf26622bd28fe5e5fcfa4d88d6c5f`, then created
`feature/issue-22-mmmu-encoder-probe` from that exact base. The checkout was clean.

Deliverables:

- [Technical proposal](../task2/MMMU_PROBE_DESIGN.md).
- [Beginner/interview guide](../task2/ISSUE_22_GUIDE.md).
- [Machine-readable inventory audit](data/mmmu-inventory-audit.json).
- README entry points and the [two-axis review](issue-22-review.md).

## Acceptance mapping

| Requirement                                                                        | Evidence                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Distinguish full data from 660 reference rows                                      | Proposal §2: 11,550 total; 150/900/10,500 splits; 30 versus 22 subjects, eight missing subjects. Audit records source revision and local file hashes.                                                                            |
| Cover subjects, image types, difficulty and representation                         | §§3–4: answer-blind full inventory; subject/difficulty probability strata; separate constrained coverage panel; native labels, subfields, families, open questions and multi-image quotas; feasibility failure/expansion policy. |
| Resolution, text, charts, diagrams, spatial detail, clutter, color, domain imagery | §5: all eight axes, proposed severity settings, target features, semantic validity checks and destructive-control exclusions.                                                                                                    |
| Separate perception and reasoning with controls                                    | §6: original/no-image/equivalent text/two stresses/direct visual facts, independent oracle creation, interpretation matrix and identification limits.                                                                            |
| OpenAI-compatible interaction and measurement                                      | §§7–9: request structure, capability negotiation, image ordering, versioned evidence, parsing, failures, paired metrics, uncertainty, costs, release gates and future native EvalScope integration.                              |

## Research conducted on 2026-10-23

Only primary sources and actual framework source were used:

1. Official [HF dataset metadata](https://huggingface.co/api/datasets/MMMU/MMMU/revision/876ce5cb130f7f7e290ce4d9984357737d4db5cf)
   and [card](https://huggingface.co/datasets/MMMU/MMMU/blob/876ce5cb130f7f7e290ce4d9984357737d4db5cf/README.md).
   The metadata declares 30 configurations; summing split counts gives 11,550.
   The audit stores per-subject counts and field types. This is a metadata audit,
   not an independent Parquet/image census.
2. Official [MMMU README](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/README.md)
   and [released test mapping](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/mmmu/answer_dict_test.json).
   Verified 10,500 source-ID entries and recorded the answer-file SHA-256.
3. [Official scoring code](https://github.com/MMMU-Benchmark/MMMU/blob/268471d0d488258990025331c7528359c324aa25/mmmu/utils/eval_utils.py):
   inspected answer normalization and random MC parse fallback. The proposed
   diagnostic parser deliberately fails malformed answers rather than guessing;
   the proposal explicitly disclaims leaderboard-equivalent scores.
4. [MMStar paper](https://arxiv.org/abs/2403.20330v2) and
   [MMMU-Pro paper](https://arxiv.org/abs/2409.02813v3): motivation for image-necessity
   controls and caution about text shortcuts. Neither dataset replaces original
   MMMU in this plan; no claimed effect size is borrowed for this probe.
5. Official [vision documentation](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)
   and [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create):
   request content, provider-specific capabilities and recorded usage/settings.
6. Pinned [EvalScope MMMU adapter](https://github.com/modelscope/evalscope/blob/66f0945d145ce6c30de40253cd78144003c6f1fe/evalscope/benchmarks/mmmu/mmmu_adapter.py),
   read using `git show` from the existing fork checkout. Verified its default
   validation split, mirror/HF configuration, image ordering and stale note about
   withheld test answers. No fork files were modified.
7. Statistics Canada's [stratified sampling treatment](https://www150.statcan.gc.ca/n1/pub/12-001-x/2019002/article/00006/02-eng.htm)
   and NIST's [Bonferroni method](https://itl.nist.gov/div898/handbook/prc/section4/prc473.htm)
   support the design-variance expression and simultaneous-bound approach.

Local audit streamed every supplied prediction/review file, joined equal indices
within subjects and checked metadata source IDs: 660 unique validation IDs,
zero prediction/review source-ID disagreements, 613 MC and 47 open rows, 209 Easy,
304 Medium and 147 Hard labels. The 27 observed image labels overlap and describe
only those references. No model score was used to choose a probe or claimed as
encoder-quality evidence.

## Reproducing the inventory checks

From the repo root, the following standard-library Python snippet verifies the
official metadata snapshot and local prediction hashes without downloading images
or contacting a model. It needs internet access to Hugging Face. Metadata JSON
order is irrelevant because counts are compared as objects.

```python
import hashlib
import json
import urllib.request
from pathlib import Path

audit = json.loads(Path("docs/data/mmmu-inventory-audit.json").read_text())
source = audit["official_source"]
with urllib.request.urlopen(source["metadata_url"], timeout=60) as response:
    metadata = json.load(response)
assert metadata["sha"] == source["revision"]
counts = {
    item["config_name"]: {
        split["name"]: split["num_examples"] for split in item["splits"]
    }
    for item in metadata["cardData"]["dataset_info"]
}
assert counts == source["subject_split_counts"]
for item in audit["supplied_reference"]["prediction_files"]:
    raw = Path(item["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert len(raw.splitlines()) == item["rows"]
```

For the released labels, fetch `official_test_answers.url` in the audit, hash its
raw response bytes and compare the recorded checksum. Decode JSON, require the
recorded entry count, and verify the per-entry `question_type`/`ground_truth`
schema. A future full run must additionally join every selected question ID and
verify the target and image content against the downloaded dataset.

## Validation and limitations

This is a documentation/data-evidence change with no new runtime seam. No TDD
tests were added to assert prose. Existing Task 2 type checks, lint and the full
Task 2 test suite are the regression checks; Markdown/JSON formatting, internal
links, audit arithmetic and patch whitespace are checked separately.

Verified results:

- `.venv/Scripts/python.exe -m mypy` from `task2/`: no issues in 34 source
  files. The type check also passed during the initial research stage.
- `.venv/Scripts/python.exe -m ruff check .`: passed.
- `.venv/Scripts/python.exe -m ruff format --check .`: 47 files already formatted.
- `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp output/pytest-issue22-20261023`:
  **129 passed in 33.54 seconds**, Python 3.12.8. The initial default-temp run had
  62 passes and 67 fixture-setup errors because the sandbox could not create its
  Windows temp directories. Moving the test temp root into the workspace resolved
  the environmental failure without application changes.
- Pinned remote metadata matched every saved subject/split count. The answer
  checksum matched and all 10,500 entries had supported question types and
  nonempty ground truths. All 22 local prediction hashes and row counts matched.
- Audit totals, missing-subject count, local Markdown links, Prettier formatting
  and `git diff --check` were checked. Independent parallel review found
  **Standards: 0 findings; Spec: 0 findings**; see the [reports](issue-22-review.md).

Commands beginning `.venv/` above run from `task2/`; Prettier runs from the repo
root with `frontend/node_modules/.bin/prettier.cmd`. Task 1 and the separate fork
were not modified, so their runtime suites were not rerun.

No full-data image census, feasible selected manifest, equivalent-text oracle,
transformed image, live API request, confidence interval, accuracy result or
cost-saving measurement exists for this probe. R=360/S=120 and example release
gates are proposed values. The design states what must be measured before they
can justify a customer decision. No runnable MMMU probe command was added.
