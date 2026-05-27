# V2 — Botanical Trait Ontology

A standalone, explorable ontology of botanical traits, controlled vocabularies,
and recorded fields. The ontology YAML in `ontology/` is the **sole source of
truth** — hand-edited, with a query tool on top.

The goal is an editable data store plus a query tool, so that **both humans and
an extraction agent** can ask things like *"what are the allowed corolla
types?"*, *"what does CORDATE mean?"*, *"map the phrase 'heart-shaped' to a
controlled value"*, or *"what fields do I record for the male calyx?"*

## What's in the ontology

Every recorded variable has one of five **datatypes**:

| Datatype | Example | What it carries |
|----------|---------|-----------------|
| **categorical** | `leaf_shape_type`, `corolla_type` | a controlled vocabulary of **values**, each with a **definition**, **synonyms** (raw OCR phrasings → controlled term), **parents** (hierarchy), and **status** (`CategoricalTrait`) |
| **quantitative** | `leaf_length`, `calyx_dimensions` | a number with units — a single measurement or a length+width dimension; carries `kind` (measurement / dimensions / count) and `unit_hint` (`FieldTrait`) |
| **text** | `corolla_color`, `perianth_inner_color`, `common_name` | a free-form string (`FieldTrait`, `kind=text`) |
| **list** | `ploidy`, `chromosome_number`, `plate_references` | a list of values (`FieldTrait`, `kind=list`) |

Quantitative, text, and list fields all share one storage class
(`FieldTrait`, formerly `MeasurementTrait` — alias kept) and are grouped under a
**Group** (`leaf_morphology`, etc.); groups can have a `parent` (e.g.
`leaflet_morphology` under `leaf_morphology`).

Identity / provenance is split into two groups: **`taxon_identity`** (the
organism — names, major group) and **`source_document`** (non-trait provenance —
page number, plate references).

Current size: **15 groups · 24 categorical traits (265 values) · 100 fields
(85 quantitative + 12 text + 3 list)**. See `python3 -m trait_ontology stats`.

Every non-categorical field is tagged with **structure** (calyx, corolla,
leaf…), **sex** (male / female / neutral), and **position** (inner, outer, upper,
lower, tube, lobe…), so an agent can ask *"what fields do I record for the male
calyx?"* (`list --structure calyx`, or `--sex male` to narrow).

## Layout

```
V2/
├── ontology/                 # the data — the sole source of truth (hand-edited YAML)
│   ├── groups.yaml           # groups (all top-level)
│   ├── measurements.yaml     # non-categorical fields (quantitative/text/list/path)
│   └── categorical/          # one YAML file per categorical trait
│       ├── leaf_shape.yaml
│       ├── corolla_type.yaml
│       └── ...
├── trait_ontology/           # the lookup tool (loader + query API + CLI)
│   ├── models.py             # dataclasses
│   ├── ontology.py           # load_ontology() + TraitOntology query methods
│   └── cli.py                # command-line explorer
├── extraction/               # extraction-time helpers for the agent
│   ├── models.py             # Pydantic group models, generated from the ontology
│   └── writer.py             # save_group(...) writes parsed/<f>/<g>/<sp>/<group>.json
├── parsed/                   # output directory: one JSON file per group per species
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt        # just PyYAML
```

## CLI usage

Run from the `V2/` directory. Two verbs cover all exploration —
**`list`** (show any node, or filter fields) and **`search`** (find) — plus a few
task verbs. See `USAGE.md` for a fuller guide.

