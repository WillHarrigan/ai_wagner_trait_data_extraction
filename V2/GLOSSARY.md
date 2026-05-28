# Glossary — terms and how they relate

The vocabulary used throughout the trait ontology, with concrete examples and a
picture of how everything fits together.

## Terms

| Term | What it is | Example |
|------|-----------|---------|
| **Group** | A bucket of related traits/fields (a body region or theme). 15 of them, all top-level. | `leaf_morphology`, `outer_flower_morphology`, `source_document` |
| **Trait** | A single recordable variable. The umbrella term for both a *categorical trait* and a *field* (below). Every trait belongs to one group. | `leaf_shape_type`, `fruit_diameter` |
| **Categorical trait** | A trait answered by picking from a fixed list (a controlled vocabulary). | `leaf_shape_type` (33 allowed values) |
| **Value** | One allowed term in a categorical trait's vocabulary. Carries a **definition**, **synonyms**, and optional **parents**. | `CORDATE`, `OBCORDATE` |
| **Field** | A trait that is *not* a controlled vocabulary — you fill in a number/string directly. Has a **datatype** plus tags. | `male_calyx_tube_length` |
| **Datatype** | What kind of answer a thing takes: `categorical`, `quantitative` (number/measurement), `text` (free string), `list`. | `quantitative` |
| **Structure** | A tag on a field naming the body part it describes (used to filter, e.g. `list --structure calyx`). | `calyx`, `corolla`, `fruit` |
| **Sex** | A tag on a field: `neutral` / `male` / `female` (for unisexual flower parts). | `male` |
| **Position** | A tag on a field: where on the part (`inner`, `outer`, `tube`, `lobe`, `upper`, `lower`…). | `tube` |
| **Synonym** | An alternate phrasing that maps to a value (lets an agent normalize raw book text to a code). | "heart-shaped" → `CORDATE` |
| **Parent** | A broader term on a **value** (forms a value-level hierarchy). The group-level `parent` field is supported by the loader but not currently used — all groups are top-level. | `OBCORDATE`'s parent is `CORDATE` |
| **Status** | Lifecycle of a value: `active`, `proposed` (defined but not yet in use), or `deprecated`. | `proposed` |

## How they relate

```
ONTOLOGY
│
├── GROUP  (15, all top-level)
│     e.g. leaf_morphology, leaf_indumentum, leaflet_morphology,
│          juvenile_leaf_morphology, inflorescence_morphology,
│          bract_involucre_morphology, inflorescence_morphology, ...
│
│   each group contains TRAITS, of two kinds:
│
├── (a) CATEGORICAL TRAIT        ── pick from a fixed vocabulary
│         e.g. leaf_shape_type
│            └── VALUE  (33 of them)
│                  e.g. CORDATE
│                     ├── definition: "Heart-shaped, with a notch at the base."
│                     ├── synonyms:  ["heart-shaped", ...]   → for normalizing book text
│                     └── parents:   [ ]        (OBCORDATE has parent → CORDATE)
│
└── (b) FIELD                    ── fill in a number / string directly
          e.g. male_calyx_tube_length
             ├── datatype:  quantitative   (or text / list)
             ├── structure: calyx          ┐
             ├── sex:       male           ├─ tags used for filtering
             └── position:  [tube]         ┘
```

## The one distinction that trips people up

A **trait** is the umbrella for *both* categorical traits and fields:

```
                       TRAIT (a recordable variable)
                      /                              \
        CATEGORICAL TRAIT                          FIELD
   (answer = a VALUE from a list)        (answer = number / text)
   datatype: categorical                 datatype: quantitative|text|list
   has: values (definition,              has: structure, sex, position tags
        synonyms, parents)
```

## How the commands map onto these terms

| Command | Operates on |
|---------|-------------|
| `list` | all 15 **groups** (top-level list) |
| `list <group>` | a **group**: its traits + fields |
| `list <trait>` | a **categorical trait**: its **values** (definitions, synonyms) |
| `list <trait> <VALUE>` | one **value** + its narrower terms |
| `list <field>` | a **field**: datatype + structure / sex / position |
| `list --structure calyx` | filters **fields** (and pulls in the matching **categorical trait**) by their **structure** tag |
| `list --structures` | lists the **structure** names |
| `search <kw>` | matches a keyword against **names, synonyms, definitions** |
| `resolve <trait> "phrase"` | maps a **synonym** to its **value** within one trait |
| `resolve-any "phrase"` | maps a **synonym** to its **value** across all traits |

`list` is the single verb for showing any node — give it a name to drill in, or
flags to filter. See `USAGE.md` for examples and `COMMANDS.md` for the design.

