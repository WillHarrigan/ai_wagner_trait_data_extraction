"""Slice a parsed-manual markdown file into a Family / Genus / Species folder tree.

For each input markdown file we call `extract()` from
`extract_taxonomy.py` to get the ordered list of taxonomic headings and
their byte offsets, then write each adjacent slice of the source text to
its destination path:

    <out_root>/<Family>/Family.md
    <out_root>/<Family>/<Genus>/Genus.md
    <out_root>/<Family>/<Genus>/<Genus>_<epithet>.md

The slices are contiguous and non-overlapping: concatenating every file in
offset order reproduces the original markdown verbatim.

Usage:
    python build_hierarchy.py <path-to-markdown> [<path> ...]
    python build_hierarchy.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extract_taxonomy import extract


def slice_file(text: str, source_name: str, out_root: Path) -> dict[str, int]:
    """Write the family/genus/species slice tree for one markdown file.

    Returns a small stats dict for the caller to print.
    """
    rows = extract(text)
    if not rows:
        print(f"  no taxonomic headings found in {source_name}", file=sys.stderr)
        return {"family": 0, "genus": 0, "species": 0}

    # Append a sentinel so the last real row gets a valid end offset.
    end_offsets = [r[2] for r in rows[1:]] + [len(text)]

    current_family: str | None = None
    current_genus: str | None = None
    stats = {"family": 0, "genus": 0, "species": 0}

    for (name, kind, start), end in zip(rows, end_offsets):
        slice_text = text[start:end]

        if kind == "family":
            current_family = name.capitalize()
            current_genus = None
            target = out_root / current_family / "Family.md"
        elif kind == "genus":
            if current_family is None:
                print(
                    f"  warning: genus {name!r} appears before any family in "
                    f"{source_name}; skipping",
                    file=sys.stderr,
                )
                continue
            current_genus = name
            target = out_root / current_family / name / "Genus.md"
        elif kind == "species":
            genus_token = name.split()[0]
            epithet = name.split()[1]
            family_dir = current_family or "Unknown"
            genus_dir = current_genus or genus_token
            target = (
                out_root
                / family_dir
                / genus_dir
                / f"{genus_token}_{epithet}.md"
            )
        else:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(slice_text, encoding="utf-8")
        stats[kind] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every .md file in V2/test_data/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output root (default: V2/test_data/hierarchy)",
    )
    args = parser.parse_args()

    repo_v2 = Path(__file__).resolve().parents[1]
    out_root = args.out if args.out else repo_v2 / "test_data" / "hierarchy"

    if args.all:
        paths = sorted((repo_v2 / "test_data").glob("*.md"))
    else:
        paths = args.paths

    if not paths:
        parser.error("provide at least one path or use --all")

    out_root.mkdir(parents=True, exist_ok=True)

    for path in paths:
        text = path.read_text(encoding="utf-8")
        stats = slice_file(text, path.name, out_root)
        print(
            f"{path.name}: "
            f"{stats['family']} family, "
            f"{stats['genus']} genus, "
            f"{stats['species']} species"
        )

    print(f"\nWrote tree under: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
