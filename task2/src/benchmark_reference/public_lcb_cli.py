"""Fetch, check, and map the public LiveCodeBench results. No command prints a grade.

- ``fetch`` downloads the public file to a Git-ignored location. It stops when the
  SHA-256 differs from the pinned value.
- ``check`` validates the downloaded file and prints its shape.
- ``map`` joins the 315 reference-panel questions to public question identifiers.
  It needs the ``public-source`` extra and internet access.
"""

import argparse
import hashlib
from collections.abc import Sequence
from pathlib import Path

from benchmark_reference import public_lcb
from benchmark_reference.models import AnalysisError
from benchmark_reference.reporting import write_atomic


def _fetch(args: argparse.Namespace) -> str:
    source = public_lcb.PINNED_SOURCE
    digest = public_lcb.fetch_source(args.output, source=source, download=public_lcb.download_url)
    return (
        f"Fetched {source.size:,} bytes from {source.url}; SHA-256 {digest} matches the pin. "
        f"Saved to {args.output}"
    )


def _load(path: Path) -> public_lcb.PublicResults:
    return public_lcb.load_public_results(
        path, sha256=public_lcb.PINNED_SOURCE.sha256, shape=public_lcb.RECORDED_SHAPE
    )


def _check(args: argparse.Namespace) -> str:
    results = _load(args.source)
    cells = len(results.models) * len(results.questions)
    return (
        f"Public LiveCodeBench file {args.source}: {len(results.models)} models, "
        f"{len(results.questions):,} questions, {cells:,} cells, no missing cell. "
        f"SHA-256 {results.sha256} matches the pin. Grades stay locked until a frozen "
        "policy passes the real-grade replay check."
    )


def _map(args: argparse.Namespace) -> str:
    output = args.output.resolve()
    for name, path in (("panel", args.panel), ("public file", args.source)):
        if output == path.resolve():
            raise AnalysisError(f"The mapping output {args.output} would overwrite the {name}")
    results = _load(args.source)
    panel = public_lcb.panel_fingerprints(args.panel)
    rows = public_lcb.read_dataset_rows()
    mapped = public_lcb.map_panel_questions(
        panel,
        public_lcb.dataset_questions(rows),
        results,
        expected=public_lcb.REFERENCE_QUESTIONS,
    )
    panel_sha256 = hashlib.sha256(args.panel.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(args.output, public_lcb.mapping_document(mapped, panel_sha256=panel_sha256))
    return (
        f"Mapped {len(mapped)} of {len(panel)} reference questions uniquely to public question "
        f"identifiers ({len(rows)} dataset rows, {len(results.questions):,} public questions). "
        f"Wrote {args.output}. No grade was printed."
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lcb-public", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Download the pinned public file")
    fetch.add_argument("--output", type=Path, default=public_lcb.DEFAULT_SOURCE_PATH)
    fetch.set_defaults(run=_fetch)
    check = commands.add_parser("check", help="Validate the downloaded file and print its shape")
    check.add_argument("--source", type=Path, default=public_lcb.DEFAULT_SOURCE_PATH)
    check.set_defaults(run=_check)
    mapping = commands.add_parser("map", help="Join the panel questions to public identifiers")
    mapping.add_argument("--source", type=Path, default=public_lcb.DEFAULT_SOURCE_PATH)
    mapping.add_argument("--panel", type=Path, default=public_lcb.DEFAULT_PANEL_PATH)
    mapping.add_argument("--output", type=Path, default=public_lcb.DEFAULT_MAPPING_PATH)
    mapping.set_defaults(run=_map)
    args = parser.parse_args(argv)
    try:
        message = args.run(args)
    except (AnalysisError, OSError, ImportError) as exc:
        parser.exit(2, f"lcb-public {args.command}: {exc}\n")
    print(message)


if __name__ == "__main__":
    main()
