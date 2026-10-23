"""Reproducible offline image pairs; no selection, inference, or encoder claims."""

import hashlib
import io
import json
import math
import platform
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, __version__, features

PROTOCOL = "mmmu-pairs-v1"
SLOT = re.compile(r"<image ([1-7])>")
TRANSFORMS = ("downsample", "blur", "jpeg", "occlusion", "contrast", "color", "text_blur")


def encoded_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(value: Any) -> str:
    return digest(encoded_json(value))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def object_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected a JSON object")
    return value


def text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text")
    return value


def sequence(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array")
    return value


def relative_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing file or path outside its inventory: {name}")
    return path


def png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def normalized_image(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as opened:
        if getattr(opened, "n_frames", 1) != 1:
            raise ValueError("Animated/multipage images are not supported")
        oriented = ImageOps.exif_transpose(opened).convert("RGBA")
        background = Image.new("RGBA", oriented.size, "white")
        result = Image.alpha_composite(background, oriented).convert("RGB")
        result.info.clear()
        return result


def rectangles(value: Any, size: tuple[int, int]) -> list[list[int]]:
    result: list[list[int]] = []
    for region in sequence(value):
        coords = sequence(region)
        if len(coords) != 4 or any(
            isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c)
            for c in coords
        ):
            raise ValueError("Text regions need four finite normalized coordinates")
        x0, y0, x1, y1 = coords
        if not 0 <= x0 < x1 <= 1 or not 0 <= y0 < y1 <= 1:
            raise ValueError("Text regions must satisfy 0 <= left < right <= 1 (also top/bottom)")
        box = [int(x0 * size[0]), int(y0 * size[1]), int(x1 * size[0]), int(y1 * size[1])]
        if box[0] == box[2] or box[1] == box[3]:
            raise ValueError("Text region rounds to an empty pixel mask")
        result.append(box)
    return result


def transform_image(
    image: Image.Image, name: str, level: int, regions: list[list[int]]
) -> tuple[bytes, dict[str, Any]]:
    """Pure, fixed operations; every severity starts from the same normalized original."""
    params: dict[str, Any] = {"name": name, "severity": ("mild", "strong")[level]}
    if name == "downsample":
        factor = (0.75, 0.5)[level]
        size = tuple(max(1, int(side * factor)) for side in image.size)
        result = image.resize(size, Image.Resampling.LANCZOS).resize(
            image.size, Image.Resampling.LANCZOS
        )
        params.update(scale=factor, intermediate_size=size, resampler="LANCZOS")
    elif name in {"blur", "text_blur"}:
        radius = (0.6, 1.2)[level]
        blurred = image.filter(ImageFilter.GaussianBlur(radius))
        result = blurred if name == "blur" else image.copy()
        if name == "text_blur":
            for region in regions:
                box = (region[0], region[1], region[2], region[3])
                result.paste(blurred.crop(box), box)
            params["pixel_regions"] = regions
        params["radius_px"] = radius
    elif name == "jpeg":
        quality = (75, 40)[level]
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=quality, subsampling=0, optimize=False)
        params.update(quality=quality, subsampling="4:4:4", optimize=False)
        # Re-decode to PNG so the API sees one MIME/container across conditions.
        # This isolates compression artifacts from provider format-dependent behavior.
        result = normalized_image(stream.getvalue())
    elif name == "occlusion":
        fraction = (0.05, 0.15)[level]
        width = max(1, int(image.width * fraction))
        result = image.copy()
        result.paste("#808080", (0, 0, width, image.height))
        params.update(pixel_region=[0, 0, width, image.height], fill="#808080")
    elif name in {"contrast", "color"}:
        factor = (0.75, 0.5)[level]
        enhancer = ImageEnhance.Contrast if name == "contrast" else ImageEnhance.Color
        result = enhancer(image).enhance(factor)
        params["factor"] = factor
    else:
        raise ValueError(f"Unknown transform: {name}")
    return png(result), params


