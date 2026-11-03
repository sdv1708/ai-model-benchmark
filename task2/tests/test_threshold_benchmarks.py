"""Reference panels of each benchmark and the strata of their stratifiers."""

import json
from collections import Counter
from pathlib import Path

import pytest

from benchmark_reference.long_context import TaskMetadata, select_long_context
from benchmark_reference.models import AnalysisError
from benchmark_reference.pruning import reference_strata
from benchmark_reference.threshold_benchmarks import (
    AA_LCR,
    LIVE_CODE_BENCH,
    ReferencePanel,
    load_reference_panel,
)

DATA = Path(__file__).parents[1] / "data"
AA_LCR_PANEL = DATA / "aa-lcr-reference-panel.json"


def _sizes(groups: dict[str, list[int]]) -> dict[str, int]:
    return {key: len(members) for key, members in groups.items()}


def test_aa_lcr_panel_gives_length_and_document_strata_from_its_metadata() -> None:
    panel = load_reference_panel(AA_LCR_PANEL, benchmark=AA_LCR)
    assert panel.stratifiers == ("metadata_stratified", "length_difficulty_stratified")
    assert len(panel.questions) == 100
    assert panel.metadata[0] == TaskMetadata(
        94494,
        tuple(json.loads(AA_LCR_PANEL.read_text(encoding="utf-8"))["tasks"][0]["source_urls"]),
    )
    # Hand counts from the committed panel: input-length thirds x document-count thirds.
    # Two strata hold fewer than five questions.
    assert _sizes(panel.strata("metadata_stratified")) == {
        "length:0|documents:0": 16,
        "length:0|documents:1": 17,
        "length:1|documents:0": 3,
        "length:1|documents:1": 16,
        "length:1|documents:2": 15,
        "length:2|documents:0": 15,
        "length:2|documents:1": 2,
        "length:2|documents:2": 16,
    }
    assert sorted(_sizes(panel.strata("length_difficulty_stratified")).values()) == [
        4, 5, 5, 6, 7, 7, 9, 10, 10, 11, 11, 15,
    ]  # fmt: skip


@pytest.mark.parametrize("stratifier", ["metadata_stratified", "length_difficulty_stratified"])
def test_aa_lcr_strata_are_the_strata_of_the_subset_study(stratifier: str) -> None:
    panel = load_reference_panel(AA_LCR_PANEL, benchmark=AA_LCR)
    census = select_long_context(
        panel.references, metadata=panel.metadata, strategy=stratifier, keep_ratio=1.0, seed=0
    )
    expected: dict[str, list[int]] = {}
    for item in census:
        expected.setdefault(item.stratum, []).append(item.index)
    assert panel.strata(stratifier) == expected


def test_lcb_panel_uses_reference_strata_and_has_no_metadata() -> None:
    panel = load_reference_panel(DATA / "lcb-reference-panel.json", benchmark=LIVE_CODE_BENCH)
    assert panel.stratifiers == ("difficulty_stratified", "response_stratified")
    assert panel.metadata == {}
    assert panel.strata("difficulty_stratified") == reference_strata(
        panel.references, strategy="difficulty_stratified"
    )


@pytest.mark.parametrize(
    ("benchmark", "stratifier"),
    [(AA_LCR, "difficulty_stratified"), (LIVE_CODE_BENCH, "metadata_stratified")],
)
def test_a_stratifier_of_another_benchmark_is_refused(benchmark: str, stratifier: str) -> None:
    references = {m: {0: 1.0, 1: 0.0} for m in "ab"}
    metadata = {i: TaskMetadata(10 + i, (f"doc{i}",)) for i in (0, 1)}
    panel = ReferencePanel(benchmark, references, metadata if benchmark == AA_LCR else {})
    with pytest.raises(AnalysisError, match=f"not a {benchmark} stratifier"):
        panel.strata(stratifier)


def test_aa_lcr_panel_needs_metadata_for_every_question() -> None:
    references = {m: {0: 1.0, 1: 0.0} for m in "ab"}
    with pytest.raises(AnalysisError, match="metadata"):
        ReferencePanel(AA_LCR, references, {0: TaskMetadata(10, ("doc",))})


def test_aa_lcr_panel_file_without_input_tokens_is_rejected(tmp_path: Path) -> None:
    value = json.loads(AA_LCR_PANEL.read_text(encoding="utf-8"))
    del value["tasks"][5]["input_tokens"]
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AnalysisError, match="input_tokens"):
        load_reference_panel(path, benchmark=AA_LCR)


def test_unknown_benchmark_is_refused() -> None:
    with pytest.raises(AnalysisError, match="Unknown benchmark"):
        ReferencePanel("mmmu", {"a": {0: 1.0}})
    with pytest.raises(AnalysisError, match="Unknown benchmark"):
        load_reference_panel(AA_LCR_PANEL, benchmark="mmmu")


def test_lcb_panel_must_not_have_question_metadata() -> None:
    references = {m: {0: 1.0} for m in "ab"}
    with pytest.raises(AnalysisError, match="must not have question metadata"):
        ReferencePanel(LIVE_CODE_BENCH, references, {0: TaskMetadata(10, ("doc",))})


def test_panel_keeps_plain_copies_that_a_worker_can_unpickle() -> None:
    import pickle
    from types import MappingProxyType

    grades = MappingProxyType({0: 1.0, 1: 0.0})
    panel = ReferencePanel(LIVE_CODE_BENCH, MappingProxyType({"a": grades, "b": grades}))
    assert pickle.loads(pickle.dumps(panel)) == panel


def test_equal_lengths_and_document_counts_share_one_band() -> None:
    # Two length bands with one shared document set: the documents band is the same.
    references = {m: dict.fromkeys(range(6), 1.0) for m in "ab"}
    metadata = {i: TaskMetadata(100 if i < 3 else 900, ("doc",)) for i in range(6)}
    panel = ReferencePanel(AA_LCR, references, metadata)
    groups = panel.strata("metadata_stratified")
    assert Counter({k: len(v) for k, v in groups.items()}) == Counter(
        {"length:0|documents:1": 3, "length:2|documents:1": 3}
    )
