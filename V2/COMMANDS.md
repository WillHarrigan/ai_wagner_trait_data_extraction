# CLI command design

Goal: a small, predictable command surface for an **agent doing structured
extraction from a book** (and for humans exploring the taxonomy). Two verbs
cover all exploration; a few task verbs cover extraction. No data changes — this
is purely the CLI surface.

## The two exploration verbs

### `list` — show any node, or filter
Give it a name to show that node (group / trait / field / value); give it flags
to filter fields across the taxonomy.

```
list                                → all groups
list <group>                        → traits + fields in that group
list <trait>                        → values of that trait
list <a>,<b>,<c>                    → multi-name: one call, one section per name
list --structure calyx              → the calyx checklist: categorical trait(s)
                                      + measurement fields, grouped by sex
list --structure calyx --sex male   → narrowed to male fields (omits categorical)
list --structures                   → the valid structure names
list --positions                    → the valid position names
list --position tube                → every tube field
list --group fruit_morphology       → everything in a group (same as `list <group>`)
```
Filters: `--structure`, `--sex`, `--position`, `--group`.
`list --structure <part>` includes the categorical trait (e.g. `fruit_type`) as
well as the measurement fields — it is the full "what to record" checklist for a
body part. Adding `--sex`/`--position` narrows to fields only. Each field's
datatype (quantitative / text / list) is shown inline in `[brackets]`;
there is no datatype filter — the workflow is body-part driven, not type driven.
(Absorbs the old `groups`, `group`, `list`, `fields`, `structures`, `fields-for`.)

### `search <keyword>` — find anything matching
Substring match across **name, synonyms, and definitions**, over fields +
traits + values. Output shows what matched and where.

```
search calyx →
  field   calyx_dimensions       (name)
  field   male_calyx_tube_length (name)
  value   CORDATE  in leaf_shape_type  (synonym: heart-shaped)

search "floret, ray color, pappus"   →  BATCH form: one section per keyword
                                        in one call (dict keyed by keyword
                                        in --json mode)
```

`list <name>` shows the full detail of one node:
```
list <group>             → group: description + traits + fields
                           (all 15 groups are top-level; no hierarchy)
list <trait>             → categorical trait: description + all values
list <trait> <VALUE>     → value: definition, synonyms, parents, narrower terms
list <field>             → field: datatype, description, structure / sex / position
list a,b,c               → batch: comma-separated names, one section per name
                           (dict keyed by name in `--json` mode)
```
A bare value name that exists in several traits errors and lists the matches
(value detail requires the trait, e.g. `list leaf_shape_type CORDATE`).
(Absorbs the old `show`, `value`, `children`, and `describe`.)

## Extraction task verbs (kept — agent-critical, not browsing)

```
resolve <trait> "phrase"        → normalize one phrase to a code within one trait
resolve <trait> "p1, p2, p3"    → BATCH: same trait, several phrases, ONE call
resolve-any "phrase"            → normalize a phrase across all traits
resolve-any "p1, p2, p3"        → BATCH form for resolve-any too
```

## Utility

```
stats     → summary counts
check     → validate the ontology YAML for internal consistency
```

## How an extraction agent uses it

1. **Discover** what's recordable — `list`, `list <group>`.
2. **Scope a body part** seen in the text — `list --structure calyx` for the full
   checklist, or add `--sex male` to narrow it.
3. **Normalize** a phrase from the book — `resolve` / `resolve-any`
   ("heart-shaped" → CORDATE).
4. **Disambiguate** a term — `list <trait> <VALUE>` for definition + synonyms
   + narrower terms.

## Migration (old → new)

| Old command | New |
|-------------|-----|
| `groups` | `list` |
| `group <g>` | `list <g>` |
| `fields --…` | `list --…` |
| `structures` | `list --structures` |
| `show <trait>` / `describe <trait>` | `list <trait>` |
| `value <trait> <v>` / `describe <trait> <v>` | `list <trait> <v>` |
| `children <v> <trait>` | shown within `list <trait> <v>` |
| `record-sheet` / `fields-for` | `list --structure <part>` |
| `resolve`, `resolve-any`, `stats`, `check` | unchanged |
