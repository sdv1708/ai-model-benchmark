"""The "Frozen policy" block of the summary and the report."""

import copy
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from policy_fixtures import frozen_value, simulated_document, write_policy

from benchmark_reference.threshold_benchmarks import AA_LCR, LIVE_CODE_BENCH
from benchmark_reference.threshold_frozen_report import (
    console_lines,
    frozen_document,
    frozen_html,
)
from benchmark_reference.threshold_policy import LoadedPolicy, load_policy

LCB = LIVE_CODE_BENCH


def _loaded(tmp_path: Path, value: dict[str, Any] | None = None) -> LoadedPolicy:
    return load_policy(
        write_policy(tmp_path / "v1.json", frozen_value() if value is None else value)
    )


def _evidence(loaded: LoadedPolicy, sections: dict[str, Any] | None = None) -> dict[str, Any]:
    """Coverage and error-rate summaries of a run. By default they choose the frozen values."""
    value = frozen_value()
    evidence = {}
    for name, policy in loaded.benchmarks.items():
        section = (sections or value["benchmarks"])[name]
        document = simulated_document(name, section)
        evidence[name] = (policy, document["coverage"], document["error_rate"])
    return evidence


def test_a_draft_has_no_frozen_block(tmp_path: Path) -> None:
    loaded = load_policy(write_policy(tmp_path / "draft.json", {**frozen_value(), "frozen": False}))
    assert frozen_document(loaded, {}) is None
    assert console_lines(None) == ()


