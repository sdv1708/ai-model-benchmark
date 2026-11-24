"""The committed results page is the page that the recorded data gives."""

import importlib.util
from collections.abc import Callable
from pathlib import Path

TOOL = Path(__file__).parents[1] / "tools" / "build_results_page.py"
DOCS = TOOL.parents[2] / "docs"


def _outputs() -> dict[str, bytes]:
    spec = importlib.util.spec_from_file_location("build_results_page", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outputs: Callable[[], dict[str, bytes]] = module.outputs
    return outputs()


def test_the_committed_page_and_charts_match_the_recorded_data() -> None:
    outputs = _outputs()
    assert set(outputs) == {
        "results.md",
        "results-distance-light.svg",
        "results-distance-dark.svg",
    }
    for name, data in outputs.items():
        assert (DOCS / name).read_bytes() == data, name


def test_the_page_states_the_published_numbers_and_the_hard_case() -> None:
    page = _outputs()["results.md"].decode("utf-8")
    # The numbers come from the recorded reports of #63, #77, #76, and #88.
    for text in (
        "made 82.7% of 28,000 decisions",
        "the mean cost was 33.8% of the questions",
        "with 601 wrong of 1,708,000 decisions",
        "61 thresholds from 0.30 to 0.90",
        "Wrong decisions: 1. A random probe of the same size made 25 wrong decisions.",
        "43.3% of the estimated tokens",
        "0 of 1,206,000 decisions were wrong",
        "made 40.6% of the decisions, at 67.4% of the tokens",
        "19 of 28 models score within 0.10",
        "Wrong decisions fall from 601 to 130.",
        "25.4% with 63 of 315 questions and 82.0% with 211 of 1,055",
        "The verdicts of 8 answers (2.7%) were not all equal.",
        "2 to 7 points above the saved scores",
        "made 10 of the 13 INCORRECT again",
    ):
        assert text in page
    assert page.count("| Pass |") == 3
