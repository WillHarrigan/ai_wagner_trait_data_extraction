# Using the Trait Ontology — Command-Line Guide

A practical guide for exploring the ontology from the terminal. Run everything
from the `V2/` directory.

```bash
cd V2
# (one-time) pip install -r requirements.txt
```

Every command is `python3 -m trait_ontology <command> [args]`.
Add `--json` to any command for machine-readable output (handy for agents).

## The three verbs you need

| Verb | Does | Example |
|------|------|---------|
| **`list`** | show any node (group / trait / field / value), or filter fields | `list leaf_shape_type CORDATE` |
| **`search`** | find anything matching a keyword | `search calyx` |

Plus task verbs for extraction: `resolve`, `resolve-any`, and the utilities
`stats`, `check`.

---

## `list` — show any node, or filter

`list <name>` shows the full detail of whatever you name — a group, a trait, a
field, or (with a second arg) a single value. With no name it shows all groups;
with `--` flags it filters fields.

```bash
list                          # all 15 groups (all top-level)
list leaf_morphology          # a group: its traits + fields
list leaf_shape_type          # a trait: all its values (definitions, synonyms)
list leaf_shape_type CORDATE  # a single value: definition, synonyms, narrower terms
list fruit_diameter           # a field: datatype, description, structure/sex/position
list a,b,c                    # multi-name: one call, returns sections for each name
```

For batch lookups, pass a comma-separated list:
`list life_form_type,breeding_type,description` returns all three trait
checklists in one call (sections separated by `── name ──` headers, or a
dict keyed by name in `--json` mode).

A value lives inside a trait, so name both: `list <trait> <VALUE>`. A bare
`list CORDATE` (a value in several traits) tells you which trait to name.

Filter across the whole taxonomy with flags. **`list --structure <part>` is the
extraction checklist for a body part** — it includes the categorical trait (e.g.
`fruit_type`) *and* the measurement fields, grouped by sex:

```bash
list --structure fruit              # fruit_type + fruit measurements (the checklist)
list --structure calyx              # everything for the calyx
list --structure calyx --sex male   # just the male calyx fields
list --position tube                # every tube field
list --group fruit_morphology       # everything in a group

list --structures                   # the valid structure names (with field counts)
list --positions                    # the valid position names (with field counts)
```

Filters: `--structure`, `--sex`, `--position`, `--group`.
(Adding `--sex`/`--position` narrows to fields only and omits the categorical
trait, since those filters don't apply to a controlled vocabulary. Each field's
datatype — quantitative / text / list — is shown inline in `[brackets]`.)

---

## `search` — find anything matching a keyword

Substring match across **names, synonyms, and definitions**, over groups,
traits, fields, and values. Each hit shows *where* it matched.

```bash
search calyx
```
```
field  calyx_dimensions         quantitative  (name)
field  male_calyx_tube_length   quantitative  (name)
... 11 match(es).
```

Find by a book phrasing (matches synonyms):

```bash
search "heart-shaped"
```
```
value  CORDATE   in leaf_shape_type   (synonym)
```

**Batch form** — comma-separated keywords in one call:

```bash
search "floret, ray color, pappus, outer flower"
```
Returns one section per keyword (sections separated by `── search 'kw' ──`
headers) or a dict keyed by keyword in `--json` mode.


---

## Extraction tasks

### `resolve` / `resolve-any` — normalize a book phrase to a code

```bash
resolve leaf_shape_type "heart-shaped"   # -> CORDATE  (within one trait)
resolve-any "bell-shaped"                # -> corolla_type.CAMPANULATE  (across all traits)
```

**Batch form** — comma-separated phrases for the same trait in one call.
Always prefer this when the passage gives several phrases at once
("ovate to lanceolate", "rhombic-ovate to triangular"):

```bash
resolve leaf_shape_type "ovate, lanceolate, rhombic, triangular"
# -> four mappings printed, one per phrase
resolve-any "bell-shaped, prostrate, opposite"
# -> grouped by phrase; "prostrate" reports no match
```
JSON mode returns a dict keyed by phrase.

---

## Utilities

```bash
stats     # summary counts
check     # validate the ontology YAML after hand-edits
```

---

## Editing the ontology

It's plain YAML in `ontology/` — the sole source of truth.

- **Add a value to a trait:** add an item under `values:` in the trait's file
  (`ontology/categorical/<trait>.yaml`).
- **Add a synonym** (so `resolve`/`search` catch a book phrasing): add it to that
  value's `synonyms:` list.
- **Add a new trait:** create a file in `ontology/categorical/` with a `group`
  that exists in `ontology/groups.yaml` (membership is derived from `group`).
- **Add a field:** add an entry under `measurements:` in
  `ontology/measurements.yaml`.

After any edit:

```bash
python3 -m trait_ontology check
```

---

## How an extraction agent uses it

1. **Discover** what's recordable — `list`, `list <group>`.
2. **Scope a body part** seen in the text — `list --structure calyx` for the full
   checklist (categorical trait + measurements, grouped by sex), or add
   `--sex male` to narrow to just the male fields.
3. **Normalize** a phrase from the book — `resolve` / `resolve-any`
   ("heart-shaped" → CORDATE).
4. **Disambiguate** a term — `list <trait> <VALUE>` for definition + synonyms
   + narrower terms.

---

## Quick reference

| I want to...                          | Command |
|---------------------------------------|---------|
| See the groups                        | `list` |
| Drill into a group / trait            | `list <group>` / `list <trait>` |
| Filter fields                         | `list --structure calyx --sex male` |
| Find anything by keyword              | `search <text>` |
| Full detail of one thing             | `list <name> [VALUE]` |
| Checklist for a body part             | `list --structure <part>` |
| See valid structure names             | `list --structures` |
| See valid position names               | `list --positions` |
| Map a book phrase → code              | `resolve <trait> "<phrase>"` / `resolve-any "<phrase>"` |
| Summary counts                        | `stats` |
| Validate after editing                | `check` |
| Machine-readable output               | add `--json` to any command |

Trait names to try: `leaf_shape_type`, `corolla_type`, `leaf_margin_type`,
`phyllotaxy_type`, `inflorescence_type`, `fruit_type`, `life_form_type`,
`stem_hair_type`, `origin`, `island_type`.
