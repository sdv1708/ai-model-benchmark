"""Versioned two-stage threshold policy files and the frozen-hash replay gate.

The policy hash is the SHA-256 of the exact file bytes. A real-grade replay runs
only for a policy that is marked frozen. Its hash must also match the lock file
in git HEAD. An uncommitted edit to the lock file therefore authorizes nothing.
A policy change after the freeze needs a new version and a new committed hash.
"""

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import CANDIDATES
from benchmark_reference.uncertainty import validate_threshold

POOLED_EXACT = "pooled_exact_hypergeometric"
INTERVAL_METHODS = (POOLED_EXACT,)
FROZEN_LOCK = Path(__file__).resolve().parents[2] / "policies" / "frozen-policies.json"
_KEYS = {
    "schema_version",
    "policy_id",
    "version",
    "frozen",
    "benchmark",
    "threshold",
    "alpha",
    "stage1_size",
    "interval_method",
    "stratifier",
    "seeds",
    "simulation",
}
_SIMULATION_KEYS = {"seed", "true_scores", "models_per_seed"}


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """Decide whether the full-set score is at or above ``threshold``."""

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


@dataclass(frozen=True, slots=True)
class LoadedPolicy:
    """A validated policy, its file name, and the SHA-256 of its exact bytes."""

    policy: ThresholdPolicy
    file_name: str
    sha256: str

    @property
    def key(self) -> str:
        """Lock-file identity; each frozen version has exactly one hash."""
        return f"{self.policy.policy_id}@{self.policy.version}"


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


def load_policy(path: Path) -> LoadedPolicy:
    """Parse and validate one policy file; reject unknown or missing settings."""
    try:
        data = path.read_bytes()
        raw = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"Cannot read policy {path}: {exc}") from exc
    value = _exact_keys(raw, _KEYS, "file")
    if value["schema_version"] != 1:
        raise AnalysisError("Policy schema_version must be 1")
    if not isinstance(value["frozen"], bool):
        raise AnalysisError("Policy frozen must be true or false")
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
    if value["stratifier"] not in CANDIDATES:
        raise AnalysisError(f"Policy stratifier must be one of {CANDIDATES}")
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
    policy = ThresholdPolicy(
        policy_id=_text(value["policy_id"], "policy_id"),
        version=_text(value["version"], "version"),
        frozen=value["frozen"],
        benchmark=_text(value["benchmark"], "benchmark"),
        threshold=float(threshold),
        alpha=float(alpha),
        stage1_size=_integer(value["stage1_size"], "stage1_size", minimum=1),
        interval_method=str(value["interval_method"]),
        stratifier=str(value["stratifier"]),
        seeds=tuple(seeds),
        simulation_seed=_integer(simulation["seed"], "simulation seed", minimum=0),
        true_scores=tuple(float(s) for s in scores),
        models_per_seed=_integer(simulation["models_per_seed"], "models_per_seed", minimum=1),
    )
    return LoadedPolicy(policy, path.name, hashlib.sha256(data).hexdigest())


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
    if not loaded.policy.frozen:
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
