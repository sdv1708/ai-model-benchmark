"""Versioned two-stage threshold policy files and the frozen-hash replay gate.

A policy file has one section for each benchmark. Each section has its own
threshold, stage-1 size, interval method, stratifier, and study settings. The
file-level ``policy_id``, ``version``, and ``frozen`` apply to every section.

The policy hash is the SHA-256 of the exact file bytes. A real-grade replay runs
only for a policy that is marked frozen. Its hash must also match the lock file
in git HEAD. An uncommitted edit to the lock file therefore authorizes nothing.
A policy change after the freeze needs a new version and a new committed hash.
"""

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.threshold_benchmarks import BENCHMARKS
from benchmark_reference.threshold_intervals import INTERVAL_METHODS
from benchmark_reference.uncertainty import validate_threshold

SCHEMA_VERSION = 5
FROZEN_LOCK = Path(__file__).resolve().parents[2] / "policies" / "frozen-policies.json"
_FILE_KEYS = {"schema_version", "policy_id", "version", "frozen", "benchmarks"}
_KEYS = {
    "threshold",
    "alpha",
    "stage1_size",
    "interval_method",
    "stratifier",
    "seeds",
    "simulation",
    "coverage",
    "cost",
    "error_rate",
}
_SIMULATION_KEYS = {"seed", "true_scores", "models_per_seed"}
_COVERAGE_KEYS = {"subsets", "stage_sizes"}
_COST_KEYS = {"stage_sizes", "bands"}
_ERROR_KEYS = {"draws", "stage_sizes", "true_scores"}
_GRID_KEYS = {"start", "stop", "step"}
MAX_COST_BANDS = 4


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """Decide whether the full-set score of ``benchmark`` is at or above ``threshold``.

    One section of a policy file. It repeats the file-level identity and
    ``frozen``, so each benchmark study needs only its own section.
    """

    policy_id: str
    version: str
    frozen: bool
    benchmark: str
    threshold: float
    alpha: float
    stage1_size: int
    interval_method: str
    stratifier: str
    seeds: tuple[int, ...]
    simulation_seed: int
    true_scores: tuple[float, ...]
    models_per_seed: int
    coverage_subsets: int
    coverage_stage_sizes: tuple[int, ...]
    cost_stage_sizes: tuple[int, ...]
    cost_bands: tuple[tuple[float, float], ...]
    error_draws: int
    error_stage_sizes: tuple[int, ...]
    error_true_scores: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class LoadedPolicy:
    """A validated policy file, its file name, and the SHA-256 of its exact bytes.

    ``benchmarks`` holds one section for each benchmark of the file, in report order.
    """

    policy_id: str
    version: str
    frozen: bool
    benchmarks: Mapping[str, ThresholdPolicy]
    file_name: str
    sha256: str

    @property
    def key(self) -> str:
        """Lock-file identity; each frozen version has exactly one hash."""
        return f"{self.policy_id}@{self.version}"


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AnalysisError(f"Policy {name} must be an integer of at least {minimum}")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"Policy {name} must be nonempty text")
    return value


def _exact_keys(value: object, expected: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise AnalysisError(f"Policy {name} keys must be exactly {sorted(expected)}")
    return value


def _stage_sizes(value: object, name: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in value)
        or value != sorted(set(value))
    ):
        raise AnalysisError(f"Policy {name} must be unique, ascending integers >= 1")
    return tuple(value)


def _number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def in_band(score: float | str, band: tuple[float, float]) -> bool:
    """True when ``score`` is in the inclusive band.

    Decimal text, not binary floats, decides membership: 0.55 is in [0.55, 0.65].
    """
    return Fraction(str(band[0])) <= Fraction(str(score)) <= Fraction(str(band[1]))


def _cost_bands(value: object, true_scores: list[float]) -> tuple[tuple[float, float], ...]:
    """Ascending ``[low, high]`` true-score ranges; each true score is in exactly one."""
    message = "Policy cost bands must be ascending, separate [low, high] pairs in [0, 1]"
    if not isinstance(value, list) or not value:
        raise AnalysisError(message)
    # The cost chart gives each band one of four colors, dash patterns, and markers.
    if len(value) > MAX_COST_BANDS:
        raise AnalysisError(f"Policy cost bands must number at most {MAX_COST_BANDS}")
    bands: list[tuple[float, float]] = []
    for band in value:
        if (
            not isinstance(band, list)
            or len(band) != 2
            or not all(_number(edge) for edge in band)
            or band[0] > band[1]
            or (bands and band[0] <= bands[-1][1])
        ):
            raise AnalysisError(message)
        bands.append((float(band[0]), float(band[1])))
    for score in true_scores:
        if not any(in_band(score, band) for band in bands):
            raise AnalysisError(f"Policy cost bands must hold every true score; {score} is in none")
    for band in bands:
        if not any(in_band(score, band) for score in true_scores):
            raise AnalysisError(f"Policy cost band {list(band)} holds no true score")
    return tuple(bands)


