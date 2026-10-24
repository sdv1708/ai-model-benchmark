"""Render canonical Handout B within the top half of one A4 page.

Documentation-only dependencies: ReportLab and pypdf (bundled runtime).
Run from any directory: python docs/scripts/render_handout_b.py
"""

import re
from html import escape
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Preformatted,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "task2/HANDOUT_B.md"
OUTPUT = ROOT / "output/pdf/handout-b.pdf"
REPO = "https://github.com/sdv1708/ai-model-benchmark"
MARGIN = 30


def inline(value: str) -> str:
    """Translate this handout's bold and verified local links into PDF markup."""
    value = escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)

    def link(match: re.Match[str]) -> str:
        label, relative = match.groups()
        target = (SOURCE.parent / relative).resolve()
        path = target.relative_to(ROOT).as_posix()
        if not target.is_file():
            raise ValueError(f"Missing handout evidence: {relative}")
        return f'<link href="{REPO}/blob/main/{path}" color="#14605e">{label}</link>'

    return re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, value)


def main() -> None:
    width, height = A4
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#15344a"),
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#526572"),
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=9.5,
            leading=11.5,
            textColor=colors.HexColor("#1b2833"),
            spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "code",
            fontName="Courier",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#15344a"),
            spaceAfter=7,
        ),
        "evidence": ParagraphStyle(
            "evidence",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#526572"),
            spaceAfter=0,
        ),
    }
    story = []
    blocks = SOURCE.read_text(encoding="utf-8").strip().split("\n\n")
    for index, block in enumerate(blocks):
        if block.startswith("```powershell\n") and block.endswith("\n```"):
            code = block.removeprefix("```powershell\n").removesuffix("\n```")
            for line in code.splitlines():
                if len(line) * 8 * 0.6 > width - 2 * MARGIN:
                    raise ValueError("Command exceeds the readable page width")
            story.append(Preformatted(code, styles["code"]))
            continue
        if block.startswith("# "):
            kind, block = "title", block[2:]
        elif index == 1:
            kind = "subtitle"
        elif block.startswith("Evidence:"):
            kind = "evidence"
        else:
            kind = "body"
        story.append(Paragraph(inline(block), styles[kind]))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    staged = OUTPUT.with_suffix(".pending.pdf")
    try:
        doc = BaseDocTemplate(
            str(staged),
            pagesize=A4,
            title="Handout B - Why this matters and how to use it",
            author="AI Model Quality Challenge",
            invariant=1,
        )
        # A physical half-page constraint, not just a one-page or word-count check.
        frame = Frame(
            MARGIN,
            height / 2 + 12,
            width - 2 * MARGIN,
            height / 2 - MARGIN - 12,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        doc.addPageTemplates(PageTemplate(id="half-page", frames=[frame]))
        doc.build(story)
        reader = PdfReader(staged)
        if len(reader.pages) != 1:
            raise ValueError(f"Handout exceeds half a page: {len(reader.pages)} pages")
        text = reader.pages[0].extract_text()
        if "Why a PM cares" not in text or "visual probe and limits" not in text:
            raise ValueError("Handout content is incomplete")
        staged.replace(OUTPUT)
    finally:
        staged.unlink(missing_ok=True)
    print(f"Created {OUTPUT}: top half of A4, 9.5 pt body text")


if __name__ == "__main__":
    main()
