"""Public LiveCodeBench results: fetch, locked grades, and the question mapping.

Every test uses a small synthetic file with the schema of the public file.
No test reads or prints a real model score.
"""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmark_reference.models import AnalysisError
from benchmark_reference.public_lcb import (
    PINNED_SOURCE,
    RECORDED_SHAPE,
    DatasetQuestion,
    MappedQuestion,
    PublicQuestion,
    PublicResults,
    PublicShape,
    PublicSource,
    fetch_source,
    load_mapping,
    load_public_grades,
    load_public_results,
    map_panel_questions,
    mapping_document,
    panel_fingerprints,
    question_fingerprint,
)
from benchmark_reference.threshold_policy import LoadedPolicy, load_policy

TASK2 = Path(__file__).parents[1]
DRAFT = TASK2 / "policies" / "threshold-draft.json"
COMMITTED_PANEL = TASK2 / "data" / "lcb-reference-panel.json"
COMMITTED_MAPPING = TASK2 / "data" / "lcb-public-mapping.json"

SYNTHETIC = b'{"performances": [], "models": [], "date_marks": []}'
SHAPE = PublicShape(models=2, questions=3)
QUESTIONS = {
    "abc301_a": (1682899200000, "easy", "atcoder"),
    "1873_A": (1692662400000, "medium", "codeforces"),
    "3324": (1700000000000, "hard", "leetcode"),
}
MODELS = ("Model-B", "Model-A")


def _results(**changes: Any) -> dict[str, Any]:
    """A synthetic public file: 2 models and 3 questions, every cell present.

    The ``pass@1`` values are made up. They follow no real model.
    """
    rows = [
        {
            "question_id": question,
            "model": model,
            "date": date,
            "difficulty": difficulty,
            "pass@1": float(25 * (m + q)),
            "platform": platform,
        }
        for m, model in enumerate(MODELS)
        for q, (question, (date, difficulty, platform)) in enumerate(QUESTIONS.items())
    ]
    models = [
        {
            "model_name": model.lower(),
            "model_repr": model,
            "model_style": "Synthetic",
            "release_date": 1719705600000,
            "link": "https://example.invalid",
        }
        for model in MODELS
    ]
    value: dict[str, Any] = {"performances": rows, "models": models, "date_marks": [1682899200000]}
    value.update(changes)
    return value


