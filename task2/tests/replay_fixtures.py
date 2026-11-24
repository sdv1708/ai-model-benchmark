"""A synthetic world for the real-grade commands: every input file, with made-up grades.

The public file, the reference panels, and the question mapping are synthetic
copies. The model names are real, because the policy names them, but every
grade is made up. Nothing here opens the downloaded public file.
"""

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policy_fixtures import TASK2, draft_value, frozen_value, write_policy

from benchmark_reference.threshold_benchmarks import BENCHMARKS, LIVE_CODE_BENCH

DATA = TASK2 / "data"
SEEDS, SUBSETS = 10, 20
THRESHOLDS = ("0.50", "0.60", "0.70", "0.80", "0.90")
VALUES = (0.0, 10.0, 50.0, 90.0, 100.0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def synthetic_panels(folder: Path) -> None:
    """Copies of the committed panels with made-up grades."""
    rng = random.Random(63)
    for benchmark in BENCHMARKS.values():
        panel = json.loads((DATA / benchmark.panel_file).read_text(encoding="utf-8"))
        for task in panel["tasks"]:
            hard = rng.random()
            task["scores"] = {m: int(rng.random() > hard) for m in sorted(task["scores"])}
        (folder / benchmark.panel_file).write_text(json.dumps(panel), encoding="utf-8")


def synthetic_mapping(folder: Path) -> tuple[Path, list[str]]:
    """The committed mapping, bound to the synthetic panel."""
    document = json.loads((DATA / "lcb-public-mapping.json").read_text(encoding="utf-8"))
    document["panel_sha256"] = sha(folder / BENCHMARKS[LIVE_CODE_BENCH].panel_file)
    path = folder / "lcb-public-mapping.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, [entry["question_id"] for entry in document["questions"]]


def synthetic_public(path: Path, models: list[str], mapped: list[str]) -> None:
    """A file of the public schema and shape with made-up ``pass@1`` values."""
    rng = random.Random(85)
    questions = [*mapped, *(f"other-{k}" for k in range(1055 - len(mapped)))]
    rows = []
    for rank, model in enumerate(models):
        skill = 0.15 + 0.8 * rank / (len(models) - 1)
        for question in questions:
            good = rng.random() < skill
            rows.append(
                {
                    "question_id": question,
                    "model": model,
                    "date": 1719705600000,
                    "difficulty": "easy",
                    "pass@1": rng.choice(VALUES[2:] if good else VALUES[:2]),
                    "platform": "synthetic",
                }
            )
    listed = [{"model_repr": m} for m in models]
    path.write_text(json.dumps({"performances": rows, "models": listed}), encoding="utf-8")


@dataclass(frozen=True)
class World:
    folder: Path
    policy: Path
    public: Path
    mapping: Path
    lock: str

    def argv(self, output: Path, *extra: str) -> list[str]:
        return [
            *("--policy", str(self.policy), "--real-grades"),
            *("--panel-dir", str(self.folder), "--public-file", str(self.public)),
            *("--mapping", str(self.mapping), "--output-dir", str(output), *extra),
        ]


def policy_value(folder: Path, public: Path, mapping: Path) -> dict[str, Any]:
    base = draft_value()
    for section in base["benchmarks"].values():
        section["seeds"] = [0, 1, 2]
    value = frozen_value(base)
    protocol = value["protocol"]
    protocol["public_panel"]["sha256"] = sha(public)
    protocol["public_panel"]["mapping_sha256"] = sha(mapping)
    replay = protocol["unseen_model_replay"]
    replay["reference_panel_sha256"] = sha(folder / BENCHMARKS[LIVE_CODE_BENCH].panel_file)
    replay["selection_seeds"] = {"first": 0, "last": SEEDS - 1}
    replay["coverage_subsets"] = SUBSETS
    replay["thresholds"] = {"start": 0.5, "stop": 0.9, "step": 0.1}
    return value


def public_models() -> list[str]:
    groups = frozen_value()["protocol"]["reference_panel_study"]["developer_groups"]
    return sorted(model for models in groups.values() for model in models)


def build_world(folder: Path) -> World:
    """Every input of the real-grade commands in ``folder``, with made-up grades."""
    synthetic_panels(folder)
    mapping, questions = synthetic_mapping(folder)
    public = folder / "public.json"
    synthetic_public(public, public_models(), questions)
    policy = write_policy(folder / "policy.json", policy_value(folder, public, mapping))
    lock = json.dumps({"schema_version": 1, "policies": {"threshold-policy@v1": sha(policy)}})
    return World(folder, policy, public, mapping, lock)
