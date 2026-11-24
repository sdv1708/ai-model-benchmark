"""The two judge prompts: the JSON prompt of #76, and the old one-word prompt of #88."""

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from judge_fixtures import MODELS, QUESTIONS, Scripted, scripted_judge, verdict, write_data

from benchmark_reference.judge_estimate import Estimate, Prices, build_estimate, load_estimate
from benchmark_reference.judge_items import JudgeInputs, load_judge_inputs
from benchmark_reference.judge_prompt import (
    JSON_CONTRACT,
    ONE_WORD,
    PromptVariant,
    prompt_sha256,
    render_prompt,
)
from benchmark_reference.judge_run import read_attempts, run_judge
from benchmark_reference.long_context_reporting import encode_json
from benchmark_reference.models import AnalysisError

ANSWERS = len(MODELS) * QUESTIONS
PRICES = Prices(Fraction("0.09"), Fraction("0.55"), "test prices", "2026-11-23")
QWEN = "Qwen/Qwen3-235B-A22B-Instruct-2507"
PAID_URL = "https://judge.invalid/v1"
ISSUES = "https://github.com/sdv1708/ai-model-benchmark/issues/"
RECORDED = Path(__file__).parents[2] / "docs" / "data" / "task2-aa-lcr-judge-estimate.json"


@pytest.fixture
def inputs(tmp_path: Path) -> JudgeInputs:
    data = write_data(tmp_path)
    return load_judge_inputs(panel_path=data.panel, data_root=data.root, source_csv=data.csv)


def _estimate(inputs: JudgeInputs, url: str, variant: PromptVariant, **changes: Any) -> Estimate:
    settings: dict[str, Any] = {
        "judge_model": QWEN,
        "prices": PRICES,
        "limit_usd": Fraction(10),
        "variant": variant,
        **changes,
    }
    return load_estimate(build_estimate(inputs, base_url=url, **settings))


# The prompt and the parser


def test_the_one_word_prompt_is_the_json_prompt_with_no_contract() -> None:
    values = {"question": "Q {x}?", "reference": "R", "answer": " A {y}"}
    one_word = ONE_WORD.render(**values)
    assert one_word == (
        "Assess whether the following CANDIDATE ANSWER is CORRECT or INCORRECT. For the "
        "CANDIDATE ANSWER to be correct, it must be consistent with the OFFICIAL ANSWER.\n\n"
        "The question, for reference only: Q {x}?\n"
        "The OFFICIAL ANSWER: R\n"
        "CANDIDATE ANSWER TO ASSESS:  A {y}\n\n"
        "Reply only with CORRECT or INCORRECT."
    )
    assert JSON_CONTRACT.render(**values) == render_prompt(**values)
    assert JSON_CONTRACT.render(**values).startswith(one_word + "\n\nReply with a single JSON")


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("CORRECT", "CORRECT"),
        (" correct.\n", "CORRECT"),
        ("INCORRECT", "INCORRECT"),
        ("Incorrect", "INCORRECT"),
        ("The answer is CORRECT", "CORRECT"),
        # The old parser reads the word only, so it does not see the negation.
        ("NOT CORRECT", "CORRECT"),
        ("INCORRECT, not CORRECT", "CORRECT"),
        ("CORRECTLY", "INCORRECT"),
        ("I cannot tell", "INCORRECT"),
        ("", None),
        (" \n", None),
    ],
)
def test_the_one_word_parser_reads_the_word_and_rejects_an_empty_reply(
    reply: str, expected: str | None
) -> None:
    assert ONE_WORD.parse(reply).verdict == expected


# The estimate


