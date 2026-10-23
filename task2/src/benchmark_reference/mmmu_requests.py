"""Materialize answer-blind Chat Completions requests, without making network calls."""

import base64
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from benchmark_reference.mmmu_images import (
    PROTOCOL,
    SLOT,
    digest,
    encoded_json,
    identity,
    load_json,
    object_value,
    relative_file,
    text,
)


def load_bundle(root: Path) -> dict[str, Any]:
    bundle = object_value(load_json(root / "manifest.json"))
    if bundle["protocol"] != PROTOCOL:
        raise ValueError("Unsupported bundle protocol")
    for artifact in [
        *(image for sample in bundle["samples"] for image in sample["images"].values()),
        *(pair["transformed_image"] for pair in bundle["pairs"]),
    ]:
        data = relative_file(root, artifact["path"]).read_bytes()
        if digest(data) != artifact["sha256"]:
            raise ValueError("Image checksum mismatch")
    return bundle


def validate_profile(value: Any) -> dict[str, Any]:
    profile = object_value(value)
    if set(profile) != {"endpoint", "model", "detail", "generation"}:
        raise ValueError(
            "Profile needs exactly endpoint, model, detail, generation; no credentials"
        )
    parsed = urlsplit(text(profile["endpoint"]))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/chat/completions")
    ):
        raise ValueError("Use a credential-free HTTPS Chat Completions endpoint")
    text(profile["model"])
    if profile["detail"] not in {"low", "high", "auto", "original"}:
        raise ValueError("Invalid image detail")
    generation = object_value(profile["generation"])
    if set(generation) - {"temperature", "top_p", "max_tokens", "max_completion_tokens", "seed"}:
        raise ValueError("Unsupported generation option")
    caps = set(generation) & {"max_tokens", "max_completion_tokens"}
    if len(caps) != 1:
        raise ValueError("Specify exactly one completion-token cap supported by your provider")
    for name, value in generation.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Invalid generation value: {name}")
        if name in caps and (not isinstance(value, int) or value < 1):
            raise ValueError("Completion cap must be a positive integer")
        if name == "temperature" and not 0 <= value <= 2:
            raise ValueError("Temperature must be in [0,2]")
        if name == "top_p" and not 0 < value <= 1:
            raise ValueError("top_p must be in (0,1]")
        if name == "seed" and not isinstance(value, int):
            raise ValueError("Provider seed must be an integer")
    encoded_json(profile)  # rejects nonfinite values
    return profile


def request_body(
    root: Path, sample: dict[str, Any], profile: dict[str, Any], pair: dict[str, Any] | None
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    prompt = (
        sample["question"]
        + "\n"
        + "\n".join(
            f"{chr(65 + index)}. {option}" for index, option in enumerate(sample["options"])
        )
    )
    prompt += "\nReply only in this format, without extra punctuation: ANSWER: " + (
        "<letter>" if sample["options"] else "<value>"
    )
    offset = 0
    for match in SLOT.finditer(prompt):
        if match.start() > offset:
            content.append({"type": "text", "text": prompt[offset : match.start()]})
        slot = f"image_{match[1]}"
        artifact = (
            pair["transformed_image"]
            if pair and pair["target_slot"] == slot
            else sample["images"][slot]
        )
        data = relative_file(root, artifact["path"]).read_bytes()
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                    "detail": profile["detail"],
                },
            }
        )
        offset = match.end()
    if offset < len(prompt):
        content.append({"type": "text", "text": prompt[offset:]})
    return {
        "model": profile["model"],
        "messages": [{"role": "user", "content": content}],
        **profile["generation"],
        "stream": False,
    }


def build_plan(root: Path, profile: Any, repeats: int = 2, seed: int = 23) -> dict[str, Any]:
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer in [1,20]")
    profile = validate_profile(profile)
    bundle = load_bundle(root)
    bundle_sha256 = digest((root / "manifest.json").read_bytes())
    samples = {sample["sample_id"]: sample for sample in bundle["samples"]}
    calls = []
    for condition in [*bundle["samples"], *bundle["pairs"]]:
        sample = samples[condition["sample_id"]]
        pair = condition if "pair_id" in condition else None
        condition_id = condition["pair_id"] if pair else sample["sample_id"]
        body = request_body(root, sample, profile, pair)
        for repeat in range(repeats):
            call = {
                "condition_id": condition_id,
                "sample_id": sample["sample_id"],
                "repeat": repeat,
                "request_sha256": identity(body),
                "body": body,
            }
            call["attempt_id"] = identity({"bundle": bundle_sha256, "profile": profile, **call})
            calls.append(call)
    calls.sort(key=lambda call: identity([seed, call["attempt_id"]]))
    return {
        "protocol": PROTOCOL,
        "bundle_sha256": bundle_sha256,
        "profile": profile,
        "repeats": repeats,
        "schedule_seed": seed,
        "endpoint_executed": False,
        "calls": calls,
    }


def write_new_json(path: Path, value: Any) -> None:
    data = encoded_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
