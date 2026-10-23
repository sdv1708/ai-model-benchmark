"""Render the canonical Handout A Markdown as a readable single-page PDF.

Documentation-only dependencies: reportlab and pypdf (Codex bundled runtime).
Run from any directory: python docs/scripts/render_handout_a.py
No benchmark, application dependency, or evidence file is modified.
"""

import re
from html import escape
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "task2/HANDOUT_A.md"
OUTPUT = ROOT / "output/pdf/handout-a.pdf"
REPO = "https://github.com/sdv1708/ai-model-quality-challenge"


def inline(text: str) -> str:
    """Map this document's bold and relative links to PDF paragraph markup."""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    def link(match: re.Match[str]) -> str:
        label, relative = match.groups()
        target = (SOURCE.parent / relative).resolve()
        path = target.relative_to(ROOT).as_posix()
        if not target.is_file():
            raise ValueError(f"Missing handout evidence: {relative}")
        return f'<link href="{REPO}/blob/main/{path}" color="#14605e">{label}</link>'

    return re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, text)


def main() -> None:
    blocks = SOURCE.read_text(encoding="utf-8").strip().split("\n\n")
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=colors.HexColor("#15344a"),
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#526572"),
            spaceAfter=8,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#14605e"),
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10.2,
            leading=12.7,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1b2833"),
            spaceAfter=2,
        ),
        "evidence": ParagraphStyle(
            "evidence",
            fontName="Helvetica",
            fontSize=8.5,
            leading=10.5,
            textColor=colors.HexColor("#526572"),
            spaceBefore=7,
        ),
    }
    story = []
    for index, block in enumerate(blocks):
        if block.startswith("# "):
            kind, block = "title", block[2:]
        elif block.startswith("## "):
            kind, block = "heading", block[3:]
        elif index == 1:
            kind = "subtitle"
        elif block.startswith("Evidence:"):
            kind = "evidence"
        else:
            kind = "body"
        story.append(Paragraph(inline(block), styles[kind]))
    story.append(Spacer(1, 2))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    staged = OUTPUT.with_suffix(".pending.pdf")
    try:
        SimpleDocTemplate(
            str(staged),
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=30,
            bottomMargin=30,
            title="Handout A - Why this works",
            author="AI Model Quality Challenge",
            invariant=1,
        ).build(story)
        reader = PdfReader(staged)
        if len(reader.pages) != 1:
            raise ValueError(f"Handout must be one readable page; got {len(reader.pages)}")
        text = reader.pages[0].extract_text()
        if "Assumptions and what would change" not in text or "primary research" not in text:
            raise ValueError("Handout content is incomplete")
        staged.replace(OUTPUT)
    finally:
        staged.unlink(missing_ok=True)
    print(f"Created {OUTPUT}: one A4 page, 10.2 pt body text")


if __name__ == "__main__":
    main()