def test_the_estimate_records_the_prompt_variant_and_its_settings(inputs: JudgeInputs) -> None:
    estimate = _estimate(inputs, PAID_URL, ONE_WORD)
    document = estimate.document
    assert (estimate.variant, document["issue"]) == (ONE_WORD, ISSUES + "88")
    assert (estimate.temperature, estimate.max_tokens) == (0.0, 1024)
    prompt = document["prompt"]
    assert (prompt["variant"], prompt["tag"]) == ("one-word", "v1.4.2")
    assert prompt["source"] == "https://github.com/modelscope/evalscope"
    assert prompt["files"] == [
        "evalscope/benchmarks/aa_lcr/aa_lcr_adapter.py",
        "evalscope/metrics/llm_judge.py",
    ]
    assert document["tokens"]["expected"]["output"] == ANSWERS * 5 * 3
    json_prompt = _estimate(inputs, PAID_URL, JSON_CONTRACT)
    assert (json_prompt.variant, json_prompt.max_tokens) == (JSON_CONTRACT, 4096)
    assert json_prompt.document["issue"] == ISSUES + "76"
    assert json_prompt.prompts_sha256 != estimate.prompts_sha256


def test_the_estimate_of_76_has_no_variant_and_still_loads() -> None:
    estimate = load_estimate(RECORDED.read_bytes())
    assert "variant" not in estimate.document["prompt"]
    assert (estimate.variant, estimate.max_tokens) == (JSON_CONTRACT, 4096)


def test_an_estimate_with_another_variant_or_issue_is_refused(inputs: JudgeInputs) -> None:
    document = json.loads(json.dumps(_estimate(inputs, PAID_URL, ONE_WORD).document))
    unknown = {**document, "prompt": {**document["prompt"], "variant": "two-words"}}
    with pytest.raises(AnalysisError, match="unknown judge prompt"):
        load_estimate(encode_json(unknown))
    with pytest.raises(AnalysisError, match="names the issue"):
        load_estimate(encode_json({**document, "issue": ISSUES + "76"}))


@pytest.mark.parametrize("variant", [ONE_WORD, JSON_CONTRACT])
@pytest.mark.parametrize(
    ("section", "change"),
    [
        ("judge", {"max_tokens": 512}),
        ("judge", {"temperature": 0.7}),
        ("prompt", {"commit": "0"}),
        ("prompt", {"tag": "v9"}),
        ("prompt", {"files": []}),
        ("prompt", {"source": "https://example.com"}),
    ],
)
def test_an_estimate_must_have_the_settings_of_its_prompt(
    inputs: JudgeInputs, variant: PromptVariant, section: str, change: dict[str, Any]
) -> None:
    document = json.loads(json.dumps(_estimate(inputs, PAID_URL, variant).document))
    document[section].update(change)
    with pytest.raises(AnalysisError, match="settings of its prompt"):
        load_estimate(encode_json(document))


# The run


