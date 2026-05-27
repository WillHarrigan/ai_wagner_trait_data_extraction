"""Disk-writer for per-group extraction results.

Each group is saved as its own JSON file under
``parsed/<family>/<genus>/<species>/<group>.json``. Family / genus / species
come from the extraction input (not extracted), and are lowercased for the path
to match the project's `family_genus_species` key convention.

The JSON is the model's full ``model_dump`` — every field present, with
unset ones written as ``null``. Predictable schema for downstream consumers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


DEFAULT_PARSED_DIR = "parsed"


def species_dir(family: str, genus: str, species: str, base: str | Path = DEFAULT_PARSED_DIR) -> Path:
    """The directory for one species' parsed JSON files. Names are lowercased
    so paths are stable regardless of the casing the input uses."""
    return (
        Path(base)
        / family.strip().lower()
        / genus.strip().lower()
        / species.strip().lower()
    )


def save_group(
    group_name: str,
    model: BaseModel,
    family: str,
    genus: str,
    species: str,
    *,
    base: str | Path = DEFAULT_PARSED_DIR,
) -> Path:
    """Write one group's extracted data to ``<base>/<family>/<genus>/<species>/<group_name>.json``.

    Returns the path written. The directory is created if it doesn't exist.

    The JSON is the model's full dump (including ``null`` for unset fields), so
    every group file has a predictable, complete schema.
    """
    if not isinstance(model, BaseModel):
        raise TypeError(
            f"save_group expects a Pydantic BaseModel for `model`, got {type(model).__name__}"
        )

    out_dir = species_dir(family, genus, species, base=base)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{group_name}.json"
    out_path.write_text(
        model.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return out_path
