# ontology_v3 — regenerated categorical vocabularies

Generated from three sources:

1. **`codes_cleaned.tsv`** — the 15 existing trait dropdown lists (the real values).
2. **Expert email** — adds/removes/new groups (see per-file header comments).
3. **`Wagner_glossary.pdf`** — controlled vocabulary for the new groups the email
   named but left value-less (gynoecium, androecium, roots, pollination, calyx).

This folder is **new and standalone** — the live ontology (`../measurements.yaml`,
`../categorical/`, `../groups.yaml`) is unchanged. Nothing loads these yet.

## What changed vs. the old vocabularies

**Contamination removed (the key cleanup):**
- `corolla_type`: removed `DISK`, `RAY` (→ ray/floret structures), `SUBPANICULATE`
  (→ inflorescence_type), `LABELLUM` (→ labellum structure). Added `ACTINOMORPHIC`.

**Values added (expert email):**
- `life_form_type`: + `SUBSHRUB`, + `LIANA`; `VINE` redefined as herbaceous.
- `breeding_type`: + `HERMAPHRODITIC`, `ANDRODIOECIOUS`, `SUBDIOECIOUS`;
  `CLEISTOGAMOUS`/`CHASMOGAMOUS` **moved out** to `pollination_mode`.
- `fruit_type`: + 7 fruit KINDS (SAMARA, SAMAROID, UTRICLE, PYXIS, LOMENT,
  HESPERIDIUM, SIMPLE). The email's FLESHY/DRY/SINGLE_SEEDED/MULTI_SEEDED were
  handled separately — see "Resolved from test_data" below.
- `inflorescence_type`: + `SUBPANICULATE` (moved in from corolla).
- `status`: ensured `ENDANGERED`, `THREATENED`.

**New groups + vocabularies (glossary-sourced):**
- Gynoecium: `ovary_position`, `placentation`, `ovule_type`.
- Androecium: `anther_attachment`, `stamen_fusion`, `staminode_presence`.
- Roots: `root_type`.
- Pollination/mating: `pollination_mode`, `mating_system`.
- Calyx: `calyx_type` (calyx had measurements but no shape/fusion categorical).
- Fruit/seed: `fruit_shape`, `fruit_surface`, `seed_shape`, `seed_surface`.

## Modeling notes

- **Variants share one vocabulary.** juvenile/upper/lower leaf traits reuse the
  base vocab (e.g. `leaf_hair_type` covers upper/lower/juvenile). No per-slice files.
- **Parts are NOT vocabulary values.** Fruit pericarp layers (exocarp/mesocarp/
  endocarp) and seed aril/hilum are PARTS — they belong on the fruit/seed `part:`
  axis in `base_traits_with_axes.yaml`, not as dropdown values here.

## Resolved (decided from data / design)

- **Fruit kinds vs. properties** — checked ~286 fruit descriptions in `test_data/`:
  ~60% do NOT name a fruit type, and "fleshy/dry" always appear as modifiers of a
  type (e.g. "drupe with fleshy mesocarp", "fleshy when young, dry with age"), never
  as standalone tags. Therefore:
  - `fruit_type` is now KINDS ONLY.
  - `FLESHY`/`DRY` moved to new **`fruit_texture`** (optional, set only when stated).
  - Seed count is recorded by the numeric `seeds_per_fruit` field.
- **Pollen** detailed characters intentionally omitted (sparse in Wagner) — pollen
  kept as a measure/text field only.

## Open — needs expert / botanist

- New groups still need **measures** defined in the axes spec (stigma/style/ovary
  dimensions, filament/anther length, root dimensions).
- `fruit_shape`/`fruit_surface`/`seed_*` value lists are reasonable defaults, not
  expert-confirmed — review with botanist.