def test_a_one_word_run_sends_the_old_prompt_and_settings(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    with scripted_judge(lambda _prompt, _n: Scripted("CORRECT")) as judge:
        estimate = _estimate(inputs, judge.url, ONE_WORD)
        result = run_judge(estimate, inputs, run_dir=tmp_path / "run", key=None, approval_url=None)
    assert (result.complete, result.judgments) == (True, ANSWERS * 5)
    prompts = {item.prompt for item in inputs.for_variant(ONE_WORD).items}
    assert judge.seen == dict.fromkeys(prompts, 5)
    assert all(p.endswith("\n\nReply only with CORRECT or INCORRECT.") for p in prompts)
    for body in judge.bodies:
        assert set(body) == {"model", "messages", "temperature", "max_tokens"}
        assert (body["temperature"], body["max_tokens"]) == (0.0, 1024)
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    assert {a["prompt_sha256"] for a in attempts} == {prompt_sha256(p) for p in prompts}
    assert {(a["reply"], a["verdict"]) for a in attempts} == {("CORRECT", "CORRECT")}


def test_a_fault_or_an_empty_reply_never_becomes_incorrect(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    def script(_prompt: str, number: int) -> Scripted:
        return {1: Scripted(""), 2: Scripted(status=503)}.get(number, Scripted("INCORRECT"))

    with scripted_judge(script) as judge:
        result = run_judge(
            _estimate(inputs, judge.url, ONE_WORD),
            inputs,
            run_dir=tmp_path / "run",
            key=None,
            approval_url=None,
            sleep=lambda _seconds: None,
        )
    assert result.complete
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    assert {(a["status"], a["verdict"]) for a in attempts} == {
        ("parse_error", None),
        ("transport_error", None),
        ("success", "INCORRECT"),
    }


@pytest.mark.parametrize(
    "fault",
    [
        Scripted("upstream fault", error={"message": "secret echo", "code": 502}),
        Scripted("upstream fault", error="secret echo"),
        Scripted("upstream fault", finish_reason="error"),
    ],
)
def test_a_reply_that_carries_an_error_is_not_a_verdict(
    inputs: JudgeInputs, tmp_path: Path, fault: Scripted
) -> None:
    """The old parser reads any text, so an error text must not reach it."""
    with scripted_judge(lambda _prompt, _n: fault) as judge:
        result = run_judge(
            _estimate(inputs, judge.url, ONE_WORD),
            inputs,
            run_dir=tmp_path / "run",
            key=None,
            approval_url=None,
            max_new_requests=3,
            sleep=lambda _seconds: None,
        )
    assert result.judgments == 0 and result.cost_bound > 0
    attempts = read_attempts(tmp_path / "run" / "judgments.jsonl")
    assert {(a["status"], a["verdict"]) for a in attempts} == {("transport_error", None)}
    assert all(a["error"] for a in attempts)
    assert "secret echo" not in (tmp_path / "run" / "judgments.jsonl").read_text(encoding="utf-8")


def test_a_null_error_field_is_not_a_fault(inputs: JudgeInputs, tmp_path: Path) -> None:
    raw = {
        "id": "x",
        "error": None,
        "choices": [{"message": {"content": "INCORRECT"}, "finish_reason": "stop"}],
    }
    reply = Scripted(raw=json.dumps(raw).encode("utf-8"))
    with scripted_judge(lambda _prompt, _n: reply) as judge:
        estimate = _estimate(inputs, judge.url, ONE_WORD)
        run = {"run_dir": tmp_path / "run", "key": None, "approval_url": None}
        options: dict[str, Any] = {**run, "max_new_requests": 1}
        assert run_judge(estimate, inputs, **options).judgments == 1


def test_a_paid_run_needs_a_comment_on_the_issue_of_its_prompt(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    for variant, number in ((ONE_WORD, "76"), (JSON_CONTRACT, "88")):
        with pytest.raises(AnalysisError, match="approval-url"):
            run_judge(
                _estimate(inputs, PAID_URL, variant),
                inputs,
                run_dir=tmp_path / "run",
                key="test-key",
                approval_url=f"{ISSUES}{number}#issuecomment-1",
            )
    assert not (tmp_path / "run").exists()


def test_a_run_writes_no_settings_into_a_folder_that_another_run_holds(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    """The other run has the lock, and it has not written its settings yet."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.lock").touch()
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        estimate = _estimate(inputs, judge.url, ONE_WORD)
        with pytest.raises(AnalysisError, match="Another run"):
            run_judge(estimate, inputs, run_dir=run, key=None, approval_url=None)
    assert [p.name for p in run.iterdir()] == ["run.lock"]


def test_a_refused_run_keeps_the_settings_and_leaves_no_lock(
    inputs: JudgeInputs, tmp_path: Path
) -> None:
    run = tmp_path / "run"
    options: dict[str, Any] = {"run_dir": run, "key": None, "approval_url": None}
    with scripted_judge(lambda _prompt, _n: verdict(True)) as judge:
        first = _estimate(inputs, judge.url, JSON_CONTRACT)
        run_judge(first, inputs, max_new_requests=1, **options)
        before = (run / "run.json").read_bytes()
        with pytest.raises(AnalysisError, match="another estimate"):
            run_judge(_estimate(inputs, judge.url, ONE_WORD), inputs, **options)
    assert (run / "run.json").read_bytes() == before
    assert not (run / "run.lock").exists()
