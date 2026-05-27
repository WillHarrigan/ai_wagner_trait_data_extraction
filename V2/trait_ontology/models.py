"""Dataclasses describing the botanical trait ontology.

The ontology has three kinds of entries:

- ``CategoricalTrait``  — a variable with a controlled vocabulary of allowed
  ``TraitValue`` terms (e.g. ``leaf_shape_type`` -> ``OVATE``, ``CORDATE`` ...).
- ``FieldTrait``        — any recorded field that is NOT a controlled vocabulary.
  Its ``datatype`` is one of: ``quantitative`` (a measurement or length+width
  dimension), ``text`` (a free-form string like a color or name), ``list``
  (e.g. chromosome numbers), or ``path`` (filesystem path(s)).
  (``MeasurementTrait`` is a legacy alias for it.)
- ``TraitGroup``        — a group that bundles related traits
  (e.g. ``leaf_morphology`` bundles leaf shape, margin, dimensions ...).

Each kind is intentionally a plain dataclass so the whole ontology round-trips
cleanly to and from YAML and is trivial for an agent to introspect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TraitValue:
    """One allowed term within a categorical trait's controlled vocabulary."""

    name: str  # canonical code, e.g. "CORDATE"
    label: Optional[str] = None  # human label, e.g. "Cordate"
    definition: str = ""  # botanical definition
    synonyms: List[str] = field(default_factory=list)  # alt terms seen in source text
    parents: List[str] = field(default_factory=list)  # broader terms (other value names)
    status: str = "active"  # "active" | "deprecated" | "proposed"
    notes: str = ""

    def matches(self, term: str) -> bool:
        """True if ``term`` refers to this value (by name, label, or synonym)."""
        t = term.strip().lower()
        candidates = [self.name, self.label or "", *self.synonyms]
        return any(t == c.strip().lower() for c in candidates if c)


@dataclass
class CategoricalTrait:
    """A trait whose answer is one (or more) terms from a controlled vocabulary."""

    name: str  # e.g. "leaf_shape_type"
    description: str = ""
    group: Optional[str] = None  # owning TraitGroup name
    multi: bool = True  # may a species carry several values?
    values: List[TraitValue] = field(default_factory=list)

    def value(self, name: str) -> Optional[TraitValue]:
        for v in self.values:
            if v.name.lower() == name.lower():
                return v
        return None

    def resolve(self, term: str) -> Optional[TraitValue]:
        """Map an arbitrary source term to a controlled value via synonyms."""
        for v in self.values:
            if v.matches(term):
                return v
        return None

    @property
    def value_names(self) -> List[str]:
        return [v.name for v in self.values]


# How each fine-grained `kind` rolls up into a top-level datatype bucket that
# is shown to humans/agents. Three buckets:
#   quantitative — numbers with units (lengths, diameters, length+width pairs)
#   text         — free-form strings (colors, names, page number)
#   list         — list-valued notes (ploidy, chromosome numbers)
# (Categorical traits are their own datatype and live in CategoricalTrait.)
KIND_TO_DATATYPE = {
    "measurement": "quantitative",
    "dimensions": "quantitative",
    "count": "quantitative",
    "text": "text",
    "list": "list",
    "path": "path",       # a single filesystem path
    "path_list": "path",  # a list of filesystem paths, e.g. species image files
}


@dataclass
class FieldTrait:
    """A recorded field that is NOT a controlled vocabulary. It is one of four
    datatypes (see ``datatype``):

      - quantitative: a measurement or a length+width dimension (numbers+units)
      - text:         a free-form string (e.g. a color or a name)
      - list:         a list of values (e.g. chromosome numbers)
      - path:         filesystem path(s) (e.g. species image files)

    These are the fields the extractor fills in directly (no fixed vocabulary).
    The ``structure`` / ``sex`` / ``position`` tags let an agent ask
    "what fields do I record for the male calyx?" by filtering on them.
    """

    name: str  # e.g. "male_calyx_lobe_dimensions"
    description: str = ""
    group: Optional[str] = None
    kind: str = "measurement"  # measurement | dimensions | text | list | count | path
    unit_hint: str = ""  # typical units, e.g. "mm", "cm", "count"
    structure: Optional[str] = None  # body part, e.g. "calyx", "corolla"
    sex: str = "neutral"  # "neutral" | "male" | "female"
    position: List[str] = field(default_factory=list)  # inner/outer/upper/lower/tube/lobe...

    @property
    def datatype(self) -> str:
        """Top-level bucket: 'quantitative', 'text', 'list', or 'path'."""
        return KIND_TO_DATATYPE.get(self.kind, "text")

    @property
    def length_column(self) -> str:
        """CSV column for the length (dimensions split into *_length/*_width)."""
        if self.kind == "dimensions":
            return self.name.replace("_dimensions", "_length")
        return self.name

    @property
    def width_column(self) -> Optional[str]:
        if self.kind == "dimensions":
            return self.name.replace("_dimensions", "_width")
        return None


@dataclass
class TraitGroup:
    """A grouping of related traits (e.g. leaf_morphology bundles leaf shape,
    margin, dimensions...). Membership is derived from each trait's own
    ``group``, so the group itself just carries a name, description, and an
    optional ``parent`` for hierarchy."""

    name: str  # e.g. "leaf_morphology"
    description: str = ""
    parent: Optional[str] = None  # broader group, for hierarchy


# Backwards-compatible alias: the class was renamed MeasurementTrait -> FieldTrait
# when text/list fields were recognised as distinct datatypes. Existing code that
# imports MeasurementTrait keeps working.
MeasurementTrait = FieldTrait


@dataclass
class Ontology:
    """The whole ontology: groups, categorical traits, and non-categorical
    fields (``fields``: quantitative / text / list)."""

    groups: Dict[str, TraitGroup] = field(default_factory=dict)
    categorical: Dict[str, CategoricalTrait] = field(default_factory=dict)
    fields: Dict[str, FieldTrait] = field(default_factory=dict)

    @property
    def measurements(self) -> Dict[str, FieldTrait]:
        """Backwards-compatible alias for ``fields``."""
        return self.fields