```bash
# list — show any node (group / trait / field / value), or filter fields
python3 -m trait_ontology list                              # all groups
python3 -m trait_ontology list leaf_morphology              # a group: traits + fields
python3 -m trait_ontology list leaf_shape_type              # a trait: its values
python3 -m trait_ontology list leaf_shape_type CORDATE      # a single value
python3 -m trait_ontology list fruit_diameter               # a field: its detail
python3 -m trait_ontology list --structure calyx            # checklist for a body part
python3 -m trait_ontology list --structure calyx --sex male # narrowed to male
python3 -m trait_ontology list --structures                 # valid structure names
python3 -m trait_ontology list --positions                  # valid position names

# search — find anything matching a keyword (name / synonym / definition)
python3 -m trait_ontology search calyx
python3 -m trait_ontology search "heart-shaped"

# extraction tasks
python3 -m trait_ontology resolve leaf_shape_type "heart-shaped"   # -> CORDATE
python3 -m trait_ontology resolve-any "bell-shaped"               # -> corolla_type.CAMPANULATE

# utilities
python3 -m trait_ontology stats
python3 -m trait_ontology check

# add --json to ANY command for machine-readable output (for agents/scripts)
python3 -m trait_ontology --json list leaf_shape_type CORDATE
```

## Python API

```python
from trait_ontology import load_ontology

onto = load_ontology()

onto.list_traits()                              # discover what's extractable
trait = onto.get_trait("leaf_shape_type")       # full CategoricalTrait
trait.values[0].definition                      # botanical definitions

onto.get_value("corolla_type", "TUBULAR")
onto.resolve_value("leaf_shape_type", "heart-shaped")   # synonym -> CORDATE
onto.resolve_anywhere("bell-shaped")            # which trait + value?
onto.children("OVATE", "leaf_shape_type")       # hierarchy
onto.allowed_values("fruit_type")               # ['ACHENE', 'BERRY', ...]
onto.vocabulary_prompt("leaf_shape_type")       # inject into an LLM prompt
```

## How an extraction agent uses this

The methods are designed for an agent loop:

1. **Discover** — `list_groups()` / `list_traits()` to learn what can be extracted.
2. **Get the vocabulary** — `allowed_values(trait)` (or `show <trait>`) returns
   the allowed values *with definitions* to drop into a prompt so the model picks
   from the controlled set instead of inventing terms.
3. **Normalise** — when the source text says "heart-shaped," call
   `resolve_value()` / `resolve_anywhere()` to map it to `CORDATE`.
4. **Disambiguate** — definitions and `children()` help the agent choose between
   close terms (e.g. OVATE vs OBOVATE).

## Validating the ontology

After hand-editing the YAML, run the internal consistency check (valid groups,
no duplicate / colliding names, valid parents):

```bash
python3 -m trait_ontology check
```

## Editing / extending the ontology

It's just YAML — edit by hand or have an agent edit it. The `ontology/` files
are the only source of truth.

- **Add a value to a trait:** add an item under `values:` in the trait's file.
- **Add a whole new categorical trait:** drop a new file in `ontology/categorical/`
  with `name`, `description`, `group`, and `values`. Make sure `group` names a
  group defined in `groups.yaml` (membership is derived from this field — no list
  to maintain).
- **Add a new field:** add an entry under `measurements:` in `measurements.yaml`
  with `group`, `kind` (measurement / dimensions / text / list / path),
  `description`, and the `structure` / `sex` / `position` tags.
- **Reuse another trait's vocabulary:** set `same_values_as: <other_trait>`
  instead of repeating the `values:` list (used by the leaflet/juvenile leaf
  traits and the leaf-surface hair traits).
- **Hierarchy:** give a value a `parents: [BROADER_TERM]` list; give a group a
  `parent:` field.
- **Status:** each value has a `status` (`active` / `proposed` / `deprecated`)
  and a free-text `notes` field.

Run `python3 -m trait_ontology check` after editing.

## Notes & open questions for the maintainer

- **Status / origin overlap:** `status` and `origin` both contain `ENDEMIC` and
  `NATURALIZED`. They're kept with a note; you may want to drop them from
  `status`.
- **Structure tags are collapsed to a base part:** sub-variant tags derived from
  field names (e.g. `perianth_tube`, `calyx_lobe`) are folded into their base
  structure (`perianth`, `calyx`) at load time, so `list --structures` and
  `list --structure <name>` always agree on counts. The tube/lobe detail is kept
  in the `position` tag — e.g. `list --structure perianth --position tube`.
- **Synonyms are a starting point** — they're hand-seeded from botanical usage.
  They're the highest-value thing to expand as you see real source phrasings the
  agent fails to map.
