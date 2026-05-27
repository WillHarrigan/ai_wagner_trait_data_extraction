"""Botanical trait ontology for the Wagner extraction project (V2).

A standalone, explorable, agent-friendly taxonomy of the traits, controlled
vocabularies, and recorded fields. The ontology YAML in ``ontology/`` is the
sole source of truth.
"""

from .models import (
    CategoricalTrait,
    FieldTrait,
    MeasurementTrait,
    Ontology,
    TraitGroup,
    TraitValue,
)
from .ontology import TraitOntology, load_ontology

__all__ = [
    "load_ontology",
    "TraitOntology",
    "Ontology",
    "TraitGroup",
    "CategoricalTrait",
    "FieldTrait",
    "MeasurementTrait",  # legacy alias for FieldTrait
    "TraitValue",
]