def _grid(value: object) -> tuple[float, ...]:
    """True scores from ``start`` to ``stop`` in exact decimal steps of ``step``.

    Each value must be a multiple of 0.01, so every true score has an exact
    two-decimal label. The step must divide the span exactly.
    """
    grid = _exact_keys(value, _GRID_KEYS, "error_rate true_scores")
    for name in ("start", "stop"):
        if not _number(grid[name]):
            raise AnalysisError(f"Policy error_rate true_scores {name} must be in [0, 1]")
    start, stop = Fraction(str(grid["start"])), Fraction(str(grid["stop"]))
    if start > stop:
        raise AnalysisError("Policy error_rate true_scores start must not exceed stop")
    if not _number(grid["step"]) or Fraction(str(grid["step"])) < Fraction(1, 100):
        raise AnalysisError("Policy error_rate true_scores step must be in [0.01, 1]")
    step = Fraction(str(grid["step"]))
    if any((value * 100).denominator != 1 for value in (start, stop, step)):
        raise AnalysisError("Policy error_rate true_scores start, stop, and step need 2 decimals")
    points = (stop - start) / step
    if points.denominator != 1:
        raise AnalysisError("Policy error_rate true_scores step must divide stop - start")
    return tuple(float(start + k * step) for k in range(int(points) + 1))


def load_policy(path: Path) -> LoadedPolicy:
    """Parse and validate one policy file; reject unknown or missing settings."""
    try:
        data = path.read_bytes()
        raw = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read policy {path}: {exc}") from exc
    value = _exact_keys(raw, _FILE_KEYS, "file")
    if value["schema_version"] != SCHEMA_VERSION:
        raise AnalysisError(f"Policy schema_version must be {SCHEMA_VERSION}")
    if not isinstance(value["frozen"], bool):
        raise AnalysisError("Policy frozen must be true or false")
    policy_id = _text(value["policy_id"], "policy_id")
    version = _text(value["version"], "version")
    sections = value["benchmarks"]
    if not isinstance(sections, dict) or not sections:
        raise AnalysisError("Policy benchmarks must name at least one benchmark")
    unknown = sorted(set(sections) - set(BENCHMARKS))
    if unknown:
        raise AnalysisError(
            f"Unknown policy benchmark {unknown[0]!r}; choose one of {tuple(BENCHMARKS)}"
        )
    benchmarks: dict[str, ThresholdPolicy] = {}
    for name in BENCHMARKS:
        if name not in sections:
            continue
        try:
            benchmarks[name] = _section(
                name, sections[name], policy_id=policy_id, version=version, frozen=value["frozen"]
            )
        except AnalysisError as exc:
            # The section name tells the reader which benchmark has the bad setting.
            raise AnalysisError(f"Policy section {name}: {exc}") from exc
    return LoadedPolicy(
        policy_id, version, value["frozen"], benchmarks, path.name, hashlib.sha256(data).hexdigest()
    )


