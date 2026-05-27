"""Extraction-time code (separate from the lookup ontology in
``trait_ontology``). The agent builds a Pydantic model per group and uses
:func:`save_group` to write it to disk under ``parsed/<family>/<genus>/<species>/``.
"""

from .models import (
    CATEGORICAL_ENUMS,
    Dimensions,
    GROUP_MODELS,
    Measurements,
)
from .writer import DEFAULT_PARSED_DIR, save_group, species_dir

__all__ = [
    "CATEGORICAL_ENUMS",
    "Dimensions",
    "GROUP_MODELS",
    "Measurements",
    "save_group",
    "species_dir",
    "DEFAULT_PARSED_DIR",
]
