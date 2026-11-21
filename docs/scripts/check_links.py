"""Check the links in Markdown files, as a reader who is not signed in.

The check reads inline links, autolinks, and bare URLs outside code.
A relative link must point to a file that exists, with the same letter case.
An anchor on a Markdown file must match a heading in that file.
The check sends a GET request to each external link, with no credentials and no cookies.
An external link must return an HTTP status below 400.
The check skips links to local hosts: localhost, 127.0.0.1, ::1, 0.0.0.0, and *.localhost.

Run from the repository root:
    uv run --no-project --python 3.12 python docs/scripts/check_links.py README.md

Exit code 0 means that every link works.
Exit code 1 means that at least one link is broken.
"""

import argparse
import functools
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

# A link target can hold one level of balanced parentheses, as in GitHub Markdown.
# An optional title in double or single quotes can follow the target.
INLINE_LINK = re.compile(r"""\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+"[^"]*"|\s+'[^']*')?\)""")
AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
BARE_URL = re.compile(r"https?://[^\s<>()\[\]\"'`|]+")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
USER_AGENT = "readme-link-check/1.0"
RETRY_STATUSES = {429, 500, 502, 503, 504}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")


@dataclass(frozen=True)
class BrokenLink:
    source: Path
    line: int
    target: str
    reason: str


def prose_lines(path: Path) -> Iterator[tuple[int, str]]:
    """Yield the number and text of each line that is outside a fenced code block."""
    fence = ""
    for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = FENCE.match(text)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = ""
        elif match:
            fence = match.group(1)
        else:
            yield number, text


def heading_anchors(path: Path) -> set[str]:
    """Return the anchors that GitHub makes for the headings in a Markdown file."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for _, text in prose_lines(path):
        match = HEADING.match(text)
        if match is None:
            continue
        title = LINK_TEXT.sub(r"\1", match.group(1)).lower()
        slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def blank(pattern: re.Pattern[str], text: str) -> str:
    """Replace each match with spaces, so the positions of the other characters stay the same."""
    return pattern.sub(lambda match: " " * len(match.group(0)), text)


def link_targets(text: str) -> Iterator[str]:
    """Yield each link target in one line, in the order of the line."""
    found: list[tuple[int, str]] = []
    rest = text
    for pattern in (INLINE_LINK, AUTOLINK):
        for match in pattern.finditer(rest):
            found.append((match.start(), match.group(1)))
        rest = blank(pattern, rest)
    for match in BARE_URL.finditer(rest):
        found.append((match.start(), match.group(0).rstrip(".,;:!?*_")))
    for _, target in sorted(found):
        yield target


def is_local(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def check_markdown(path: Path, fetch: Callable[[str], int]) -> list[BrokenLink]:
    """Return every broken link in a Markdown file.

    `fetch` takes a URL and returns the final HTTP status. It raises OSError on a network error.
    """
    broken: list[BrokenLink] = []

    @functools.cache
    def url_problem_once(url: str) -> str | None:
        return url_problem(url, fetch)

    for number, text in prose_lines(path):
        for target in link_targets(blank(CODE_SPAN, text)):
            reason = link_problem(path, target, url_problem_once)
            if reason is not None:
                broken.append(BrokenLink(path, number, target, reason))
    return broken


def link_problem(
    path: Path, target: str, url_problem_once: Callable[[str], str | None]
) -> str | None:
    """Return the reason that one link target is broken, or None if it works."""
    if target.startswith(("http://", "https://")):
        return None if is_local(target) else url_problem_once(target)
    if target.startswith("mailto:"):
        return None
    file_part, _, anchor = target.partition("#")
    linked = path.parent / unquote(file_part) if file_part else path
    if not linked.exists():
        return "file does not exist"
    if file_part and not case_matches(path.parent, Path(unquote(file_part))):
        return "letter case does not match the file on disk"
    # GitHub gives other files line anchors such as #L10, so only Markdown anchors are checked.
    is_markdown = linked.is_file() and linked.suffix.lower() == ".md"
    if anchor and is_markdown and anchor not in heading_anchors(linked):
        return "heading does not exist"
    return None


def case_matches(base: Path, relative: Path) -> bool:
    """Return True if each name in `relative` has the same letter case as the name on disk.

    GitHub paths are case-sensitive. Windows and macOS paths usually are not.
    """
    current = base
    for name in relative.parts:
        if name not in (".", "..") and name not in os.listdir(current):
            return False
        current = current / name
    return True


def url_problem(url: str, fetch: Callable[[str], int]) -> str | None:
    """Return the reason that an external link is broken, or None if it works."""
    try:
        status = fetch(url)
    except OSError as error:
        return str(error)
    return f"HTTP {status}" if status >= 400 else None


def fetch_signed_out(url: str) -> int:
    """Return the final HTTP status of a GET request that sends no credentials and no cookies."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return int(response.status)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUSES or attempt == 2:
                return error.code
        time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Markdown files to check")
    args = parser.parse_args(argv)
    broken: list[BrokenLink] = []
    for path in args.files:
        broken.extend(check_markdown(path, fetch_signed_out))
    for link in broken:
        print(f"{link.source}:{link.line}: {link.target} ({link.reason})")
    print(f"{len(broken)} broken link(s) in {len(args.files)} file(s).")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