def build_bundle(source: Path, output: Path) -> None:
    """Build into a new directory and publish only after all inputs are validated."""
    if output.exists():
        raise ValueError("Output already exists; choose a fresh directory")
    inventory = object_value(load_json(source))
    dataset, revision = text(inventory.get("dataset")), text(inventory.get("revision"))
    runtime = {
        "python": platform.python_version(),
        "pillow": __version__,
        "jpeg": features.version_codec("jpg"),
        "zlib": features.version_codec("zlib"),
        "implementation_sha256": digest(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
    }
    files: dict[str, bytes] = {}

    def artifact(data: bytes) -> dict[str, Any]:
        name = f"images/{digest(data)}.png"
        files[name] = data
        with Image.open(io.BytesIO(data)) as image:
            size = list(image.size)
        return {"path": name, "sha256": digest(data), "size": size}

    samples: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in sequence(inventory.get("samples")):
        row = object_value(raw)
        source_id = text(row.get("source_id"))
        if source_id in seen:
            raise ValueError(f"Duplicate source_id: {source_id}")
        seen.add(source_id)
        question = text(row.get("question"))
        options = [text(option) for option in sequence(row.get("options", []))]
        if len(options) == 1 or len(options) > 26:
            raise ValueError("Use 2..26 options for MC, or [] for open questions")
        answers = [text(answer) for answer in sequence(row.get("accepted_answers"))]
        if not answers or (
            options
            and any(
                a not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[: len(options)] or len(a) != 1
                for a in answers
            )
        ):
            raise ValueError("Accepted answers must be nonempty, valid MC letters or open strings")
        images = object_value(row.get("images"))
        referenced = {f"image_{slot}" for slot in SLOT.findall("\n".join([question, *options]))}
        if not referenced or referenced != images.keys():
            raise ValueError("Image slots must exactly match references in question and options")
        target = text(row.get("target_slot"))
        if target not in images:
            raise ValueError("target_slot is not a referenced image")
        original_images: dict[str, Any] = {}
        decoded: dict[str, Image.Image] = {}
        for slot, path in sorted(images.items()):
            data = relative_file(source.parent, text(path)).read_bytes()
            decoded[slot] = normalized_image(data)
            original_images[slot] = {**artifact(png(decoded[slot])), "source_sha256": digest(data)}
        regions = rectangles(row.get("text_regions", []), decoded[target].size)
        sample = {
            "source_id": source_id,
            "subject": text(row.get("subject")),
            "split": text(row.get("split")),
            "question": question,
            "options": options,
            "accepted_answers": answers,
            "target_slot": target,
            "images": original_images,
            "text_regions_px": regions,
        }
        sample_id = identity(
            {
                "protocol": PROTOCOL,
                "dataset": dataset,
                "revision": revision,
                "runtime": runtime,
                "sample": sample,
            }
        )
        sample["sample_id"] = sample_id
        samples.append(sample)
        for name in TRANSFORMS:
            if name == "text_blur" and not regions:
                skipped.append(
                    {
                        "sample_id": sample_id,
                        "transform": name,
                        "reason": "No reviewed text regions supplied",
                    }
                )
                continue
            for level in range(2):
                data, parameters = transform_image(decoded[target], name, level, regions)
                if digest(data) == original_images[target]["sha256"]:
                    skipped.append(
                        {
                            "sample_id": sample_id,
                            "transform": name,
                            "severity": parameters["severity"],
                            "reason": "No pixel change on this image",
                        }
                    )
                    continue
                pair = {
                    "sample_id": sample_id,
                    "source_id": source_id,
                    "target_slot": target,
                    "transform": parameters,
                    "transformed_image": artifact(data),
                }
                pair["pair_id"] = identity(pair)
                pairs.append(pair)
    if not samples:
        raise ValueError("Inventory is empty")
    manifest = {
        "protocol": PROTOCOL,
        "evidence_kind": "offline_artifacts_only",
        "dataset": dataset,
        "revision": revision,
        "runtime": runtime,
        "normalization": "EXIF transpose; alpha over white; RGB PNG without metadata",
        "samples": samples,
        "pairs": pairs,
        "inapplicable": skipped,
    }
    files["manifest.json"] = encoded_json(manifest)
    files["qa-template.json"] = encoded_json(
        [
            {"pair_id": pair["pair_id"], "status": "pending", "reviewers": [], "notes": ""}
            for pair in pairs
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mmmu-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, contents in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        staging.rename(output)


def create_demo(output: Path) -> None:
    """Tiny synthetic visual families, explicitly unrelated to MMMU population estimates."""
    if output.exists():
        raise ValueError("Demo output already exists; choose a fresh directory")
    output.mkdir(parents=True)
    rows = []
    for family in ("chart", "diagram", "text"):
        image = Image.new("RGB", (480, 300), "white")
        draw = ImageDraw.Draw(image)
        draw.text((20, 10), f"SYNTHETIC {family.upper()} - not an MMMU sample", fill="black")
        if family == "chart":
            draw.line((50, 55, 50, 250, 430, 250), fill="black", width=2)
            draw.rectangle((100, 130, 180, 249), fill="#e03030")
            draw.rectangle((260, 80, 340, 249), fill="#2040d0")
            draw.text((110, 255), "Red: 12", fill="black")
            draw.text((270, 255), "Blue: 17", fill="black")
            question, options, answer = "Which bar is taller in <image 1>?", ["Red", "Blue"], "B"
        elif family == "diagram":
            draw.rectangle((70, 100, 180, 190), outline="black", width=2)
            draw.rectangle((300, 100, 410, 190), outline="black", width=2)
            draw.text((110, 140), "A", fill="black")
            draw.text((340, 140), "B", fill="black")
            draw.line((180, 145, 300, 145), fill="black", width=2)
            draw.polygon(((300, 145), (288, 139), (288, 151)), fill="black")
            question, options, answer = "Where does the arrow point in <image 1>?", ["A", "B"], "B"
        else:
            draw.text((70, 100), "Voltage: -12 mV", fill="black")
            draw.text((70, 140), "Current: 4 mA", fill="black")
            question, options, answer = (
                "Read the voltage, including units, in <image 1>.",
                [],
                "-12 mV",
            )
        image.save(output / f"{family}.png")
        rows.append(
            {
                "source_id": f"synthetic-{family}",
                "subject": family,
                "split": "synthetic",
                "question": question,
                "options": options,
                "accepted_answers": [answer],
                "images": {"image_1": f"{family}.png"},
                "target_slot": "image_1",
                "text_regions": [[0.1, 0.25, 0.9, 0.95]],
            }
        )
    (output / "input.json").write_bytes(
        encoded_json({"dataset": "synthetic-visual-demo", "revision": "v1", "samples": rows})
    )
