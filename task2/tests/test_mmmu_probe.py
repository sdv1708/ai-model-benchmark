"""Public CLI and reporting contracts for the offline visual-path prototype."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw


def inventory(tmp_path: Path) -> Path:
    image = Image.new("RGB", (160, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 60, 80), fill="red")
    draw.text((5, 5), "Value: 12", fill="black")
    image.save(tmp_path / "source.png")
    Image.new("RGB", (40, 40), "blue").save(tmp_path / "option.png")
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            {
                "dataset": "synthetic-test",
                "revision": "fixture-v1",
                "samples": [
                    {
                        "source_id": "fixture-chart",
                        "subject": "synthetic-chart",
                        "split": "synthetic",
                        "question": "Read <image 1>. Compare <image 1> with the option.",
                        "options": ["<image 2>", "Red"],
                        "accepted_answers": ["B"],
                        "images": {"image_1": "source.png", "image_2": "option.png"},
                        "target_slot": "image_1",
                        "text_regions": [[0, 0, 1, 0.25]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return source


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_builds_reproducible_pairs_without_changing_sources(tmp_path: Path) -> None:
    from benchmark_reference.mmmu_cli import main

    source = inventory(tmp_path)
    original = (tmp_path / "source.png").read_bytes()
    for name in ("first", "second"):
        main(["build", "--input", str(source), "--output-dir", str(tmp_path / name)])
    first, second = tmp_path / "first", tmp_path / "second"
    bundle = read_json(first / "manifest.json")
    assert bundle["evidence_kind"] == "offline_artifacts_only"
    assert len(bundle["pairs"]) == 14  # seven transformations, two severities
    assert {pair["transform"]["name"] for pair in bundle["pairs"]} == {
        "downsample",
        "blur",
        "jpeg",
        "occlusion",
        "contrast",
        "color",
        "text_blur",
    }
    assert len({pair["pair_id"] for pair in bundle["pairs"]}) == 14
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    assert (tmp_path / "source.png").read_bytes() == original
    sample = bundle["samples"][0]
    for pair in bundle["pairs"]:
        artifact = pair["transformed_image"]
        data = (first / artifact["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
        with Image.open(first / artifact["path"]) as image:
            assert image.size == (160, 100)
        assert artifact["sha256"] != sample["images"]["image_1"]["sha256"]
        assert pair["target_slot"] == "image_1"
    assert all(row["status"] == "pending" for row in read_json(first / "qa-template.json"))


def test_request_plan_preserves_image_order_and_never_sends_answers(tmp_path: Path) -> None:
    from benchmark_reference.mmmu_cli import main

    source = inventory(tmp_path)
    bundle = tmp_path / "bundle"
    main(["build", "--input", str(source), "--output-dir", str(bundle)])
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "endpoint": "https://example.org/v1/chat/completions",
                "model": "pinned-test-model",
                "detail": "high",
                "generation": {"temperature": 0, "max_completion_tokens": 128},
            }
        )
    )
    for name in ("plan1.json", "plan2.json"):
        main(
            [
                "plan",
                "--bundle",
                str(bundle),
                "--profile",
                str(profile),
                "--output",
                str(tmp_path / name),
            ]
        )
    assert (tmp_path / "plan1.json").read_bytes() == (tmp_path / "plan2.json").read_bytes()
    plan = read_json(tmp_path / "plan1.json")
    assert len(plan["calls"]) == 30  # original reused + 14 variants, twice each
    sample = read_json(bundle / "manifest.json")["samples"][0]
    originals = [call for call in plan["calls"] if call["condition_id"] == sample["sample_id"]]
    assert len(originals) == 2
    content = originals[0]["body"]["messages"][0]["content"]
    images = [part["image_url"] for part in content if part["type"] == "image_url"]
    assert len(images) == 3  # repeated question image and image in option A
    assert images[0] == images[1] and images[1] != images[2]
    assert all(image["detail"] == "high" for image in images)
    for call in plan["calls"]:
        assert call["body"]["model"] == "pinned-test-model"
        assert "accepted_answers" not in json.dumps(call["body"])
    assert plan["endpoint_executed"] is False


@pytest.mark.parametrize(
    "failure", ["duplicate", "missing_slot", "bad_region", "outside", "existing"]
)
def test_invalid_inventory_does_not_publish_or_replace_bundle(tmp_path: Path, failure: str) -> None:
    from benchmark_reference.mmmu_cli import main

    source = inventory(tmp_path)
    value = read_json(source)
    row = value["samples"][0]
    output = tmp_path / "bundle"
    if failure == "duplicate":
        value["samples"].append(row)
    elif failure == "missing_slot":
        row["images"].pop("image_2")
    elif failure == "bad_region":
        row["text_regions"] = [[0, 0, 2, 1]]
    elif failure == "outside":
        row["images"]["image_1"] = "../source.png"
    else:
        output.mkdir()
        (output / "keep.txt").write_text("prior bundle")
    source.write_text(json.dumps(value))
    with pytest.raises(SystemExit) as error:
        main(["build", "--input", str(source), "--output-dir", str(output)])
    assert error.value.code == 2
    if failure == "existing":
        assert (output / "keep.txt").read_text() == "prior bundle"
    else:
        assert not output.exists()


def measurement_files(tmp_path: Path, count: int = 1) -> tuple[Path, Path, Path, Path]:
    from benchmark_reference.mmmu_cli import main

    source = inventory(tmp_path)
    value = read_json(source)
    template = value["samples"][0]
    value["samples"] = [{**template, "source_id": f"chart-{i}"} for i in range(count)]
    source.write_text(json.dumps(value))
    bundle = tmp_path / "bundle"
    main(["build", "--input", str(source), "--output-dir", str(bundle)])
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "endpoint": "https://example.org/v1/chat/completions",
                "model": "pinned-test-model",
                "detail": "high",
                "generation": {"max_completion_tokens": 128},
            }
        )
    )
    plan_path = tmp_path / "plan.json"
    main(["plan", "--bundle", str(bundle), "--profile", str(profile), "--output", str(plan_path)])
    qa_path = tmp_path / "qa.json"
    qa = read_json(bundle / "qa-template.json")
    for row in qa:
        row.update(
            status="labels_preserved",
            reviewers=["reviewer-1", "reviewer-2"],
            notes="Synthetic test annotation, not human study evidence",
        )
    qa_path.write_text(json.dumps(qa))
    responses_path = tmp_path / "responses.json"
    plan = read_json(plan_path)
    responses_path.write_text(
        json.dumps(
            {
                "evidence_kind": "synthetic",
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                "attempts": [
                    {
                        "attempt_id": call["attempt_id"],
                        "request_sha256": call["request_sha256"],
                        "status": "completed",
                        "finish_reason": "stop",
                        "raw_answer": "ANSWER: B",
                    }
                    for call in plan["calls"]
                ],
            }
        )
    )
    return bundle, plan_path, qa_path, responses_path


def test_report_counts_paired_regressions_and_rescues_without_hiding_cancellation(
    tmp_path: Path,
) -> None:
    from benchmark_reference.mmmu_measurements import paired_report

    bundle, plan_path, qa_path, responses_path = measurement_files(tmp_path, count=4)
    manifest, plan, responses = (
        read_json(bundle / "manifest.json"),
        read_json(plan_path),
        read_json(responses_path),
    )
    answers = ["B", "B", "A", "A"]
    variants = ["B", "A", "B", "A"]
    sample_index = {s["sample_id"]: i for i, s in enumerate(manifest["samples"])}
    calls = {c["attempt_id"]: c for c in plan["calls"]}
    for attempt in responses["attempts"]:
        call = calls[attempt["attempt_id"]]
        i = sample_index[call["sample_id"]]
        answer = answers[i] if call["condition_id"] == call["sample_id"] else variants[i]
        attempt["raw_answer"] = f"ANSWER: {answer}"
    responses_path.write_text(json.dumps(responses))
    report = paired_report(bundle, plan_path, responses_path, qa_path)
    group = next(
        g for g in report["groups"] if g["transform"] == "downsample" and g["severity"] == "mild"
    )
    assert group["unique_questions"] == 4 and group["expected_paired_attempts"] == 8
    assert group["original_accuracy"] == group["transformed_accuracy"] == 0.5
    assert group["accuracy_drop_pp"] == 0
    assert group["answer_consistency"] == 0.5
    assert group["error_categories"] == {
        "stable_correct": 2,
        "regression": 2,
        "improvement": 2,
        "stable_wrong": 2,
    }
    assert group["accuracy_drop_bounds_pp"] == [0, 0]
    assert report["full_live_model_conclusion"] is False
    assert report["evidence_kind"] == "synthetic"


def test_report_scores_format_failure_and_bounds_missing_transformed_attempt(
    tmp_path: Path,
) -> None:
    from benchmark_reference.mmmu_measurements import paired_report

    bundle, plan_path, qa_path, responses_path = measurement_files(tmp_path)
    pair = next(
        p
        for p in read_json(bundle / "manifest.json")["pairs"]
        if p["transform"] == {"name": "blur", "severity": "mild", "radius_px": 0.6}
    )
    calls = [c for c in read_json(plan_path)["calls"] if c["condition_id"] == pair["pair_id"]]
    responses = read_json(responses_path)
    responses["attempts"] = [
        r for r in responses["attempts"] if r["attempt_id"] != calls[1]["attempt_id"]
    ]
    next(r for r in responses["attempts"] if r["attempt_id"] == calls[0]["attempt_id"])[
        "raw_answer"
    ] = "Maybe B?"
    responses_path.write_text(json.dumps(responses))
    report = paired_report(bundle, plan_path, responses_path, qa_path)
    group = next(
        g for g in report["groups"] if g["transform"] == "blur" and g["severity"] == "mild"
    )
    assert group["complete_paired_attempts"] == 1
    assert group["accuracy_drop_pp"] == 100  # explicitly complete-pair descriptive
    assert group["accuracy_drop_bounds_pp"] == [50, 100]
    assert group["answer_consistency"] is None
    assert group["error_categories"] == {"format_failure": 1, "missing_or_transport": 1}
    assert report["response_coverage"]["missing"] == 1


@pytest.mark.parametrize("status", ["pending", "invalid", "destructive_control"])
def test_unreviewed_or_destructive_pairs_do_not_enter_robustness_metrics(
    tmp_path: Path, status: str
) -> None:
    from benchmark_reference.mmmu_measurements import paired_report

    bundle, plan_path, qa_path, responses_path = measurement_files(tmp_path)
    qa = read_json(qa_path)
    for row in qa:
        row["status"] = status
    qa_path.write_text(json.dumps(qa))
    report = paired_report(bundle, plan_path, responses_path, qa_path)
    assert report["groups"] == []
    assert report["qa_counts"][status] == 14
    assert len(report["pairs"]) == 14


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_response",
        "unknown_response",
        "wrong_request",
        "wrong_plan",
        "tampered_plan",
        "tampered_image",
        "weak_qa",
    ],
)
def test_report_rejects_incompatible_or_ambiguous_evidence(tmp_path: Path, failure: str) -> None:
    from benchmark_reference.mmmu_measurements import paired_report

    bundle, plan_path, qa_path, responses_path = measurement_files(tmp_path)
    responses = read_json(responses_path)
    if failure == "duplicate_response":
        responses["attempts"].append(responses["attempts"][0])
    elif failure == "unknown_response":
        responses["attempts"][0]["attempt_id"] = "unknown"
    elif failure == "wrong_request":
        responses["attempts"][0]["request_sha256"] = "wrong"
    elif failure == "wrong_plan":
        responses["plan_sha256"] = "wrong"
    elif failure == "tampered_plan":
        plan = read_json(plan_path)
        plan["calls"][0]["body"]["model"] = "different-model"
        plan_path.write_text(json.dumps(plan))
        responses["plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    elif failure == "tampered_image":
        image = next((bundle / "images").glob("*.png"))
        image.write_bytes(b"bad")
    else:
        qa = read_json(qa_path)
        qa[0]["reviewers"] = ["one-reviewer"]
        qa_path.write_text(json.dumps(qa))
    responses_path.write_text(json.dumps(responses))
    with pytest.raises(ValueError):
        paired_report(bundle, plan_path, responses_path, qa_path)


def test_cli_records_inapplicable_changes_instead_of_pretending_to_degrade(tmp_path: Path) -> None:
    from benchmark_reference.mmmu_cli import main

    source = inventory(tmp_path)
    Image.new("RGB", (160, 100), "gray").save(tmp_path / "source.png")
    value = read_json(source)
    value["samples"][0].pop("text_regions")
    source.write_text(json.dumps(value))
    main(["build", "--input", str(source), "--output-dir", str(tmp_path / "bundle")])
    bundle = read_json(tmp_path / "bundle/manifest.json")
    assert {row["transform"] for row in bundle["inapplicable"]} >= {"text_blur", "color", "blur"}
    assert "color" not in {pair["transform"]["name"] for pair in bundle["pairs"]}


def test_open_answers_use_explicit_normalization_and_reject_multiline_format(
    tmp_path: Path,
) -> None:
    from benchmark_reference.mmmu_cli import main
    from benchmark_reference.mmmu_measurements import paired_report

    _bundle, _plan, qa, responses = measurement_files(tmp_path)
    # Rebuild through the public CLI with an open-answer task.
    source = tmp_path / "input.json"
    value = read_json(source)
    value["samples"][0].update(
        options=[], accepted_answers=["-12 mV"], question="Read <image 1> and <image 2>."
    )
    source.write_text(json.dumps(value))
    open_bundle = tmp_path / "open-bundle"
    main(["build", "--input", str(source), "--output-dir", str(open_bundle)])
    open_plan = tmp_path / "open-plan.json"
    main(
        [
            "plan",
            "--bundle",
            str(open_bundle),
            "--profile",
            str(tmp_path / "profile.json"),
            "--output",
            str(open_plan),
        ]
    )
    qa_rows = read_json(open_bundle / "qa-template.json")
    for row in qa_rows:
        row.update(status="labels_preserved", reviewers=["one", "two"], notes="Fixture")
    qa.write_text(json.dumps(qa_rows))
    records = []
    for call in read_json(open_plan)["calls"]:
        records.append(
            {
                "attempt_id": call["attempt_id"],
                "request_sha256": call["request_sha256"],
                "status": "completed",
                "finish_reason": "stop",
                "raw_answer": "ANSWER: -12  MV"
                if call["condition_id"] == call["sample_id"]
                else "ANSWER:\n-12 mV",
            }
        )
    responses.write_text(
        json.dumps(
            {
                "evidence_kind": "synthetic",
                "plan_sha256": hashlib.sha256(open_plan.read_bytes()).hexdigest(),
                "attempts": records,
            }
        )
    )
    report = paired_report(open_bundle, open_plan, responses, qa)
    assert all(g["original_accuracy"] == 1 for g in report["groups"])
    assert all(g["transformed_accuracy"] == 0 for g in report["groups"])
    assert all(g["answer_consistency"] is None for g in report["groups"])