def _write(path: Path, value: object) -> tuple[Path, str]:
    data = json.dumps(value).encode("utf-8")
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _source(data: bytes) -> PublicSource:
    return PublicSource(
        url="https://example.invalid/performances_generation.json",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def test_pinned_source_is_the_recorded_public_file() -> None:
    assert (
        PublicSource(
            url="https://livecodebench.github.io/performances_generation.json",
            sha256="17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1",
            size=6_950_346,
        )
        == PINNED_SOURCE
    )


def test_fetch_saves_the_file_when_its_hash_matches_the_pin(tmp_path: Path) -> None:
    destination = tmp_path / "external" / "performances_generation.json"
    source = _source(SYNTHETIC)
    digest = fetch_source(destination, source=source, download=lambda url, limit: SYNTHETIC)
    assert digest == source.sha256
    assert destination.read_bytes() == SYNTHETIC


def test_fetch_stops_and_writes_nothing_when_the_hash_differs(tmp_path: Path) -> None:
    destination = tmp_path / "performances_generation.json"
    source = _source(SYNTHETIC)
    changed = SYNTHETIC.replace(b"[]", b"[ ]", 1)
    with pytest.raises(AnalysisError, match="differs from the pinned SHA-256"):
        fetch_source(destination, source=source, download=lambda url, limit: changed)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_fetch_keeps_an_existing_file_when_the_hash_differs(tmp_path: Path) -> None:
    destination = tmp_path / "performances_generation.json"
    destination.write_bytes(SYNTHETIC)
    with pytest.raises(AnalysisError, match="differs from the pinned SHA-256"):
        fetch_source(destination, source=_source(SYNTHETIC), download=lambda url, limit: b"{}")
    assert destination.read_bytes() == SYNTHETIC


def test_fetch_downloads_the_source_url_with_a_size_limit(tmp_path: Path) -> None:
    calls: list[tuple[str, int]] = []

    def download(url: str, limit: int) -> bytes:
        calls.append((url, limit))
        return SYNTHETIC

    source = _source(SYNTHETIC)
    fetch_source(tmp_path / "file.json", source=source, download=download)
    # The limit is larger than the pinned size, so a larger answer is visible as a mismatch.
    assert calls == [(source.url, source.size + 1)]


def test_recorded_shape_is_28_models_and_1055_questions() -> None:
    assert PublicShape(models=28, questions=1055) == RECORDED_SHAPE


def test_loader_gives_questions_dates_labels_platforms_and_models(tmp_path: Path) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    results = load_public_results(path, sha256=digest, shape=SHAPE)
    assert results.sha256 == digest
    assert results.models == ("Model-A", "Model-B")
    assert results.questions == {
        "1873_A": PublicQuestion("1873_A", 1692662400000, "medium", "codeforces"),
        "3324": PublicQuestion("3324", 1700000000000, "hard", "leetcode"),
        "abc301_a": PublicQuestion("abc301_a", 1682899200000, "easy", "atcoder"),
    }
    assert list(results.questions) == ["1873_A", "3324", "abc301_a"]


def test_loader_result_holds_no_grade(tmp_path: Path) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    results = load_public_results(path, sha256=digest, shape=SHAPE)
    # The metadata result has no field for grades; only load_public_grades gives them.
    assert [field.name for field in dataclasses.fields(results)] == [
        "sha256",
        "models",
        "questions",
    ]
    assert [field.name for field in dataclasses.fields(PublicQuestion)] == [
        "question_id",
        "date",
        "difficulty",
        "platform",
    ]


def _rows(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = value["performances"]
    return rows


def test_loader_rejects_a_missing_cell(tmp_path: Path) -> None:
    value = _results()
    removed = _rows(value).pop(4)
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="missing cell") as raised:
        load_public_results(path, sha256=digest, shape=SHAPE)
    assert f"model {removed['model']!r}" in str(raised.value)
    assert f"question {removed['question_id']!r}" in str(raised.value)


def test_loader_rejects_a_duplicate_model_and_question_pair(tmp_path: Path) -> None:
    value = _results()
    _rows(value).append({**_rows(value)[0], "pass@1": 0.0})
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="duplicate model and question pair"):
        load_public_results(path, sha256=digest, shape=SHAPE)


def test_loader_rejects_a_duplicate_model_in_the_model_list(tmp_path: Path) -> None:
    value = _results()
    value["models"].append(dict(value["models"][0]))
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="duplicate model 'Model-B'"):
        load_public_results(path, sha256=digest, shape=SHAPE)


@pytest.mark.parametrize("grade", [100.5, -0.5, float("nan"), float("inf"), True, "50", None])
def test_loader_rejects_a_pass_at_1_value_outside_0_to_100(tmp_path: Path, grade: object) -> None:
    value = _results()
    _rows(value)[2]["pass@1"] = grade
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="pass@1 must be a number from 0 to 100") as raised:
        load_public_results(path, sha256=digest, shape=SHAPE)
    # The message names the cell, never its value.
    assert "question '3324'" in str(raised.value)
    assert str(grade) not in str(raised.value).replace(str(path), "")


def test_loader_accepts_the_bounds_0_and_100(tmp_path: Path) -> None:
    value = _results()
    _rows(value)[0]["pass@1"] = 0
    _rows(value)[1]["pass@1"] = 100
    path, digest = _write(tmp_path / "public.json", value)
    assert load_public_results(path, sha256=digest, shape=SHAPE).models == ("Model-A", "Model-B")


@pytest.mark.parametrize(
    ("shape", "message"),
    [
        (PublicShape(models=3, questions=3), "2 models, but the recorded shape has 3"),
        (PublicShape(models=2, questions=4), "3 questions, but the recorded shape has 4"),
    ],
)
def test_loader_rejects_a_count_that_differs_from_the_recorded_shape(
    tmp_path: Path, shape: PublicShape, message: str
) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    with pytest.raises(AnalysisError, match=message):
        load_public_results(path, sha256=digest, shape=shape)


def test_loader_rejects_a_file_with_another_hash(tmp_path: Path) -> None:
    path, _ = _write(tmp_path / "public.json", _results())
    with pytest.raises(AnalysisError, match="not the pinned"):
        load_public_results(path, sha256="0" * 64, shape=SHAPE)


def test_loader_checks_the_pinned_hash_by_default(tmp_path: Path) -> None:
    path, _ = _write(tmp_path / "public.json", _results())
    with pytest.raises(AnalysisError, match=f"not the pinned {PINNED_SOURCE.sha256}"):
        load_public_results(path, shape=SHAPE)


