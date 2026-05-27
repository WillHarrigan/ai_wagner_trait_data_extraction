"""Extract family / genus / species headers from a markdown manual.

Output format: one record per line, tab-separated:
    <matching string>\t<family|genus|species>\t<start position>

Position is a byte/char offset into the original file.

Usage:
    python extract_taxonomy.py <path-to-markdown> [path-to-markdown ...]
    python extract_taxonomy.py --all                # process V2/test_data/*.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADER_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# Bare numbered species lines that lost their "#" in the markdown export,
# e.g. "8. Ipomoea littoralis Blume" appearing as a standalone paragraph.
# Constraints, designed to skip dichotomous-key couplet entries:
#   - Preceded by a blank line (so it's a paragraph, not a list item).
#   - Shape "N. Genus epithet ..." where Genus is Title-Case and epithet is
#     a single lowercase word (allowing hyphens), i.e. a Linnaean binomial.
#   - Does NOT end in "..." or contain "....." (key-couplet pointer rows).
BARE_NUMBERED_RE = re.compile(
    r"(?:^|\n)\n(\d+\.\s+\*?[A-Z][A-Za-z\-]+\s+[a-z][a-z\-]+\*?\b[^\n]*)\n",
    re.MULTILINE,
)

# Bare numbered genus headers like "4. *DIANTHUS* L. Pink" appearing as a
# standalone paragraph (lost their "#" in the VLM export).
BARE_GENUS_RE = re.compile(
    r"(?:^|\n)\n(\d+\.\s+\*?[A-Z][A-Z\-]{2,}\*?\b[^\n]*)\n",
    re.MULTILINE,
)

# Strip markdown emphasis (* and _) used inconsistently in the source.
EMPH_RE = re.compile(r"[*_]")

# Leading "N." or "N(M)." numbering like "1.", "12.", "3(1)."
LEADING_NUM_RE = re.compile(r"^\s*\d+(?:\([^)]*\))?\.\s*")

FAMILY_RE = re.compile(r"^[A-Z][A-Z\-]{3,}ACEAE\b")
GENUS_TOKEN_RE = re.compile(r"^[A-Z][A-Z\-]{2,}$")
SPECIES_RE = re.compile(r"^([A-Z][a-z\-]+)\s+([a-z][a-z\-]+)\b")

NOISE_PREFIXES = ("KEY TO", "PLATE", "FIGURE")


def classify(header_text: str) -> tuple[str, str] | None:
    """Return (kind, canonical_string) or None if the header is noise."""
    cleaned = EMPH_RE.sub("", header_text).strip()
    cleaned = LEADING_NUM_RE.sub("", cleaned).strip()
    if not cleaned:
        return None

    upper = cleaned.upper()
    if any(upper.startswith(p) for p in NOISE_PREFIXES):
        return None

    first_token = cleaned.split()[0]

    if FAMILY_RE.match(first_token):
        return ("family", first_token)

    if GENUS_TOKEN_RE.match(first_token) and not first_token.endswith("ACEAE"):
        return ("genus", first_token.capitalize())

    m = SPECIES_RE.match(cleaned)
    if m:
        return ("species", f"{m.group(1)} {m.group(2)}")

    return None


def extract(text: str) -> list[tuple[str, str, int]]:
    """Return list of (matching_string, kind, start_position).

    Family headers that repeat (page-break artifacts) are emitted only the
    first time; genus/species rows are always emitted.
    """
    seen_families: set[str] = set()
    seen_genera: set[str] = set()
    seen_species: set[str] = set()
    rows: list[tuple[str, str, int]] = []

    # First pass: collect all genus names from both #-headers and bare
    # italicized lines (e.g. "4. *DIANTHUS* L. Pink"). Species matching
    # then uses this set to reject dichotomous-key couplet rows like
    # "8(7). Corolla white..." whose first word is not a genus.
    header_candidates: list[tuple[int, str]] = []
    known_genera: set[str] = set()
    for m in HEADER_RE.finditer(text):
        header_candidates.append((m.start(), m.group(2)))
        result = classify(m.group(2))
        if result and result[0] == "genus":
            known_genera.add(result[1])

    bare_genus_candidates: list[tuple[int, str]] = []
    for m in BARE_GENUS_RE.finditer(text):
        line = m.group(1)
        result = classify(line)
        if not result or result[0] != "genus":
            continue
        known_genera.add(result[1])
        bare_genus_candidates.append((m.start(1), line))

    candidates: list[tuple[int, str]] = list(header_candidates)
    candidates.extend(bare_genus_candidates)
    for m in BARE_NUMBERED_RE.finditer(text):
        line = m.group(1)
        # The line must name an already-declared genus. Key-couplet rows
        # like "8(7). Corolla white..." fail this check.
        stripped = LEADING_NUM_RE.sub("", EMPH_RE.sub("", line)).strip()
        first_token = stripped.split()[0] if stripped else ""
        if first_token not in known_genera:
            continue
        candidates.append((m.start(1), line))

    candidates.sort(key=lambda t: t[0])

    for start, header_text in candidates:
        result = classify(header_text)
        if not result:
            continue
        kind, canonical = result
        if kind == "family":
            if canonical in seen_families:
                continue
            seen_families.add(canonical)
        elif kind == "genus":
            if canonical in seen_genera:
                continue
            seen_genera.add(canonical)
        elif kind == "species":
            if canonical in seen_species:
                continue
            seen_species.add(canonical)
        rows.append((canonical, kind, start))

    return rows


def process_file(path: Path, out) -> int:
    text = path.read_text(encoding="utf-8")
    rows = extract(text)
    for matched, kind, pos in rows:
        out.write(f"{matched}\t{kind}\t{pos}\n")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every .md file in V2/test_data/",
    )
    parser.add_argument(
        "--with-source",
        action="store_true",
        help="Prepend source filename as a fourth column",
    )
    args = parser.parse_args()

    if args.all:
        repo_root = Path(__file__).resolve().parents[1]
        paths = sorted((repo_root / "test_data").glob("*.md"))
    else:
        paths = args.paths

    if not paths:
        parser.error("provide at least one path or use --all")

    for path in paths:
        if args.with_source:
            text = path.read_text(encoding="utf-8")
            for matched, kind, pos in extract(text):
                sys.stdout.write(f"{path.name}\t{matched}\t{kind}\t{pos}\n")
        else:
            process_file(path, sys.stdout)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