def test_the_block_holds_each_chosen_value_with_its_evidence(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    document = frozen_document(loaded, _evidence(loaded))
    assert document is not None
    assert (document["key"], document["sha256"]) == (loaded.key, loaded.sha256)
    assert document["thresholds"] == {LCB: 0.7, AA_LCR: 0.6}
    lcb = document["benchmarks"][0]
    assert lcb["benchmark"] == LCB
    assert lcb["interval_method"]["chosen"] == "pooled_exact_hypergeometric"
    assert lcb["interval_method"]["next_passing"]["mean_width"] == 0.2
    assert (lcb["probe"]["stratifier"], lcb["probe"]["stage_size"]) == (
        "difficulty_stratified",
        63,
    )
    assert lcb["probe"]["mean_cost_fraction"] == 0.4
    assert lcb["probe"]["next_passing"]["mean_cost_fraction"] == 0.5
    assert lcb["probe"]["same_choice_for_each_generator"] is True
    # The rules give the same values on the results of this run.
    assert lcb["recheck"]["matches"] is True
    assert document["rules_reproduced_on_this_run"] is True
    assert document["protocol"] == loaded.protocol


def test_a_run_whose_results_give_other_values_is_reported(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    sections = copy.deepcopy(frozen_value()["benchmarks"])
    sections[AA_LCR]["stratifier"] = "metadata_stratified"
    document = frozen_document(loaded, _evidence(loaded, sections))
    assert document is not None
    aa_lcr = document["benchmarks"][1]
    assert aa_lcr["recheck"]["matches"] is False
    assert aa_lcr["recheck"]["stratifier"] == "metadata_stratified"
    assert document["rules_reproduced_on_this_run"] is False
    html = frozen_html(document)
    assert "give different values" in html
    assert "Differs: pooled_exact_hypergeometric, metadata_stratified, 20 questions" in html
    assert any("rule on this run: differs" in line for line in console_lines(document))


def test_a_generator_that_alone_gives_another_probe_is_named(tmp_path: Path) -> None:
    value = frozen_value()
    candidates = value["selection"]["benchmarks"][LCB]["probe"]["candidates"]
    # A second probe is cheaper for Rasch alone, but dearer on the mean of both generators.
    candidates[0]["mean_cost_fraction"] = {"rasch": 0.39, "reference_flip": 0.42}
    loaded = _loaded(tmp_path, value)
    document = frozen_document(loaded, _evidence(loaded))
    assert document is not None
    probe = document["benchmarks"][0]["probe"]
    assert probe["same_choice_for_each_generator"] is False
    assert probe["choice_by_generator"]["rasch"]["stage_size"] != 63
    assert "The generators alone give different choices" in frozen_html(document)


def test_the_html_section_shows_every_part_of_the_frozen_policy(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    document = frozen_document(loaded, _evidence(loaded))
    assert document is not None
    html = frozen_html(document)
    assert html.startswith(
        '<section data-frozen-policy id="frozen-policy">\n<h2>Frozen policy</h2>'
    )
    assert f"<code data-frozen-sha256>{loaded.sha256}</code>" in html
    for part in (
        "<h3>Rules</h3>",
        "<h3>Chosen values</h3>",
        "<h3>Fixed values</h3>",
        "<h3>Pass criteria of the real replay</h3>",
        "<h3>Stated comparisons</h3>",
        "<h3>Pass criteria of the pruned-set test</h3>",
        "<h3>Disclosures</h3>",
        "The Neyman selector (#61) is deferred and\nis not a candidate.",
    ):
        assert part in html
    assert 'data-chosen="live_code_bench_v5-interval-method"' in html
    assert 'data-chosen="aa_lcr-probe"' in html
    assert re.search(r"Passes 4 of 4 coverage cells\s+with mean width 0\.100", html)
    assert "17f9a1d69e3f6290fc8b967a4dd13fbb46e34dd05716fdee793780a1cfadd0c1" in html
    assert "0 for the primary result, 0.02 as a secondary result" in html
    assert "0.30 to 0.90 in steps of 0.01" in html
    assert "0 to 999 for each model and threshold" in html
    assert "uses 211 questions at stage 1" in html
    assert "Fixed subsets of 95 and 158 questions, with 63 questions" in html
    assert "selection seed 42" in html
    assert html.count("<li>") >= 3 + 2 + 6
    real = re.search(r'<ol data-criteria="real-replay">(.*?)</ol>', html, re.S)
    pruned = re.search(r'<ol data-criteria="pruned-set">(.*?)</ol>', html, re.S)
    assert real is not None and real.group(1).count("<li>") == 3
    assert pruned is not None and pruned.group(1).count("<li>") == 6
    assert "at most 0.071" in real.group(1)
    assert "gap of 0.10 or more" in pruned.group(1)
    assert "The simulated d95 of the\nLiveCodeBench setting is 0.19." in html
    for name in ("reference_replay_seen", "public_panel_read", "ordering_criterion_change"):
        assert f'data-disclosure="{name}"' in html
    assert "Claude-3-Haiku" in html and "XBai-o4-medium" in html


def test_html_escapes_the_text_of_the_policy(tmp_path: Path) -> None:
    value = frozen_value()
    value["protocol"]["disclosures"]["public_panel_read"] = "Read <b>names</b> only."
    loaded = _loaded(tmp_path, value)
    document = frozen_document(loaded, _evidence(loaded))
    assert document is not None
    assert "Read &lt;b&gt;names&lt;/b&gt; only." in frozen_html(document)


def test_a_run_whose_grid_is_not_the_prior_cannot_recheck(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    evidence = _evidence(loaded)
    policy, coverage, error_rate = evidence[LCB]
    short = {**error_rate, "true_scores": [0.5, 0.6]}
    evidence[LCB] = (replace(policy, error_true_scores=(0.5, 0.6)), coverage, short)
    document = frozen_document(loaded, evidence)
    assert document is not None
    lcb = document["benchmarks"][0]
    assert lcb["recheck"]["available"] is False
    assert "0.30 to 0.90" in lcb["recheck"]["reason"]
    # Only the sections that the rules can check count toward the result.
    assert document["rules_reproduced_on_this_run"] is True
    assert "Not available: The cost rule needs" in frozen_html(document)
