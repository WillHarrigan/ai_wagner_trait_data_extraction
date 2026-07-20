"""Build a single bundle.json for the trait-validation interface (validate.html).

The old interface graded agent output against student ground truth (an xlsx of
AUTO/MANUAL/VALIDATION rows). The new pipeline has NO ground truth — instead each
species has consensus outputs (accepted >=8/10, contested 3-7/10 with critic
verdicts, rejected <=2/10) plus the Wagner source text. This script rolls one
model's run for a whole family into a flat, review-ready bundle:

  per species:
    - identity (family / genus / species) + the three levels of source TEXT
      (Family.md, Genus.md, Species.md — the reviewer needs all three because
      lower levels INHERIT unstated characters from higher ones)
    - one row per trait FINDING, each carrying everything a reviewer needs to
      judge it against the text without opening any other file:
        path, value, tier (accepted|contested|rejected),
        votes (count/of), and — when the critic ran — its verdict,
        correct_value, and the quoted passage reason.
    - the per-species metrics (accuracy, counts) for context.

Usage:
    python trait_annot_validation/build_validation_bundle.py <Family> <model_key>
    # e.g. ... Asteraceae gpt-5.4-mini-medium
    # writes trait_annot_validation/bundle.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HIER = REPO / "test_data" / "hierarchy"
RUNS = REPO / "extraction" / "runs"
CATS = REPO / "ontology" / "categorical"
OUT = Path(__file__).resolve().parent / "bundle.json"


def build_vocabulary() -> dict:
    """Valid values for every categorical trait, so the reviewer UI can offer a
    pick-list instead of a free-text box (a typo like ANNUAL_HERD is otherwise
    saved silently and only surfaces much later, downstream).

    Returns {field_name: [{name, label, definition}, ...]}. `same_values_as`
    borrowing is resolved here so the browser never has to chase indirection.
    """
    import yaml  # local: only the bundle builder needs it

    raw: dict[str, dict] = {}
    for p in sorted(CATS.glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if d.get("name"):
            raw[d["name"]] = d

    vocab: dict[str, list] = {}
    for name, d in raw.items():
        src = d
        seen = set()
        # follow same_values_as (guard against a cycle / dangling target)
        while "same_values_as" in src and src["same_values_as"] not in seen:
            seen.add(src["same_values_as"])
            nxt = raw.get(src["same_values_as"])
            if nxt is None:
                break
            src = nxt
        vocab[name] = [
            {"name": v["name"], "label": v.get("label", v["name"]),
             "definition": v.get("definition", "")}
            for v in (src.get("values") or [])
        ]
    return {k: v for k, v in vocab.items() if v}


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _flatten_accepted(obj, prefix=""):
    """accepted.json is a nested TaxonTraits-shaped dict; flatten to (path, value)
    leaves, matching how contested/rejected paths are already dotted. A list value
    (multi-categorical) becomes one row per member so each can be judged separately."""
    rows = []
    if isinstance(obj, dict):
        # a Measurement leaf ({min,max,...}) is a value, not a branch to recurse into
        if obj and all(k in ("ex_min", "min", "max", "ex_max") for k in obj):
            rows.append((prefix, _fmt_measure(obj)))
            return rows
        for k, v in obj.items():
            if v is None:
                continue
            rows.extend(_flatten_accepted(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for x in obj:
            rows.append((prefix, str(x)))
    else:
        rows.append((prefix, str(obj)))
    return rows


def _fmt_measure(m: dict) -> str:
    """Render a {min,max,ex_min,ex_max} measurement as a compact range string."""
    lo, hi = m.get("min"), m.get("max")
    exlo, exhi = m.get("ex_min"), m.get("ex_max")
    core = f"{lo}–{hi}" if lo is not None and hi is not None else str(lo if lo is not None else hi)
    if exlo is not None:
        core = f"({exlo}) {core}"
    if exhi is not None:
        core = f"{core} ({exhi})"
    return core


def build_species(stem: str, model_key: str, source: dict) -> dict | None:
    d = RUNS / stem / model_key
    if not (d / "metrics.json").exists():
        return None
    accepted = _load(d / "accepted.json", {})
    contested = _load(d / "contested.json", [])
    rejected = _load(d / "rejected.json", [])
    critic = _load(d / "critic.json", [])
    metrics = _load(d / "metrics.json", {})

    # index critic verdicts by path (one per path; the pipeline already de-dups,
    # but guard anyway — 'ambiguous' is the sticky/authoritative verdict).
    crit_by_path: dict[str, dict] = {}
    for v in critic:
        p = v["path"]
        if crit_by_path.get(p, {}).get("verdict") != "ambiguous":
            crit_by_path[p] = v

    findings = []
    # 1. accepted (>=8/10) — high confidence
    for path, value in _flatten_accepted(accepted):
        findings.append({
            "path": path, "value": value, "tier": "accepted",
            "votes": None, "of": metrics.get("n_predictors", 10), "critic": None,
        })
    # 2. contested (3-7/10) — carry vote count + critic verdict
    for c in contested:
        findings.append({
            "path": c["path"], "value": str(c["value"]), "tier": "contested",
            "votes": c.get("count"), "of": c.get("of", 10),
            "critic": crit_by_path.get(c["path"]),
        })
    # 3. rejected (<=2/10) — a minority artifact the swarm dropped; shown so a
    #    reviewer can RESCUE a correct value the majority missed.
    for r in rejected:
        findings.append({
            "path": r["path"], "value": str(r["value"]), "tier": "rejected",
            "votes": r.get("count"), "of": r.get("of", 10), "critic": None,
        })

    return {
        "key": stem,
        "family": source["family_name"],
        "genus": source["genus_name"],
        "species": source["species_name"],
        "text": {
            "family": source["family_text"],
            "genus": source["genus_text"],
            "species": source["species_text"],
        },
        "metrics": {
            "primary_accuracy": metrics.get("primary_accuracy"),
            "n_claimed_facts": metrics.get("n_claimed_facts"),
            "accepted": metrics.get("accepted_ge8of10"),
            "contested": metrics.get("contested_genuine_split"),
            "critic_resolvable": metrics.get("critic_resolvable"),
            "critic_ambiguous": metrics.get("critic_ambiguous"),
        },
        "findings": findings,
    }


def gather_source(species_file: Path) -> dict:
    """Read the three inheritance levels of source text for a species."""
    genus_dir = species_file.parent
    family_dir = genus_dir.parent
    family_md = family_dir / "Family.md"
    genus_md = genus_dir / "Genus.md"
    return {
        "family_name": family_dir.name,
        "genus_name": genus_dir.name,
        "species_name": species_file.stem,
        "family_text": family_md.read_text(encoding="utf-8") if family_md.exists() else "",
        "genus_text": genus_md.read_text(encoding="utf-8") if genus_md.exists() else "",
        "species_text": species_file.read_text(encoding="utf-8"),
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: build_validation_bundle.py <Family> <model_key>", file=sys.stderr)
        return 1
    family, model_key = argv[0], argv[1]

    species_files = sorted(
        p for p in (HIER / family).rglob("*.md")
        if p.name not in ("Family.md", "Genus.md")
    )
    species = []
    skipped = 0
    for sf in species_files:
        rec = build_species(sf.stem, model_key, gather_source(sf))
        if rec is None:
            skipped += 1
            continue
        species.append(rec)

    vocab = build_vocabulary()
    bundle = {
        "family": family,
        "model_key": model_key,
        "n_species": len(species),
        "vocabulary": vocab,
        "species": species,
    }
    OUT.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    total_findings = sum(len(s["findings"]) for s in species)
    print(f"Wrote {OUT}")
    print(f"  {len(species)} species ({skipped} skipped: no run), {total_findings} findings")
    print(f"  {len(vocab)} categorical vocabularies "
          f"({sum(len(v) for v in vocab.values())} values) for correction pick-lists")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
