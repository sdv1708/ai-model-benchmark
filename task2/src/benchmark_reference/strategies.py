"""Register study candidates without promoting or duplicating forbidden baselines."""

from dataclasses import dataclass

from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import BASELINES, CandidateSelector, select_baseline


@dataclass(frozen=True, slots=True)
class StudyStrategy:
    name: str
    role: str
    selector: CandidateSelector


def study_strategies(
    candidate_names: tuple[str, ...], candidate_selector: CandidateSelector
) -> tuple[StudyStrategy, ...]:
    """Keep comparison-only names reserved at both public evaluation boundaries."""
    if (
        not candidate_names
        or any(not isinstance(name, str) or not name.strip() for name in candidate_names)
        or len(set(candidate_names)) != len(candidate_names)
        or set(candidate_names) & set(BASELINES)
    ):
        raise AnalysisError(
            "Candidate strategies must be nonempty, named, unique and disjoint from baselines"
        )
    return (
        *(StudyStrategy(name, "candidate", candidate_selector) for name in candidate_names),
        *(StudyStrategy(name, "comparison_baseline", select_baseline) for name in BASELINES),
    )
