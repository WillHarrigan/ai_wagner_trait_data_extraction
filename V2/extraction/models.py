"""Pydantic models for extraction, generated from the V2 ontology.

For each of the 15 trait groups in the ontology, a Pydantic ``BaseModel`` is
generated with one field per categorical trait + non-categorical field belonging
to that group. Categorical traits use ``Enum`` types whose members come straight
from the YAML; every field is ``Optional`` so the agent fills in only what the
passage states.

Generated at import time from :func:`trait_ontology.load_ontology`, so the
models can NEVER drift from the ontology — change the YAML, restart, you're
done.

Typical extraction-time use::

    from extraction.models import GROUP_MODELS, Measurements
    Model = GROUP_MODELS["taxon_identity"]
    obj = Model(common_name="Coriander", description="DICOTS", ...)
    obj.model_dump_json(indent=2)

Note: ``family``, ``genus``, ``species`` are **inputs** to the extraction (they
come with the passage), not extracted fields. They are NOT in any model — they
go into the output directory path instead.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Type

from pydantic import BaseModel, Field, create_model

from trait_ontology import load_ontology


# ---------------------------------------------------------------------------
# Shared measurement / dimension types — carried over from the notebook so the
# extraction format is identical (extract verbatim, no unit conversion).
# ---------------------------------------------------------------------------
class Measurements(BaseModel):
    """A single quantitative value with explicit min/max/extreme bounds and a
    unit copied verbatim from the source passage."""

    min: Optional[float] = None
    max: Optional[float] = None
    extreme_min: Optional[float] = None
    extreme_max: Optional[float] = None
    unit: Optional[str] = None


class Dimensions(BaseModel):
    """A length+width measurement pair (e.g. for a leaf, calyx, fruit)."""

    length: Optional[Measurements] = Field(None, description="Extract length")
    width: Optional[Measurements] = Field(None, description="Extract width")


# ---------------------------------------------------------------------------
# Build one Enum per categorical trait from the ontology values.
# ---------------------------------------------------------------------------
_ONTO = load_ontology()


def _make_enum(trait) -> Type[Enum]:
    """Create a str-Enum for a categorical trait's active values."""
    members = {v.name: v.name for v in trait.values if v.status == "active"}
    return Enum(_to_class(trait.name) + "Enum", members, type=str)


def _to_class(snake: str) -> str:
    """snake_case -> CamelCase for type names."""
    return "".join(part.capitalize() for part in snake.split("_"))


CATEGORICAL_ENUMS: Dict[str, Type[Enum]] = {
    name: _make_enum(t) for name, t in _ONTO.categorical.items()
}


# ---------------------------------------------------------------------------
# Build one Pydantic model per group, with fields drawn from the ontology.
# ---------------------------------------------------------------------------
_KIND_TO_PY = {
    "measurement": Measurements,
    "count": Measurements,
    "dimensions": Dimensions,
    "text": str,
    "list": list,
    "path": str,
    "path_list": list,
}


def _field_type_for_field(field_trait):
    """Map a non-categorical field's `kind` to its Python type."""
    return _KIND_TO_PY.get(field_trait.kind, str)


def _build_group_model(group_name: str) -> Type[BaseModel]:
    """Assemble the Pydantic model for one trait group."""
    fields: Dict[str, tuple] = {}

    # categorical traits -> Optional[List[Enum]] (multi-valued by default)
    for cat in _ONTO.categorical_in_group(group_name):
        EnumCls = CATEGORICAL_ENUMS[cat.name]
        py_type = Optional[List[EnumCls]] if cat.multi else Optional[EnumCls]
        fields[cat.name] = (
            py_type,
            Field(None, description=cat.description or ""),
        )

    # non-categorical fields -> Optional[<mapped type>]
    for m in _ONTO.measurements_in_group(group_name):
        py = _field_type_for_field(m)
        fields[m.name] = (
            Optional[py],
            Field(None, description=m.description or ""),
        )

    model_name = _to_class(group_name) + "Model"
    return create_model(model_name, __base__=BaseModel, **fields)


GROUP_MODELS: Dict[str, Type[BaseModel]] = {
    g: _build_group_model(g) for g in _ONTO.groups
}


# Convenience: expose each model as a module-level attribute too, so callers
# can `from extraction.models import TaxonIdentityModel` if they prefer.
for _g, _model in GROUP_MODELS.items():
    globals()[_model.__name__] = _model


__all__ = [
    "Measurements",
    "Dimensions",
    "CATEGORICAL_ENUMS",
    "GROUP_MODELS",
] + [m.__name__ for m in GROUP_MODELS.values()]