def _section(
    benchmark: str, raw: object, *, policy_id: str, version: str, frozen: bool
) -> ThresholdPolicy:
    """Validate the section of one benchmark."""
    value = _exact_keys(raw, _KEYS, "section")
    threshold, alpha = value["threshold"], value["alpha"]
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise AnalysisError("Policy threshold must be a number")
    validate_threshold(threshold)
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, int | float)
        or not math.isfinite(alpha)
        or not 0 < alpha < 1
    ):
        raise AnalysisError("Policy alpha must be in (0, 1)")
    if value["interval_method"] not in INTERVAL_METHODS:
        raise AnalysisError(f"Policy interval_method must be one of {INTERVAL_METHODS}")
    stratifiers = BENCHMARKS[benchmark].stratifiers
    if value["stratifier"] not in stratifiers:
        raise AnalysisError(f"Policy stratifier must be one of {stratifiers}")
    seeds = value["seeds"]
    if (
        not isinstance(seeds, list)
        or not seeds
        or len(set(seeds)) != len(seeds)
        or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds)
    ):
        raise AnalysisError("Policy seeds must be a nonempty list of unique integers")
    simulation = _exact_keys(value["simulation"], _SIMULATION_KEYS, "simulation")
    scores = simulation["true_scores"]
    if (
        not isinstance(scores, list)
        or not scores
        or any(isinstance(s, bool) or not isinstance(s, int | float) for s in scores)
        or any(not math.isfinite(s) or not 0 <= s <= 1 for s in scores)
        or scores != sorted(set(scores))
    ):
        raise AnalysisError("Policy true_scores must be unique, ascending values in [0, 1]")
    coverage = _exact_keys(value["coverage"], _COVERAGE_KEYS, "coverage")
    sizes = _stage_sizes(coverage["stage_sizes"], "coverage stage_sizes")
    cost = _exact_keys(value["cost"], _COST_KEYS, "cost")
    cost_sizes = _stage_sizes(cost["stage_sizes"], "cost stage_sizes")
    bands = _cost_bands(cost["bands"], scores)
    error = _exact_keys(value["error_rate"], _ERROR_KEYS, "error_rate")
    error_sizes = _stage_sizes(error["stage_sizes"], "error_rate stage_sizes")
    # Issue #62 chooses among these sizes, so they must hold every candidate size.
    stage1_size = _integer(value["stage1_size"], "stage1_size", minimum=1)
    if not {stage1_size, *sizes} <= set(error_sizes):
        raise AnalysisError(
            "Policy error_rate stage_sizes must hold stage1_size and every coverage stage size"
        )
    return ThresholdPolicy(
        policy_id=policy_id,
        version=version,
        frozen=frozen,
        benchmark=benchmark,
        threshold=float(threshold),
        alpha=float(alpha),
        stage1_size=stage1_size,
        interval_method=str(value["interval_method"]),
        stratifier=str(value["stratifier"]),
        seeds=tuple(seeds),
        simulation_seed=_integer(simulation["seed"], "simulation seed", minimum=0),
        true_scores=tuple(float(s) for s in scores),
        models_per_seed=_integer(simulation["models_per_seed"], "models_per_seed", minimum=1),
        coverage_subsets=_integer(coverage["subsets"], "coverage subsets", minimum=1),
        coverage_stage_sizes=sizes,
        cost_stage_sizes=cost_sizes,
        cost_bands=bands,
        error_draws=_integer(error["draws"], "error_rate draws", minimum=1),
        error_stage_sizes=error_sizes,
        error_true_scores=_grid(error["true_scores"]),
    )


def alpha_spending(policy: ThresholdPolicy) -> tuple[float, float]:
    """Error budget per stage: the stage-1 interval and the census.

    The census observes every question, so it has no sampling error and spends
    nothing. The total is therefore the policy alpha.
    """
    return (policy.alpha, 0.0)


def committed_lock_text(lock_path: Path | None = None) -> str:
    """The lock file as committed in git HEAD, not as it is in the working tree."""
    lock_path = FROZEN_LOCK if lock_path is None else lock_path
    try:
        shown = subprocess.run(
            ["git", "-C", str(lock_path.parent), "show", f"HEAD:./{lock_path.name}"],
            check=True,
            capture_output=True,
        )
        return shown.stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        raise AnalysisError(f"Cannot read the committed frozen-policy lock {lock_path}") from exc


def authorize_real_replay(loaded: LoadedPolicy, *, lock_text: str | None = None) -> None:
    """Stop unless the policy is frozen and its hash matches the committed hash.

    ``lock_text`` replaces the committed lock file in tests only.
    """
    if not loaded.frozen:
        raise AnalysisError(f"Policy {loaded.key} is not marked frozen; real replay refused")
    try:
        lock = json.loads(committed_lock_text() if lock_text is None else lock_text)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"The frozen-policy lock is not valid JSON: {exc}") from exc
    if (
        not isinstance(lock, dict)
        or lock.get("schema_version") != 1
        or not isinstance(lock.get("policies"), dict)
    ):
        raise AnalysisError("The frozen-policy lock is invalid")
    committed = lock["policies"].get(loaded.key)
    if committed is None:
        raise AnalysisError(f"Policy {loaded.key} has no committed hash; real replay refused")
    if committed != loaded.sha256:
        raise AnalysisError(
            f"Policy {loaded.key} hash mismatch: file {loaded.sha256}, committed {committed}"
        )
