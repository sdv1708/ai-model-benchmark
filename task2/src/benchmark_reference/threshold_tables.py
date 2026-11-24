"""Table and number formats that the recorded reports of the threshold policy share."""

import csv
import io
from collections.abc import Sequence
from fractions import Fraction


def rounded(value: Fraction | float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def csv_table(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def markdown_table(head: Sequence[str], rows: Sequence[Sequence[object]], *, text: int = 1) -> str:
    """A Markdown table. The first ``text`` columns align left, the others right."""
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" if i < text else "---:" for i in range(len(head))) + " |",
    ]
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def optional(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"
