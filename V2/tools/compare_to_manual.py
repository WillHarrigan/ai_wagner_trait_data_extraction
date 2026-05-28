"""Compare our V2-extracted JSON for one species against the manually-curated
ground-truth CSV (`extraction_agent/manual_extracted_wagner_data.csv`).

Output is written to a FILE (passed on the command line). Two modes:

  Default — paste-friendly TSV, three rows in the CSV's exact 172-column order:
      python3 tools/compare_to_manual.py <species_dir> <out_file>

      File contains:
          COLUMN  family  genus  species  ...      (header)
          V2      ...                              (our values)
          MANUAL  ...                              (manual CSV values)
      Open in Excel; one row per source, columns aligned, diff visually.

  Per-field — one line per CSV column, easier for one species in a terminal:
      python3 tools/compare_to_manual.py --diff <species_dir> <out_file>

      File contains lines like:
          stem_hair_type        V2='HIRSUTE'        MANUAL='HIRSUTE'

Run on every parsed species (concatenate all rows into one TSV):
      out=all_compare.tsv
      : > "$out"                                    # truncate
      find parsed -mindepth 3 -maxdepth 3 -type d | sort | while read sp; do
        python3 tools/compare_to_manual.py "$sp" /tmp/.row.tsv
        cat /tmp/.row.tsv >> "$out"
        echo >> "$out"
      done

Conventions:
  * Cells mirror the CSV's exact serialisation (dict/list reprs, `nan` for
    missing numeric bounds) so a visual/Excel diff shows real differences
    rather than formatting noise.
  * Empty cell on V2 side = our JSON had no value for that field.
  * `#` = column exists in the CSV but cannot be derived from V2's ontology.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANUAL_CSV = REPO_ROOT / "extraction_agent" / "manual_extracted_wagner_data.csv"
UNDERIVABLE = "#"   # column exists in CSV but cannot come from our JSON


# ---------------------------------------------------------------------------
# CSV-style serialisers — match the exact string form used in the manual CSV
# ---------------------------------------------------------------------------
def fmt_measurements(m: dict | None, unit_default: str = "") -> str:
    """Match CSV form: "{'exmin': nan, 'min': 2.5, 'max': 13.0, 'exmax': nan, 'unit': 'cm'}"
    Returns '' if m is missing entirely.
    """
    if not m:
        return ""
    def n(v): return "nan" if v in (None, "") else repr(v) if isinstance(v, str) else str(v)
    return ("{'exmin': %s, 'min': %s, 'max': %s, 'exmax': %s, 'unit': %s}"
            % (
                n(m.get("extreme_min")),
                n(m.get("min")),
                n(m.get("max")),
                n(m.get("extreme_max")),
                repr(m.get("unit", unit_default) or ""),
            ))


def fmt_scalar_str(v) -> str:
    """Single string value: CSV stores it raw (unquoted), so we emit it raw.
    If the ontology value is a 1-element list, unwrap it. If multi-element,
    fall back to list-repr (something is off in the data)."""
    if v in (None, ""):
        return ""
    if isinstance(v, list):
        if not v: return ""
        if len(v) == 1: return str(v[0])
        return repr(v)
    return str(v)


def fmt_list(v) -> str:
    """Multi-value list: CSV emits "['A', 'B']". Empty if missing."""
    if v in (None, ""):
        return ""
    if not isinstance(v, list):
        v = [v]
    if not v:
        return ""
    return repr(v)


def fmt_set(v) -> str:
    """Hawaiian-name style: CSV emits Python set repr "{'foo'}". Our JSON
    has it as a comma-separated string, so we split on commas, strip, and emit
    a set repr."""
    if v in (None, ""):
        return ""
    if isinstance(v, str):
        items = [p.strip() for p in v.split(",") if p.strip()]
    elif isinstance(v, list):
        items = [str(p).strip() for p in v if str(p).strip()]
    else:
        items = [str(v).strip()]
    if not items:
        return ""
    return repr(set(items))


def fmt_chromosome(v) -> str:
    """CSV form: '34, 36'  (note the trailing-space-after-comma)."""
    if v in (None, ""):
        return ""
    if not isinstance(v, list):
        v = [v]
    return ", ".join(str(x) for x in v)


def fmt_ploidy(v) -> str:
    """CSV form: '2n' (just the literal string)."""
    if v in (None, ""):
        return ""
    if isinstance(v, list):
        if not v: return ""
        return ", ".join(str(x) for x in v)
    return str(v)


def fmt_raw_str(v) -> str:
    """Common-name, colors, page numbers: CSV stores them as raw strings
    (no extra quoting beyond CSV escaping). Return the string verbatim."""
    if v in (None, ""):
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


# ---------------------------------------------------------------------------
# Per-group JSON loader
# ---------------------------------------------------------------------------
def load_groups(species_dir: Path) -> dict:
    out = {}
    for f in species_dir.glob("*.json"):
        out[f.stem] = json.loads(f.read_text())
    return out


def get(groups: dict, group: str, *path):
    cur = groups.get(group)
    for k in path:
        if cur is None or not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


# ---------------------------------------------------------------------------
# Resolvers: how to compute each CSV column from our JSON
# ---------------------------------------------------------------------------
#
# Each entry is a callable `(groups, family, genus, species) -> str`.
#
# Conventions used in the resolvers:
#   * cat_scalar(group, field)   — return our value as scalar-repr ('STRIGOSE')
#   * cat_list(group, field)     — return as list-repr ("['CORDATE','OVATE']")
#   * dim_axis(group, field, axis) — flat CSV column reads our nested
#                                   `field.<length|width>` Measurements and
#                                   serialises it as a dict-repr.
#   * meas(group, field)         — scalar Measurements (no length/width split)
#

def _cat_scalar(group, field):
    return lambda g, *_: fmt_scalar_str(get(g, group, field))

def _cat_list(group, field):
    return lambda g, *_: fmt_list(get(g, group, field))

def _dim_axis(group, field, axis):
    return lambda g, *_: fmt_measurements(get(g, group, field, axis))

def _meas(group, field):
    return lambda g, *_: fmt_measurements(get(g, group, field))

def _raw(group, field):
    return lambda g, *_: fmt_raw_str(get(g, group, field))


# Build the resolver table — one entry per CSV column. KEY = CSV column name.
# When the CSV column has no direct ontology counterpart, use UNDERIVABLE.
RESOLVERS: dict = {
    "": lambda *_: "",                       # empty leading column in CSV

    # Identity / source
    "family":                lambda g, fam, gen, sp: fam,
    "genus":                 lambda g, fam, gen, sp: gen,
    "species":               lambda g, fam, gen, sp: sp,
    "species_key":           lambda *_: UNDERIVABLE,
    "common_name":           _raw("taxon_identity", "common_name"),
    "wagner_pg_number":      _raw("source_document", "wagner_pg_number"),
    "description":           _raw("taxon_identity", "description"),
    "infraspecific_epithet": _raw("taxon_identity", "infraspecific_epithet"),
    "hawaiian_name":         lambda g, *_: fmt_set(get(g, "taxon_identity", "hawaiian_name")),

    # Single-categoricals (scalar)
    "stem_hair_type":              _cat_scalar("stem_morphology", "stem_hair_type"),
    "phyllotaxy_type":             _cat_scalar("leaf_morphology", "phyllotaxy_type"),
    "breeding_type":               _cat_scalar("reproductive_morphology", "breeding_type"),
    "inflorescence_type":          _cat_scalar("inflorescence_morphology", "inflorescence_type"),
    "fruit_type":                  _cat_scalar("fruit_morphology", "fruit_type"),
    "life_form_type":              _cat_scalar("life_form", "life_form_type"),
    "leaf_type":                   _cat_scalar("leaf_morphology", "leaf_type"),
    "juvenile_leaf_type":          _cat_scalar("juvenile_leaf_morphology", "juvenile_leaf_type"),
    "leaflets_leaf_type":          _cat_scalar("leaflet_morphology", "leaflets_leaf_type"),
    "leaf_hair_type":              _cat_scalar("leaf_indumentum", "leaf_hair_type"),
    "leaf_hair_upper_type":        _cat_scalar("leaf_indumentum", "upper_leaf_hair_type"),
    "leaf_hair_lower_type":        _cat_scalar("leaf_indumentum", "lower_leaf_hair_type"),
    "juvenile_leaf_hair_type":     _cat_scalar("juvenile_leaf_morphology", "juvenile_leaf_hair_type"),
    "corolla_type":                _cat_scalar("outer_flower_morphology", "corolla_type"),
    "staminate_corolla_type":      lambda *_: UNDERIVABLE,   # not in our ontology
    "pistillate_corolla_type":     lambda *_: UNDERIVABLE,   # not in our ontology

    # Multi-categoricals (lists)
    "leaf_margin_type":            _cat_list("leaf_morphology", "leaf_margin_type"),
    "leaf_shape_type":             _cat_list("leaf_morphology", "leaf_shape_type"),
    "juvenile_leaf_margin_type":   _cat_list("juvenile_leaf_morphology", "juvenile_leaf_margin_type"),
    "juvenile_leaf_shape_type":    _cat_list("juvenile_leaf_morphology", "juvenile_leaf_shape_type"),
    "leaflets_leaf_margin_type":   _cat_list("leaflet_morphology", "leaflets_leaf_margin_type"),
    "leaflets_leaf_shape_type":    _cat_list("leaflet_morphology", "leaflets_leaf_shape_type"),
    "island_type":                 _cat_list("distribution", "island_type"),

    # Colors (raw strings)
    "ray_color":          _raw("inflorescence_morphology", "ray_color"),
    "floret_color":       _raw("inflorescence_morphology", "floret_color"),
    "spathe_color":       _raw("inflorescence_morphology", "spathe_color"),
    "perianth_outer_color": _raw("outer_flower_morphology", "perianth_outer_color"),
    "perianth_inner_color": _raw("outer_flower_morphology", "perianth_inner_color"),
    "perianth_color":     _raw("outer_flower_morphology", "perianth_color"),
    "labellum_color":     _raw("outer_flower_morphology", "labellum_color"),
    "corolla_color":      _raw("outer_flower_morphology", "corolla_color"),

    # Cytology
    "ploidy":                   lambda g, *_: fmt_ploidy(get(g, "reproductive_morphology", "ploidy")),
    "chromosome_number":        lambda g, *_: fmt_chromosome(get(g, "reproductive_morphology", "chromosome_number")),
    "average_chromosome_number": lambda *_: UNDERIVABLE,

    # Distribution
    "origin":  lambda g, *_: (lambda v: fmt_scalar_str(v))(get(g, "distribution", "origin")),
    "status":  lambda g, *_: (lambda v: fmt_scalar_str(v))(get(g, "distribution", "status")),

    # Scalar measurements (no length/width split in CSV)
    "stem_height":                       _meas("stem_morphology", "stem_height"),
    "petioles":                          _meas("leaf_morphology", "petiole_length"),
    "rachis_length":                     _meas("inflorescence_morphology", "rachis_length"),
    "rachis_diameter":                   _meas("inflorescence_morphology", "rachis_diameter"),
    "head_length":                       _meas("inflorescence_morphology", "head_length"),
    "head_diameter":                     _meas("inflorescence_morphology", "head_diameter"),
    "bur_length":                        _meas("fruit_morphology", "bur_length"),
    "tepal_length":                      _meas("outer_flower_morphology", "tepal_length"),
    "staminate_tepal_length":            _meas("outer_flower_morphology", "staminate_tepal_length"),
    "pistillate_tepal_length":           _meas("outer_flower_morphology", "pistillate_tepal_length"),
    "florets_length":                    _meas("inflorescence_morphology", "florets_length"),
    "staminate_involucre_length":        _meas("bract_involucre_morphology", "staminate_involucre_length"),
    "pistilate_involucre_length":        _meas("bract_involucre_morphology", "pistillate_involucre_length"),   # CSV spells "pistilate"
    "bract_lower_length":                _meas("bract_involucre_morphology", "bract_lower_length"),
    "bract_outer_length":                _meas("bract_involucre_morphology", "bract_outer_length"),
    "pistillate_pedicel_length":         _meas("inflorescence_morphology", "pistillate_pedicel_dimensions") if False else _dim_axis("inflorescence_morphology", "pistillate_pedicel_dimensions", "length"),
    "spadix_length":                     _meas("inflorescence_morphology", "spadix_length"),
    "perianth_tube_length":              _meas("outer_flower_morphology", "perianth_tube_length"),
    "staminate_perianth_tube_length":    _meas("outer_flower_morphology", "staminate_perianth_tube_length"),
    "pistillate_perianth_tube_length":   _meas("outer_flower_morphology", "pistillate_perianth_tube_length"),
    "pappus_length":                     _meas("inflorescence_morphology", "pappus_length"),
    "umbellet_length":                   _meas("inflorescence_morphology", "umbellet_length"),
    "upper_calyx_length":                _meas("outer_flower_morphology", "upper_calyx_length"),
    "lower_calyx_length":                _meas("outer_flower_morphology", "lower_calyx_length"),
    "inner_calyx_length":                _meas("outer_flower_morphology", "inner_calyx_length"),
    "outer_calyx_length":                _meas("outer_flower_morphology", "outer_calyx_length"),
    "male_calyx_tube_length":            _meas("outer_flower_morphology", "male_calyx_tube_length"),
    "upper_corolla_length":              _meas("outer_flower_morphology", "upper_corolla_length"),
    "lower_corolla_length":              _meas("outer_flower_morphology", "lower_corolla_length"),
    "upper_corolla_lobes_length":        _meas("outer_flower_morphology", "upper_corolla_lobes_length"),
    "lower_corolla_lobes_length":        _meas("outer_flower_morphology", "lower_corolla_lobes_length"),
    "corolla_lip_length":                _meas("outer_flower_morphology", "corolla_lip_length"),
    "staminate_corolla_length":          _meas("outer_flower_morphology", "staminate_corolla_length"),
    "pistillate_corolla_length":         _meas("outer_flower_morphology", "pistillate_corolla_length"),
    "fruit_length":                      _meas("fruit_morphology", "fruit_length"),
    "fruit_width":                       _meas("fruit_morphology", "fruit_width"),
    "fruit_diameter":                    _meas("fruit_morphology", "fruit_diameter"),
    "seed_length":                       _meas("fruit_morphology", "seed_length"),
    "seed_width":                        _meas("fruit_morphology", "seed_width"),
    "seed_diameter":                     _meas("fruit_morphology", "seed_diameter"),
    "seeds_perfruit":                    _meas("fruit_morphology", "seeds_perfruit"),

    # CSV flat *_length / *_width  →  our nested Dimensions.length / .width
    "leaf_length":                       _dim_axis("leaf_morphology", "leaf_dimensions", "length"),
    "leaf_width":                        _dim_axis("leaf_morphology", "leaf_dimensions", "width"),
    "juvenile_leaf_length":              _dim_axis("juvenile_leaf_morphology", "juvenile_leaf_dimensions", "length"),
    "juvenile_leaf_width":               _dim_axis("juvenile_leaf_morphology", "juvenile_leaf_dimensions", "width"),
    "leaflets_leaf_length":              _dim_axis("leaflet_morphology", "leaflets_leaf_dimensions", "length"),
    "leaflets_leaf_width":               _dim_axis("leaflet_morphology", "leaflets_leaf_dimensions", "width"),
    "staminate_inflorescence_length":    _dim_axis("inflorescence_morphology", "staminate_inflorescence_dimensions", "length"),
    "staminate_inflorescence_width":     _dim_axis("inflorescence_morphology", "staminate_inflorescence_dimensions", "width"),
    "pistillate_inflorescence_length":   _dim_axis("inflorescence_morphology", "pistillate_inflorescence_dimensions", "length"),
    "pistillate_inflorescence_width":    _dim_axis("inflorescence_morphology", "pistillate_inflorescence_dimensions", "width"),
    "inflorescence_flower_length":       lambda *_: UNDERIVABLE,   # not in our ontology (no inflorescence_flower_*)
    "inflorescence_flower_width":        lambda *_: UNDERIVABLE,
    "flower_length":                     _dim_axis("outer_flower_morphology", "flower_dimensions", "length"),
    "flower_width":                      _dim_axis("outer_flower_morphology", "flower_dimensions", "width"),
    "ray_length":                        _dim_axis("inflorescence_morphology", "ray_dimensions", "length"),
    "ray_width":                         _dim_axis("inflorescence_morphology", "ray_dimensions", "width"),
    "involucre_length":                  _dim_axis("bract_involucre_morphology", "involucre_dimensions", "length"),
    "involucre_width":                   _dim_axis("bract_involucre_morphology", "involucre_dimensions", "width"),
    "bract_length":                      _dim_axis("bract_involucre_morphology", "bract_dimensions", "length"),
    "bract_width":                       _dim_axis("bract_involucre_morphology", "bract_dimensions", "width"),
    "bracteoles_length":                 _dim_axis("bract_involucre_morphology", "bracteoles_dimensions", "length"),
    "bracteoles_width":                  _dim_axis("bract_involucre_morphology", "bracteoles_dimensions", "width"),
    "pedicel_length":                    _dim_axis("inflorescence_morphology", "pedicel_dimensions", "length"),
    "pedicel_width":                     _dim_axis("inflorescence_morphology", "pedicel_dimensions", "width"),
    "staminate_pedicel_length":          _dim_axis("inflorescence_morphology", "staminate_pedicel_dimensions", "length"),
    "hypanthium_length":                 _dim_axis("inflorescence_morphology", "hypanthium_dimensions", "length"),
    "hypanthium_width":                  _dim_axis("inflorescence_morphology", "hypanthium_dimensions", "width"),
    "peduncle_length":                   _dim_axis("inflorescence_morphology", "peduncle_dimensions", "length"),
    "peduncle_width":                    _dim_axis("inflorescence_morphology", "peduncle_dimensions", "width"),
    "pistillate_peduncle_length":        _dim_axis("inflorescence_morphology", "pistillate_peduncle_dimensions", "length"),
    "pistillate_peduncle_width":         _dim_axis("inflorescence_morphology", "pistillate_peduncle_dimensions", "width"),
    "staminate_peduncle_length":         _dim_axis("inflorescence_morphology", "staminate_peduncle_dimensions", "length"),
    "staminate_peduncle_width":          _dim_axis("inflorescence_morphology", "staminate_peduncle_dimensions", "width"),
    "spathe_length":                     _dim_axis("inflorescence_morphology", "spathe_dimensions", "length"),
    "spathe_width":                      _dim_axis("inflorescence_morphology", "spathe_dimensions", "width"),
    "perianth_length":                   _dim_axis("outer_flower_morphology", "perianth_dimensions", "length"),
    "perianth_width":                    _dim_axis("outer_flower_morphology", "perianth_dimensions", "width"),
    "perianth_outer_length":             _dim_axis("outer_flower_morphology", "perianth_outer_dimensions", "length"),
    "perianth_outer_width":              _dim_axis("outer_flower_morphology", "perianth_outer_dimensions", "width"),
    "perianth_inner_length":             _dim_axis("outer_flower_morphology", "perianth_inner_dimensions", "length"),
    "perianth_inner_width":              _dim_axis("outer_flower_morphology", "perianth_inner_dimensions", "width"),
    "perianth_lobes_length":             _dim_axis("outer_flower_morphology", "perianth_lobes_dimensions", "length"),
    "perianth_lobes_width":              _dim_axis("outer_flower_morphology", "perianth_lobes_dimensions", "width"),
    "labellum_length":                   _dim_axis("outer_flower_morphology", "labellum_dimensions", "length"),
    "labellum_width":                    _dim_axis("outer_flower_morphology", "labellum_dimensions", "width"),
    "calyx_length":                      _dim_axis("outer_flower_morphology", "calyx_dimensions", "length"),
    "calyx_width":                       _dim_axis("outer_flower_morphology", "calyx_dimensions", "width"),
    "calyx_teeth_length":                _dim_axis("outer_flower_morphology", "calyx_teeth_dimensions", "length"),
    "calyx_teeth_width":                 _dim_axis("outer_flower_morphology", "calyx_teeth_dimensions", "width"),
    "calyx_lobes_length":                _dim_axis("outer_flower_morphology", "calyx_lobe_dimensions", "length"),
    "calyx_lobes_width":                 _dim_axis("outer_flower_morphology", "calyx_lobe_dimensions", "width"),
    "inner_calyx_lobes_length":          _dim_axis("outer_flower_morphology", "inner_calyx_lobes_dimensions", "length"),
    "inner_calyx_lobes_width":           _dim_axis("outer_flower_morphology", "inner_calyx_lobes_dimensions", "width"),
    "outer_calyx_lobes_length":          _dim_axis("outer_flower_morphology", "outer_calyx_lobes_dimensions", "length"),
    "outer_calyx_lobes_width":           _dim_axis("outer_flower_morphology", "outer_calyx_lobes_dimensions", "width"),
    "calyx_tube_length":                 _dim_axis("outer_flower_morphology", "calyx_tube_dimensions", "length"),
    "calyx_tube_width":                  _dim_axis("outer_flower_morphology", "calyx_tube_dimensions", "width"),
    "male_calyx_length":                 _dim_axis("outer_flower_morphology", "male_calyx_dimensions", "length"),
    "male_calyx_width":                  _dim_axis("outer_flower_morphology", "male_calyx_dimensions", "width"),
    "male_calyx_lobes_length":           _dim_axis("outer_flower_morphology", "male_calyx_lobe_dimensions", "length"),
    "male_calyx_lobes_width":            _dim_axis("outer_flower_morphology", "male_calyx_lobe_dimensions", "width"),
    "female_calyx_length":               _dim_axis("outer_flower_morphology", "female_calyx_dimensions", "length"),
    "female_calyx_width":                _dim_axis("outer_flower_morphology", "female_calyx_dimensions", "width"),
    "female_calyx_lobes_length":         _dim_axis("outer_flower_morphology", "female_calyx_lobe_dimensions", "length"),
    "female_calyx_lobes_width":          _dim_axis("outer_flower_morphology", "female_calyx_lobe_dimensions", "width"),
    "male_calyx_lobes_length_inner":     lambda *_: UNDERIVABLE,   # not in our ontology
    "male_calyx_lobes_length_outer":     lambda *_: UNDERIVABLE,
    "male_calyx_lobes_width_outer":      lambda *_: UNDERIVABLE,
    "female_calyx_lobes_length_inner":   lambda *_: UNDERIVABLE,
    "female_calyx_lobes_length_outer":   lambda *_: UNDERIVABLE,
    "female_calyx_lobes_width_inner":    lambda *_: UNDERIVABLE,
    "female_calyx_lobes_width_outer":    lambda *_: UNDERIVABLE,
    "corolla_length":                    _dim_axis("outer_flower_morphology", "corolla_dimensions", "length"),
    "corolla_width":                     _dim_axis("outer_flower_morphology", "corolla_dimensions", "width"),
    "corolla_tube_length":               _dim_axis("outer_flower_morphology", "corolla_tube_dimensions", "length"),
    "corolla_tube_width":                _dim_axis("outer_flower_morphology", "corolla_tube_dimensions", "width"),
    "corolla_lobes_length":              _dim_axis("outer_flower_morphology", "corolla_lobe_dimensions", "length"),
    "corolla_lobes_width":               _dim_axis("outer_flower_morphology", "corolla_lobe_dimensions", "width"),
    "staminate_corolla_tube_length":     _dim_axis("outer_flower_morphology", "staminate_corolla_tube_dimensions", "length"),
    "staminate_corolla_tube_width":      _dim_axis("outer_flower_morphology", "staminate_corolla_tube_dimensions", "width"),
    "pistillate_corolla_tube_length":    _dim_axis("outer_flower_morphology", "pistillate_corolla_tube_dimensions", "length"),
    "pistillate_corolla_tube_width":     _dim_axis("outer_flower_morphology", "pistillate_corolla_tube_dimensions", "width"),
    "female_corolla_lobes_length":       _dim_axis("outer_flower_morphology", "female_corolla_lobe_dimensions", "length"),
    "female_corolla_lobes_width":        _dim_axis("outer_flower_morphology", "female_corolla_lobe_dimensions", "width"),
    "male_corolla_lobes_length":         _dim_axis("outer_flower_morphology", "male_corolla_lobe_dimensions", "length"),
    "male_corolla_lobes_width":          _dim_axis("outer_flower_morphology", "male_corolla_lobe_dimensions", "width"),
}


# ---------------------------------------------------------------------------
# CSV reader: find the row matching a (family, genus, species) triple
# ---------------------------------------------------------------------------
def find_manual_row(csv_path: Path, family: str, genus: str, species: str) -> dict | None:
    fam_l, gen_l, sp_l = family.lower(), genus.lower(), species.lower()
    with open(csv_path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("family", "").lower() == fam_l
                and row.get("genus", "").lower() == gen_l
                and row.get("species", "").lower() == sp_l):
                return row
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args(argv):
    diff_mode = False
    args = []
    for a in argv[1:]:
        if a == "--diff":
            diff_mode = True
        else:
            args.append(a)
    if len(args) != 2:
        print("usage: compare_to_manual.py [--diff] <species_dir> <out_file>", file=sys.stderr)
        sys.exit(2)
    return diff_mode, Path(args[0]).resolve(), Path(args[1]).resolve()


def main():
    diff_mode, species_dir, out_path = parse_args(sys.argv)

    if not species_dir.is_dir():
        print(f"not a directory: {species_dir}", file=sys.stderr)
        sys.exit(2)
    if not MANUAL_CSV.exists():
        print(f"manual CSV not found: {MANUAL_CSV}", file=sys.stderr)
        sys.exit(2)

    # Derive family/genus/species from the path: .../parsed/<family>/<genus>/<species>/
    parts = species_dir.parts
    species = parts[-1]
    genus = parts[-2]
    family = parts[-3]

    groups = load_groups(species_dir)
    manual = find_manual_row(MANUAL_CSV, family, genus, species)

    # Read CSV header to get exact column order
    with open(MANUAL_CSV, newline="") as f:
        header = next(csv.reader(f))

    # Compute our row in CSV column order
    v2_row = []
    for col in header:
        resolver = RESOLVERS.get(col)
        if resolver is None:
            v2_row.append(UNDERIVABLE)        # CSV column we forgot to map
        else:
            try:
                v2_row.append(resolver(groups, family, genus, species))
            except Exception as e:
                v2_row.append(f"<ERR:{type(e).__name__}>")

    manual_row = [(manual or {}).get(col, "") for col in header]

    # Ensure the output directory exists.
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as out:
        if diff_mode:
            width = max(len(c) for c in header)
            for col, v2, mn in zip(header, v2_row, manual_row):
                if not v2 and not mn:
                    continue
                out.write(f"{col:<{width}}  V2={v2!r:<60}  MANUAL={mn!r}\n")
            if manual is None:
                out.write(f"\n(NOTE: no manual row found for {family} / {genus} {species})\n")
        else:
            def tsv(label, cells):
                return label + "\t" + "\t".join(
                    c.replace("\t", " ").replace("\n", " ") for c in cells
                ) + "\n"
            out.write(tsv("COLUMN", header))
            out.write(tsv("V2", v2_row))
            out.write(tsv("MANUAL", manual_row if manual else ["" for _ in header]))

    # Brief stdout summary (one line, easy to spot in a loop)
    note = "" if manual else "  (NO MANUAL ROW)"
    print(f"wrote {out_path}{note}")


if __name__ == "__main__":
    main()
