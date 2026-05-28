"""Load the YAML ontology and provide a query API for humans and agents.

Typical use::

    from trait_ontology import load_ontology
    onto = load_ontology()

    onto.list_traits()                  # every trait name + kind + group
    onto.get_trait("leaf_shape")        # full categorical trait w/ values
    onto.get_value("leaf_shape", "CORDATE")
    onto.resolve_value("leaf_shape", "heart-shaped")   # synonym -> CORDATE
    onto.search("lance")                # fuzzy search across traits/values
    onto.children("OVATE", "leaf_shape")  # narrower terms via hierarchy

The design goal is that an extraction agent can call these methods to (a)
discover what is extractable, (b) see the allowed vocabulary + definitions for a
trait, and (c) normalise raw text into controlled values.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .models import (
    CategoricalTrait,
    FieldTrait,
    MeasurementTrait,
    Ontology,
    TraitGroup,
    TraitValue,
)

# Default location: the sibling ``ontology/`` directory next to this package.
DEFAULT_ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_categorical(name: str, data: dict) -> CategoricalTrait:
    values = [
        TraitValue(
            name=v["name"],
            label=v.get("label"),
            definition=v.get("definition", ""),
            synonyms=v.get("synonyms", []) or [],
            parents=v.get("parents", []) or [],
            status=v.get("status", "active"),
            notes=v.get("notes", ""),
        )
        for v in data.get("values", [])
    ]
    return CategoricalTrait(
        name=name,
        description=data.get("description", ""),
        group=data.get("group"),
        multi=data.get("multi", True),
        values=values,
    )


class TraitOntology:
    """Query wrapper around an :class:`Ontology`."""

    def __init__(self, onto: Ontology, source_dir: Optional[Path] = None):
        self._onto = onto
        self.source_dir = source_dir

    # -- core accessors ----------------------------------------------------
    @property
    def categorical(self) -> Dict[str, CategoricalTrait]:
        return self._onto.categorical

    @property
    def fields(self) -> Dict[str, FieldTrait]:
        """Non-categorical fields (quantitative / text / list)."""
        return self._onto.fields

    @property
    def measurements(self) -> Dict[str, FieldTrait]:
        """Legacy alias for :pyattr:`fields`."""
        return self._onto.fields

    @property
    def groups(self) -> Dict[str, TraitGroup]:
        return self._onto.groups

    # -- discovery ---------------------------------------------------------
    def list_traits(self, datatype: Optional[str] = None) -> List[dict]:
        """List every trait with its datatype and group. ``datatype`` filters to
        one of: ``categorical``, ``quantitative``, ``text``, ``list``.
        (``measurement`` is accepted as a legacy alias for ``quantitative``.)"""
        want = "quantitative" if datatype == "measurement" else datatype
        out: List[dict] = []
        if want in (None, "categorical"):
            for t in self.categorical.values():
                out.append(
                    {
                        "name": t.name,
                        "datatype": "categorical",
                        "group": t.group,
                        "n_values": len(t.values),
                    }
                )
        for m in self.fields.values():
            if want in (None, m.datatype):
                out.append(
                    {
                        "name": m.name,
                        "datatype": m.datatype,
                        "kind": m.kind,
                        "group": m.group,
                    }
                )
        return sorted(out, key=lambda d: (d["group"] or "", d["name"]))

    def list_groups(self) -> List[dict]:
        return [
            {
                "name": g.name,
                "description": g.description,
                "parent": g.parent,
                "n_categorical": len(self.categorical_in_group(g.name)),
                "n_measurement": len(self.measurements_in_group(g.name)),
            }
            for g in self.groups.values()
        ]

    # -- traits ------------------------------------------------------------
    def get_trait(self, name: str) -> Optional[object]:
        """Return a categorical or measurement trait by name (categorical wins)."""
        return self.categorical.get(name) or self.measurements.get(name)

    def get_group(self, name: str) -> Optional[TraitGroup]:
        return self.groups.get(name)

    def subgroups(self, group: str) -> List[TraitGroup]:
        """Child groups whose ``parent`` is ``group``."""
        return sorted(
            (g for g in self.groups.values() if g.parent == group),
            key=lambda g: g.name,
        )

    def classify(self, name: str) -> Optional[str]:
        """What kind of node is ``name``: 'group', 'trait', 'field', or None."""
        if name in self.groups:
            return "group"
        if name in self.categorical:
            return "trait"
        if name in self.fields:
            return "field"
        return None

    def traits_with_value(self, value: str) -> List[str]:
        """Names of categorical traits that contain a value named ``value``."""
        return [t.name for t in self.categorical.values() if t.value(value)]

    def categorical_in_group(self, group: str) -> List[CategoricalTrait]:
        return sorted(
            (t for t in self.categorical.values() if t.group == group),
            key=lambda t: t.name,
        )

    def measurements_in_group(self, group: str) -> List[MeasurementTrait]:
        return sorted(
            (m for m in self.measurements.values() if m.group == group),
            key=lambda m: m.name,
        )

    def traits_in_group(self, group: str) -> List[object]:
        if group not in self.groups:
            return []
        return [*self.categorical_in_group(group), *self.measurements_in_group(group)]

    # -- fields by structure / sex / position -----------------------------
    def list_structures(self) -> List[dict]:
        """Every body structure that has recorded fields, with field counts."""
        counts: Dict[str, int] = {}
        for m in self.measurements.values():
            if m.structure:
                counts[m.structure] = counts.get(m.structure, 0) + 1
        return sorted(
            ({"structure": s, "n_fields": n} for s, n in counts.items()),
            key=lambda d: d["structure"],
        )

    def list_positions(self) -> List[dict]:
        """Every position tag that appears on fields, with field counts."""
        counts: Dict[str, int] = {}
        for m in self.measurements.values():
            for p in m.position:
                counts[p] = counts.get(p, 0) + 1
        return sorted(
            ({"position": p, "n_fields": n} for p, n in counts.items()),
            key=lambda d: d["position"],
        )

    def fields_for(
        self,
        structure: Optional[str] = None,
        sex: Optional[str] = None,
        position: Optional[str] = None,
        group: Optional[str] = None,
        datatype: Optional[str] = None,
    ) -> List[FieldTrait]:
        """All recorded fields matching the given filters.

        This answers "what do I record for the male calyx?":
            onto.fields_for(structure="calyx", sex="male")

        ``structure`` matches as a substring so ``structure="calyx"`` also
        returns calyx_tube / calyx_lobe fields. ``sex`` / ``position`` / ``group``
        / ``datatype`` are exact (position matches if it is in the field's
        position list; datatype is quantitative / text / list).
        """
        out = []
        for m in self.fields.values():
            if structure and (not m.structure or structure not in m.structure):
                continue
            if sex and m.sex != sex:
                continue
            if position and position not in m.position:
                continue
            if group and m.group != group:
                continue
            if datatype and m.datatype != datatype:
                continue
            out.append(m)
        return sorted(out, key=lambda m: m.name)

    def categorical_for_structure(self, structure: str) -> List[CategoricalTrait]:
        """Categorical traits belonging to a structure (matched by trait name or
        its group containing the structure word). Categorical traits carry no
        ``structure`` tag, so they must be matched this way rather than via
        :meth:`fields_for`."""
        return sorted(
            (t for t in self.categorical.values()
             if structure in t.name or (t.group and structure in t.group)),
            key=lambda t: t.name,
        )

    # -- values ------------------------------------------------------------
    def get_value(self, trait: str, value: str) -> Optional[TraitValue]:
        t = self.categorical.get(trait)
        return t.value(value) if t else None

    def resolve_value(self, trait: str, term: str) -> Optional[TraitValue]:
        """Normalise a raw source ``term`` to a controlled value via synonyms."""
        t = self.categorical.get(trait)
        return t.resolve(term) if t else None

    def resolve_anywhere(self, term: str) -> List[dict]:
        """Resolve ``term`` against every categorical trait. Useful when the
        agent has a word but doesn't yet know which trait it belongs to."""
        hits = []
        for t in self.categorical.values():
            v = t.resolve(term)
            if v:
                hits.append({"trait": t.name, "value": v.name, "via": "synonym/label"})
        return hits

    # -- hierarchy ---------------------------------------------------------
    def children(self, value: str, trait: str) -> List[TraitValue]:
        """Narrower terms: values whose ``parents`` include ``value``."""
        t = self.categorical.get(trait)
        if not t:
            return []
        return [v for v in t.values if value in v.parents]

    def parents(self, value: str, trait: str) -> List[TraitValue]:
        t = self.categorical.get(trait)
        v = t.value(value) if t else None
        if not v:
            return []
        return [t.value(p) for p in v.parents if t.value(p)]

    # -- search ------------------------------------------------------------
    def search(self, query: str) -> List[dict]:
        """Substring search across names, synonyms, definitions, and
        descriptions, over groups + traits + fields + values. Each hit records
        ``match`` = where it matched (name / synonym / definition / description),
        with name matches ranked first."""
        q = query.strip().lower()
        results: List[dict] = []

        def where(name_hit, syn_hit, def_hit, desc_hit) -> Optional[str]:
            if name_hit:
                return "name"
            if syn_hit:
                return "synonym"
            if def_hit:
                return "definition"
            if desc_hit:
                return "description"
            return None

        # groups
        for g in self.groups.values():
            m = where(q in g.name.lower(), False, False, q in (g.description or "").lower())
            if m:
                results.append({"type": "group", "name": g.name, "match": m})

        # categorical traits + their values
        for t in self.categorical.values():
            m = where(q in t.name.lower(), False, False, q in (t.description or "").lower())
            if m:
                results.append({"type": "trait", "name": t.name, "group": t.group, "match": m})
            for v in t.values:
                m = where(
                    q in v.name.lower() or q in (v.label or "").lower(),
                    any(q in s.lower() for s in v.synonyms),
                    q in (v.definition or "").lower(),
                    False,
                )
                if m:
                    results.append({
                        "type": "value", "trait": t.name, "value": v.name,
                        "match": m, "definition": v.definition,
                    })

        # non-categorical fields
        for f in self.fields.values():
            m = where(
                q in f.name.lower(),
                any(q in s.lower() for s in f.synonyms),
                False,
                q in (f.description or "").lower(),
            )
            if m:
                results.append({
                    "type": "field", "name": f.name, "group": f.group,
                    "datatype": f.datatype, "match": m,
                })

        # name matches first, then synonym, definition, description
        order = {"name": 0, "synonym": 1, "definition": 2, "description": 3}
        results.sort(key=lambda r: order.get(r["match"], 9))
        return results

    # -- agent-friendly exports -------------------------------------------
    def allowed_values(self, trait: str) -> List[str]:
        """Just the canonical value names for a trait (for prompt injection)."""
        t = self.categorical.get(trait)
        return t.value_names if t else []

    def vocabulary_prompt(self, trait: str) -> str:
        """A compact, prompt-ready block: each value with its definition. This
        is what you'd inject into an extraction agent's system prompt."""
        t = self.categorical.get(trait)
        if not t:
            return f"(no trait named {trait!r})"
        lines = [f"Trait: {t.name} — {t.description}".rstrip(" —"), "Allowed values:"]
        for v in t.values:
            if v.status != "active":
                continue
            syn = f" (aka {', '.join(v.synonyms)})" if v.synonyms else ""
            defn = f" — {v.definition}" if v.definition else ""
            lines.append(f"  - {v.name}{syn}{defn}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def load_ontology(ontology_dir: Optional[os.PathLike] = None) -> TraitOntology:
    """Load the ontology from ``ontology_dir`` (defaults to the bundled dir).

    Directory layout::

        ontology/
          groups.yaml              # trait groups + hierarchy
          measurements.yaml        # non-categorical fields (quantitative/text/list/path)
          categorical/*.yaml       # one file per categorical trait
    """
    base = Path(ontology_dir) if ontology_dir else DEFAULT_ONTOLOGY_DIR
    onto = Ontology()

    # groups
    groups_path = base / "groups.yaml"
    if groups_path.exists():
        for name, data in (_load_yaml(groups_path).get("groups") or {}).items():
            onto.groups[name] = TraitGroup(
                name=name,
                description=data.get("description", ""),
                parent=data.get("parent"),
            )

    # measurements
    meas_path = base / "measurements.yaml"
    if meas_path.exists():
        raw_fields = (_load_yaml(meas_path).get("measurements") or {})

        def _clean(structure):
            return None if structure in ("~", "", None) else structure

        # Pass 1: the set of all base structure tags present.
        all_structures = {
            _clean(d.get("structure")) for d in raw_fields.values()
            if _clean(d.get("structure"))
        }

        def collapse(structure):
            """Fold a sub-variant tag (e.g. ``perianth_tube``) down to its base
            (``perianth``) when the prefix is itself a structure. Keeps the
            ``--structures`` list and the ``--structure`` filter consistent.
            The fine detail (tube/lobe) is preserved separately in `position`."""
            if not structure:
                return structure
            parts = structure.split("_")
            for i in range(len(parts) - 1, 0, -1):
                prefix = "_".join(parts[:i])
                if prefix in all_structures:
                    return prefix
            return structure

        for name, data in raw_fields.items():
            onto.fields[name] = FieldTrait(
                name=name,
                description=data.get("description", ""),
                group=data.get("group"),
                kind=data.get("kind", "measurement"),
                unit_hint=data.get("unit_hint", ""),
                structure=collapse(_clean(data.get("structure"))),
                sex=data.get("sex", "neutral"),
                position=data.get("position", []) or [],
                synonyms=data.get("synonyms", []) or [],
            )

    # categorical traits (one file per trait). Two passes so a trait can borrow
    # another trait's value list via `same_values_as` regardless of file order.
    cat_dir = base / "categorical"
    raw: Dict[str, dict] = {}
    if cat_dir.exists():
        for path in sorted(cat_dir.glob("*.yaml")):
            data = _load_yaml(path)
            name = data.get("name") or path.stem
            raw[name] = data

    for name, data in raw.items():
        borrow = data.get("same_values_as")
        if borrow and not data.get("values"):
            src = raw.get(borrow, {})
            data = {**data, "values": src.get("values", [])}
        onto.categorical[name] = _build_categorical(name, data)

    return TraitOntology(onto, source_dir=base)
