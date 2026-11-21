"""Tests for check_links.check_markdown. A fake fetch keeps the tests off the network."""

from pathlib import Path

from check_links import check_markdown


def no_network(url: str) -> int:
    raise AssertionError(f"unexpected fetch of {url}")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_relative_link_to_missing_file_is_broken(tmp_path: Path) -> None:
    write(tmp_path / "guide.md", "# Guide\n")
    readme = write(tmp_path / "README.md", "See [guide](guide.md).\nSee [gone](gone.md).\n")

    broken = check_markdown(readme, no_network)

    assert [(b.line, b.target) for b in broken] == [(2, "gone.md")]


def test_relative_link_with_encoded_spaces_finds_the_file(tmp_path: Path) -> None:
    write(tmp_path / "sample" / "Model A profile 1.xlsx", "")
    readme = write(tmp_path / "README.md", "[workbook](sample/Model%20A%20profile%201.xlsx)\n")

    assert check_markdown(readme, no_network) == []


def test_same_file_anchor_must_match_a_heading(tmp_path: Path) -> None:
    readme = write(
        tmp_path / "README.md",
        "# Performance & Quality Lab\n"
        "## Use `uv run` (v2), then *check*\n"
        "## Use `uv run` (v2), then *check*\n"
        "[a](#performance--quality-lab)\n"
        "[b](#use-uv-run-v2-then-check)\n"
        "[c](#use-uv-run-v2-then-check-1)\n"
        "[d](#no-such-heading)\n",
    )

    broken = check_markdown(readme, no_network)

    assert [(b.line, b.target) for b in broken] == [(7, "#no-such-heading")]


def test_cross_file_anchor_must_match_a_heading_in_that_file(tmp_path: Path) -> None:
    write(tmp_path / "task2" / "README.md", "# Benchmark\n## Token cost\n")
    readme = write(
        tmp_path / "docs" / "guide.md",
        "[a](../task2/README.md#token-cost)\n[b](../task2/README.md#benchmark-data)\n",
    )

    broken = check_markdown(readme, no_network)

    assert [(b.line, b.target, b.reason) for b in broken] == [
        (2, "../task2/README.md#benchmark-data", "heading does not exist")
    ]


def test_external_urls_use_fetch_and_fail_on_error_status(tmp_path: Path) -> None:
    statuses = {
        "https://example.com/ok": 200,
        "https://github.com/owner/private-repo": 404,
        "https://example.com/bare": 200,
    }
    fetched: list[str] = []

    def fake_fetch(url: str) -> int:
        fetched.append(url)
        if url == "https://down.example.com/":
            raise OSError("connection refused")
        return statuses[url]

    readme = write(
        tmp_path / "README.md",
        "[ok](https://example.com/ok) and [again](https://example.com/ok)\n"
        "- **Runner:** [repo](https://github.com/owner/private-repo). It is private.\n"
        "Bare https://example.com/bare, and <https://down.example.com/>.\n"
        "Local [dev server](http://127.0.0.1:5173) and http://localhost:8000/health.\n",
    )

    broken = check_markdown(readme, fake_fetch)

    assert [(b.line, b.target, b.reason) for b in broken] == [
        (2, "https://github.com/owner/private-repo", "HTTP 404"),
        (3, "https://down.example.com/", "connection refused"),
    ]
    assert sorted(fetched) == sorted(set(fetched)), "each URL is fetched once"


def test_code_is_not_a_link_and_not_a_heading(tmp_path: Path) -> None:
    readme = write(
        tmp_path / "README.md",
        "# Real heading\n"
        "```powershell\n"
        "# install step\n"
        "curl https://not-fetched.example.com/ [x](missing.md)\n"
        "```\n"
        "~~~\n"
        "[y](missing-too.md)\n"
        "~~~\n"
        "Run `[z](missing-three.md)` and `https://also-not-fetched.example.com`.\n"
        "[ok](#real-heading) [bad](#install-step)\n",
    )

    broken = check_markdown(readme, no_network)

    assert [(b.line, b.target) for b in broken] == [(10, "#install-step")]


def test_url_with_balanced_parentheses_keeps_the_whole_target(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fake_fetch(url: str) -> int:
        fetched.append(url)
        return 200

    readme = write(tmp_path / "README.md", "[fish](https://en.wikipedia.org/wiki/Fish_(food)).\n")

    assert check_markdown(readme, fake_fetch) == []
    assert fetched == ["https://en.wikipedia.org/wiki/Fish_(food)"]


def test_link_with_a_title_is_checked(tmp_path: Path) -> None:
    readme = write(
        tmp_path / "README.md", "[t](missing.md \"Title\") and [u](gone.md 'Other title')\n"
    )

    broken = check_markdown(readme, no_network)

    assert [b.target for b in broken] == ["missing.md", "gone.md"]


def test_bare_url_in_bold_or_italic_drops_the_emphasis_marks(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fake_fetch(url: str) -> int:
        fetched.append(url)
        return 200

    readme = write(
        tmp_path / "README.md", "See **https://example.com/b** and _https://example.com/i_.\n"
    )

    assert check_markdown(readme, fake_fetch) == []
    assert fetched == ["https://example.com/b", "https://example.com/i"]


def test_anchor_is_checked_only_in_markdown_files(tmp_path: Path) -> None:
    write(tmp_path / "app.py", "print(1)\n")
    write(tmp_path / "sub" / "notes.md", "# Notes\n")
    readme = write(
        tmp_path / "README.md", "[line](app.py#L1) [folder](sub#x) [gone](sub/notes.md#x)\n"
    )

    broken = check_markdown(readme, no_network)

    assert [b.target for b in broken] == ["sub/notes.md#x"]


def test_letter_case_of_a_relative_path_must_match(tmp_path: Path) -> None:
    write(tmp_path / "Docs" / "Guide.md", "# Guide\n")
    write(tmp_path / "sub" / "x.md", "")
    readme = write(
        tmp_path / "sub" / "README.md",
        "[ok](../Docs/Guide.md) [file](../Docs/guide.md) "
        "[folder](../docs/Guide.md) [here](./x.md)\n",
    )

    broken = check_markdown(readme, no_network)

    assert [b.target for b in broken] == ["../Docs/guide.md", "../docs/Guide.md"]