@pytest.mark.parametrize(
    ("field", "setting", "message"),
    [
        ("difficulty", "trivial", "difficulty must be one of"),
        ("date", "2023-05-08", "date must be a nonnegative integer"),
        ("platform", "", "platform must be nonempty text"),
        ("model", "Model-C", "not in the model list"),
    ],
)
def test_loader_rejects_an_invalid_row_field(
    tmp_path: Path, field: str, setting: object, message: str
) -> None:
    value = _results()
    _rows(value)[0][field] = setting
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match=message):
        load_public_results(path, sha256=digest, shape=SHAPE)


def test_loader_rejects_metadata_that_differs_between_models(tmp_path: Path) -> None:
    value = _results()
    # Row 3 is the first question of the second model.
    _rows(value)[3]["difficulty"] = "hard"
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="differs between rows"):
        load_public_results(path, sha256=digest, shape=SHAPE)


def test_loader_rejects_a_row_with_another_set_of_fields(tmp_path: Path) -> None:
    value = _results()
    _rows(value)[0]["release_date"] = 1719705600000
    path, digest = _write(tmp_path / "public.json", value)
    with pytest.raises(AnalysisError, match="keys must be exactly"):
        load_public_results(path, sha256=digest, shape=SHAPE)


def _frozen_policy(tmp_path: Path) -> LoadedPolicy:
    value = json.loads(DRAFT.read_text(encoding="utf-8"))
    value["frozen"] = True
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return load_policy(path)


def _lock(policies: dict[str, str]) -> str:
    return json.dumps({"schema_version": 1, "policies": policies})


def test_grades_are_refused_for_the_draft_policy(tmp_path: Path) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    # The draft policy is not frozen, so the check refuses it before it reads any lock.
    with pytest.raises(AnalysisError, match="not marked frozen; real replay refused"):
        load_public_grades(path, load_policy(DRAFT), sha256=digest, shape=SHAPE)


def test_grade_refusal_comes_before_the_file_is_read(tmp_path: Path) -> None:
    absent = tmp_path / "absent.json"
    with pytest.raises(AnalysisError, match="not marked frozen"):
        load_public_grades(absent, load_policy(DRAFT), sha256="0" * 64, shape=SHAPE)


def test_grades_are_refused_for_a_frozen_policy_without_a_committed_hash(tmp_path: Path) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    policy = _frozen_policy(tmp_path)
    with pytest.raises(AnalysisError, match="no committed hash"):
        load_public_grades(path, policy, lock_text=_lock({}), sha256=digest, shape=SHAPE)
    with pytest.raises(AnalysisError, match="hash mismatch"):
        load_public_grades(
            path, policy, lock_text=_lock({policy.key: "0" * 64}), sha256=digest, shape=SHAPE
        )


def test_grades_are_the_raw_pass_at_1_values_after_the_gate_passes(tmp_path: Path) -> None:
    path, digest = _write(tmp_path / "public.json", _results())
    policy = _frozen_policy(tmp_path)
    grades = load_public_grades(
        path, policy, lock_text=_lock({policy.key: policy.sha256}), sha256=digest, shape=SHAPE
    )
    # Synthetic values 25 * (model position + question position); no grade rule applied.
    assert grades == {
        "Model-A": {"1873_A": 50.0, "3324": 75.0, "abc301_a": 25.0},
        "Model-B": {"1873_A": 25.0, "3324": 50.0, "abc301_a": 0.0},
    }


def test_grades_pass_the_same_validation_as_the_metadata(tmp_path: Path) -> None:
    value = _results()
    _rows(value).pop()
    path, digest = _write(tmp_path / "public.json", value)
    policy = _frozen_policy(tmp_path)
    with pytest.raises(AnalysisError, match="missing cell"):
        load_public_grades(
            path, policy, lock_text=_lock({policy.key: policy.sha256}), sha256=digest, shape=SHAPE
        )


