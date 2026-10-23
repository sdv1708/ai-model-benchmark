"""Exercise the public prototype with SCRIPTED responses, never a live endpoint."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from benchmark_reference.mmmu_images import (
    TRANSFORMS,
    build_bundle,
    create_demo,
    digest,
    load_json,
)
from benchmark_reference.mmmu_measurements import paired_report
from benchmark_reference.mmmu_requests import build_plan, write_new_json


def run(output: Path) -> None:
    if output.exists():
        raise ValueError("Choose a fresh output directory")
    create_demo(output / "inputs")
    root = output / "bundle"
    build_bundle(output / "inputs/input.json", root)
    profile = {
        "endpoint": "https://example.invalid/v1/chat/completions",
        "model": "SCRIPTED-NO-ENDPOINT",
        "detail": "high",
        "generation": {"temperature": 0, "max_completion_tokens": 128},
    }
    write_new_json(output / "profile.json", profile)
    plan = build_plan(root, profile)
    write_new_json(output / "plan.json", plan)
    bundle = load_json(root / "manifest.json")
    samples = {sample["sample_id"]: sample for sample in bundle["samples"]}
    pairs = {pair["pair_id"]: pair for pair in bundle["pairs"]}
    attempts = []
    for call in plan["calls"]:
        sample = samples[call["sample_id"]]
        subject = sample["subject"]
        pair = pairs.get(call["condition_id"])
        strong = pair is not None and pair["transform"]["severity"] == "strong"
        if subject == "diagram":
            answer = "B" if pair else "A"
        elif subject == "chart":
            answer = "A" if strong else "B"
        else:
            answer = "+12 mV" if strong else "-12 mV"
        raw_answer = f"ANSWER: {answer}"
        if pair and pair["transform"]["name"] == "text_blur" and call["repeat"] == 1:
            raw_answer = "Unparseable scripted answer"
        if pair and pair["transform"]["name"] == "blur" and strong and call["repeat"] == 1:
            continue  # Deliberately missing to exercise fixed-denominator bounds.
        attempts.append(
            {
                "attempt_id": call["attempt_id"],
                "request_sha256": call["request_sha256"],
                "status": "completed",
                "finish_reason": "stop",
                "raw_answer": raw_answer,
            }
        )
    write_new_json(
        output / "responses-SYNTHETIC.json",
        {
            "evidence_kind": "synthetic",
            "plan_sha256": digest((output / "plan.json").read_bytes()),
            "attempts": attempts,
        },
    )
    qa = [
        {
            "pair_id": pair["pair_id"],
            "status": (
                "destructive_control"
                if pair["transform"]["name"] == "occlusion"
                else "labels_preserved"
            ),
            "reviewers": ["SCRIPTED-NOT-HUMAN-1", "SCRIPTED-NOT-HUMAN-2"],
            "notes": "SYNTHETIC TEST FIXTURE. No human semantic validation was conducted.",
        }
        for pair in bundle["pairs"]
    ]
    write_new_json(output / "qa-SYNTHETIC.json", qa)
    report = paired_report(
        root,
        output / "plan.json",
        output / "responses-SYNTHETIC.json",
        output / "qa-SYNTHETIC.json",
    )
    write_new_json(output / "report-SYNTHETIC.json", report)
    canvas = Image.new("RGB", (1760, 540), "#eeeeee")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (10, 8), "SYNTHETIC VISUAL FAMILIES - strong variants - no model evidence", fill="black"
    )
    for row_index, sample in enumerate(bundle["samples"]):
        for column, name in enumerate(("original", *TRANSFORMS)):
            x, y = column * 220, 35 + row_index * 165
            draw.text((x + 5, y), f"{sample['subject']}: {name}", fill="black")
            pair = next(
                (
                    p
                    for p in bundle["pairs"]
                    if p["sample_id"] == sample["sample_id"]
                    and p["transform"]["name"] == name
                    and p["transform"]["severity"] == "strong"
                ),
                None,
            )
            artifact = (
                sample["images"][sample["target_slot"]]
                if name == "original"
                else pair["transformed_image"]
                if pair
                else None
            )
            if artifact:
                with Image.open(root / artifact["path"]) as image:
                    thumb = image.copy()
                    thumb.thumbnail((210, 135), Image.Resampling.LANCZOS)
                    canvas.paste(thumb, (x + 5, y + 20))
            else:
                draw.text((x + 5, y + 40), "Inapplicable: no pixel change", fill="black")
    canvas.save(output / "preview-SYNTHETIC.png")
    print(
        f"SYNTHETIC ONLY: {len(samples)} questions, {len(pairs)} image pairs, "
        f"{len(plan['calls'])} planned calls, {len(attempts)} scripted responses"
    )
    print(f"No endpoint called. Report: {output / 'report-SYNTHETIC.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.output_dir)
