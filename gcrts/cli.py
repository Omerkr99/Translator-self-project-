"""Phase 1+2 entry point: load a binary file, extract text runs, cluster, output results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gcrts.cluster import cluster_strings
from gcrts.extractor import extract_text_runs
from gcrts.loader import BinaryLoader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gcrts",
        description="Phase 1+2: binary loader, multi-encoding text extraction, clustering.",
    )
    parser.add_argument("input", help="Path to the binary file (e.g. a .BIN)")
    parser.add_argument(
        "--min-length",
        type=int,
        default=4,
        help="Minimum run length (bytes) to count as an extracted string (default: 4)",
    )
    parser.add_argument(
        "--max-cluster-gap",
        type=int,
        default=32,
        help="Max byte gap between strings to merge into one cluster (default: 32)",
    )
    parser.add_argument(
        "--output",
        help="Path to write JSON results. Defaults to <input>.gcrts.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    loader = BinaryLoader()
    try:
        segment = loader.load(args.input)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    strings = extract_text_runs(segment, min_length=args.min_length)
    clusters = cluster_strings(strings, max_gap=args.max_cluster_gap)

    output_path = Path(args.output) if args.output else Path(args.input + ".gcrts.json")
    result = {
        "source_file": str(segment.path),
        "file_size": segment.size,
        "min_length": args.min_length,
        "max_cluster_gap": args.max_cluster_gap,
        "strings_found": len(strings),
        "clusters_found": len(clusters),
        "strings": [s.to_dict() for s in strings],
        "clusters": [c.to_dict() for c in clusters],
    }
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Loaded {segment.path} ({segment.size} bytes)")
    print(f"Extracted {len(strings)} text run(s) (min length {args.min_length})")
    print(f"Grouped into {len(clusters)} cluster(s) (max gap {args.max_cluster_gap})")
    print(f"Results written to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
