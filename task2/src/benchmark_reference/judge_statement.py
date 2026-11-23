"""The judge-noise sentences of the threshold report.

The sentences are the fixed limit until a measured record exists. The record is
``aa-lcr-judge-noise.json`` in the panel folder. ``aa-lcr-judge report --record``
writes it from a complete run.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark_reference.models import AnalysisError

RECORD_FILE = "aa-lcr-judge-noise.json"
RECORD_SCHEMA = 1
NOT_MEASURED = (
    "Judge noise is not measured. An LLM judge grades each answer. The saved data has one "
    "judgment for each answer. The simulated grades have no judge noise, so these results "
    "do not include it. A real decision also carries the error of the judge."
)
NOT_MEASURED_CELL = "One judgment for each answer; not measured"


@dataclass(frozen=True, slots=True)
class JudgeNoise:
    """The sentences of one measured record, and the SHA-256 of its bytes."""

    sha256: str
    statement: str
    cell: str


def describe(record: Mapping[str, Any]) -> tuple[str, str]:
    """The note beside every AA-LCR result, and the cell of the side-by-side table."""
    disagree, spread = record["disagreement"], record["full_set_score"]
    changes, interval = record["decisions"], record["stage1_interval"]
    share = f"{disagree['share']:.1%}"
    statement = (
        f"Judge noise is measured on the saved answers, not on the simulated ones. The judge "
        f"{record['judge_model']} graded each of {disagree['answers']} answers "
        f"{record['passes']} times ({record['run_dates']}). The judgments are not all equal for "
        f"{disagree['not_unanimous']} answers ({share}). Between passes, the full-set score of a "
        f"model changed by at most {spread['largest_range']:.2f}, and "
        f"{changes['models_that_change']} of {changes['models']} full-set decisions at threshold "
        f"{changes['threshold']:.2f} changed. The stage-1 interval of policy {interval['policy']} "
        f"has a mean width of {interval['mean_width']:.3f} on these answers. The policy interval "
        "excludes judge noise, and the simulated grades have none. A real decision also carries "
        "the error of the judge."
    )
    cell = (
        f"{share} of answers have unequal judgments in {record['passes']} passes; "
        "the policy interval excludes it"
    )
    return statement, cell


def load_judge_noise(path: Path, *, panel_sha256: str) -> JudgeNoise | None:
    """The measured record, or None when the file does not exist."""
    if not path.exists():
        return None
    data = path.read_bytes()
    try:
        record = json.loads(data)
        if record["schema_version"] != RECORD_SCHEMA:
            raise AnalysisError(f"{path} has an unknown schema")
        if record["reference_panel_sha256"] != panel_sha256:
            raise AnalysisError(f"{path} is a record of another reference panel")
        if record["loopback_test"] is not False:
            raise AnalysisError(f"{path} is a loopback test, which measures nothing")
        statement, cell = describe(record)
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, AnalysisError):
            raise
        raise AnalysisError(f"{path} is not a judge-noise record: {exc}") from exc
    return JudgeNoise(hashlib.sha256(data).hexdigest(), statement, cell)