def _fp(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _public(tmp_path: Path) -> PublicResults:
    path, digest = _write(tmp_path / "public.json", _results())
    return load_public_results(path, sha256=digest, shape=SHAPE)


# The pinned dataset rows: identifier, platform, and question text.
DATASET_ROWS = (
    DatasetQuestion("abc301_a", "atcoder", question_fingerprint("Print A.\r\n")),
    DatasetQuestion("1873_A", "codeforces", question_fingerprint("  Sort B.\n")),
    DatasetQuestion("3324", "leetcode", question_fingerprint("Count C.")),
    DatasetQuestion("abc999_z", "atcoder", question_fingerprint("Not in the panel.")),
)
PANEL = {0: _fp("Count C."), 1: _fp("Print A."), 2: _fp("Sort B.")}


def test_fingerprint_normalizes_line_ends_and_outer_space() -> None:
    assert question_fingerprint("a\r\nb\rc\n  ") == _fp("a\nb\nc")
    assert question_fingerprint("  x ") == _fp("x")


def test_mapping_joins_each_panel_question_to_its_public_identifier(tmp_path: Path) -> None:
    mapped = map_panel_questions(PANEL, DATASET_ROWS, _public(tmp_path), expected=3)
    assert mapped == (
        MappedQuestion(0, _fp("Count C."), "3324"),
        MappedQuestion(1, _fp("Print A."), "abc301_a"),
        MappedQuestion(2, _fp("Sort B."), "1873_A"),
    )


def test_mapping_names_each_panel_question_without_a_match(tmp_path: Path) -> None:
    panel = {**PANEL, 3: _fp("Lost D."), 4: _fp("Lost E.")}
    with pytest.raises(AnalysisError, match="2 of 5 reference questions have no match") as raised:
        map_panel_questions(panel, DATASET_ROWS, _public(tmp_path), expected=5)
    message = str(raised.value)
    assert f"index 3 (fingerprint {_fp('Lost D.')})" in message
    assert f"index 4 (fingerprint {_fp('Lost E.')})" in message


def test_mapping_names_each_match_that_is_not_in_the_public_results(tmp_path: Path) -> None:
    panel = {**PANEL, 3: _fp("Not in the panel.")}
    with pytest.raises(AnalysisError, match="not in the public results") as raised:
        map_panel_questions(panel, DATASET_ROWS, _public(tmp_path), expected=4)
    assert "index 3 (question abc999_z)" in str(raised.value)


def test_mapping_requires_the_expected_number_of_reference_questions(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="3 reference questions, expected 315"):
        map_panel_questions(PANEL, DATASET_ROWS, _public(tmp_path), expected=315)


def test_mapping_rejects_a_fingerprint_that_appears_twice_in_the_dataset(tmp_path: Path) -> None:
    rows = (*DATASET_ROWS, DatasetQuestion("abc302_a", "atcoder", _fp("Print A.")))
    with pytest.raises(AnalysisError, match=r"index 1 .* matches 2 dataset questions"):
        map_panel_questions(PANEL, rows, _public(tmp_path), expected=3)


def test_mapping_rejects_two_panel_questions_with_one_fingerprint(tmp_path: Path) -> None:
    panel = {**PANEL, 3: _fp("Print A.")}
    with pytest.raises(AnalysisError, match="indexes 1 and 3 share one fingerprint"):
        map_panel_questions(panel, DATASET_ROWS, _public(tmp_path), expected=4)


def test_mapping_rejects_a_platform_that_differs_from_the_public_results(tmp_path: Path) -> None:
    rows = (DatasetQuestion("3324", "atcoder", _fp("Count C.")), *DATASET_ROWS[:2])
    with pytest.raises(AnalysisError, match="platform") as raised:
        map_panel_questions(PANEL, rows, _public(tmp_path), expected=3)
    assert "index 0 (question 3324)" in str(raised.value)


def _panel_file(tmp_path: Path, panel: dict[int, str]) -> Path:
    tasks = [
        {"index": index, "question_sha256": fingerprint, "scores": {"m": 1}}
        for index, fingerprint in sorted(panel.items())
    ]
    path = tmp_path / "lcb-reference-panel.json"
    path.write_text(json.dumps({"schema_version": 1, "tasks": tasks}), encoding="utf-8")
    return path


def _mapping_file(tmp_path: Path, panel_path: Path, **changes: Any) -> Path:
    mapped = map_panel_questions(PANEL, DATASET_ROWS, _public(tmp_path), expected=3)
    document = json.loads(mapping_document(mapped, panel_sha256=_sha(panel_path)))
    document.update(changes)
    path = tmp_path / "lcb-public-mapping.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_panel_fingerprints_reads_index_and_fingerprint(tmp_path: Path) -> None:
    assert panel_fingerprints(_panel_file(tmp_path, PANEL)) == PANEL


def test_mapping_entries_hold_index_fingerprint_and_identifier_only(tmp_path: Path) -> None:
    mapped = map_panel_questions(PANEL, DATASET_ROWS, _public(tmp_path), expected=3)
    document = json.loads(mapping_document(mapped, panel_sha256="a" * 64))
    assert document["questions"][0] == {
        "index": 0,
        "question_id": "3324",
        "question_sha256": _fp("Count C."),
    }
    assert {frozenset(entry) for entry in document["questions"]} == {
        frozenset({"index", "question_id", "question_sha256"})
    }
    assert document["public_sha256"] == PINNED_SOURCE.sha256
    assert document["panel_sha256"] == "a" * 64
    assert (document["dataset"], document["dataset_revision"]) == (
        "marianna13/livecodebench_code_generation_lite_parquet",
        "e70df9620dd54c12afac5e2881355de6f9ece2e9",
    )


def test_mapping_document_bytes_are_stable_lf_json(tmp_path: Path) -> None:
    mapped = map_panel_questions(PANEL, DATASET_ROWS, _public(tmp_path), expected=3)
    data = mapping_document(mapped, panel_sha256="a" * 64)
    assert data == mapping_document(tuple(reversed(mapped)), panel_sha256="a" * 64)
    assert data.endswith(b"}\n")
    assert b"\r" not in data


def test_mapping_round_trip_checks_the_panel(tmp_path: Path) -> None:
    panel_path = _panel_file(tmp_path, PANEL)
    mapping = _mapping_file(tmp_path, panel_path)
    assert load_mapping(mapping, panel_path=panel_path, expected=3) == (
        MappedQuestion(0, _fp("Count C."), "3324"),
        MappedQuestion(1, _fp("Print A."), "abc301_a"),
        MappedQuestion(2, _fp("Sort B."), "1873_A"),
    )


def test_mapping_load_rejects_another_panel(tmp_path: Path) -> None:
    panel_path = _panel_file(tmp_path, PANEL)
    mapping = _mapping_file(tmp_path, panel_path)
    panel_path.write_text(panel_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(AnalysisError, match="panel SHA-256"):
        load_mapping(mapping, panel_path=panel_path, expected=3)


def test_mapping_load_rejects_an_entry_that_differs_from_the_panel(tmp_path: Path) -> None:
    panel_path = _panel_file(tmp_path, PANEL)
    entries = [
        {"index": 0, "question_id": "3324", "question_sha256": _fp("Count C.")},
        {"index": 1, "question_id": "abc301_a", "question_sha256": _fp("Sort B.")},
        {"index": 2, "question_id": "1873_A", "question_sha256": _fp("Print A.")},
    ]
    mapping = _mapping_file(tmp_path, panel_path, questions=entries)
    with pytest.raises(AnalysisError, match="index 1 has another fingerprint"):
        load_mapping(mapping, panel_path=panel_path, expected=3)


def test_mapping_load_rejects_a_repeated_question_identifier(tmp_path: Path) -> None:
    panel_path = _panel_file(tmp_path, PANEL)
    document = json.loads(_mapping_file(tmp_path, panel_path).read_text(encoding="utf-8"))
    document["questions"][2]["question_id"] = "3324"
    mapping = tmp_path / "repeated.json"
    mapping.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AnalysisError, match="question 3324 appears 2 times"):
        load_mapping(mapping, panel_path=panel_path, expected=3)


@pytest.mark.parametrize(
    ("key", "setting", "message"),
    [
        ("schema_version", 2, "schema_version must be 1"),
        ("public_sha256", "0" * 64, "public SHA-256"),
        ("dataset_revision", "main", "dataset"),
        ("extra", 1, "keys must be exactly"),
    ],
)
def test_mapping_load_rejects_another_header(
    tmp_path: Path, key: str, setting: object, message: str
) -> None:
    panel_path = _panel_file(tmp_path, PANEL)
    mapping = _mapping_file(tmp_path, panel_path, **{key: setting})
    with pytest.raises(AnalysisError, match=message):
        load_mapping(mapping, panel_path=panel_path, expected=3)


def test_committed_mapping_joins_all_315_panel_questions() -> None:
    mapped = load_mapping(COMMITTED_MAPPING, panel_path=COMMITTED_PANEL)
    assert len(mapped) == 315
    assert len({item.question_id for item in mapped}) == 315
    assert [item.index for item in mapped] == sorted(panel_fingerprints(COMMITTED_PANEL))
