"""Deterministically re-deriving an Antimony identifier from an Agent 2 entity id.

Agent 2's own Antimony generator (``app.agent2.antimony.naming`` on the sibling
``agent2-antimony-builder`` repository) maps every compartment/species/parameter/reaction id to
a stable, documented Antimony identifier: strip every character outside
``[A-Za-z0-9_]`` (replacing it with ``_``), prefix by structural category (``c_``/``s_``/
``p_``/``J_``), and -- only in the rare case two distinct source ids sanitize to the identical
string -- suffix the losing id(s) with a deterministic ``_2``, ``_3``, ... (sorted by source id).

Agent 3 never imports Agent 2's Python package (see ``app.agent3.handoff``'s own docstring for
why) -- this module re-implements the **documented, published** sanitization rule
independently, purely so a diagnostic finding or a perturbation target (both expressed in
Agent 2's own entity-id terms, from the handoff) can be mapped to the identifier the *already-
compiled* Antimony/SBML model actually uses. It never guesses: every candidate this module
produces is checked against the loaded model's own real identifier list before being used (see
``app.agent3.perturbation``), and a candidate that is not found is reported as an unresolved
target, never silently assumed correct.
"""

from __future__ import annotations

import re
import unicodedata

_INVALID_CHAR = re.compile(r"[^A-Za-z0-9_]")


def sanitize_base(raw: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = _INVALID_CHAR.sub("_", ascii_text)
    if not cleaned or cleaned.strip("_") == "":
        cleaned = "id"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def candidate_parameter_antimony_id(parameter_id: str) -> str:
    return f"p_{sanitize_base(parameter_id)}"


def candidate_species_antimony_id(species_id: str) -> str:
    return f"s_{sanitize_base(species_id)}"


def build_species_antimony_id_map(species_ids: list[str]) -> dict[str, str]:
    """``{candidate_antimony_id: original_species_id}`` for every id in ``species_ids`` --
    the reverse mapping ``app.agent3.simulation``/``app.agent3.diagnostics`` use to label a
    simulated trajectory (keyed by its own real Antimony identifier) back in terms of the
    original Agent 2 entity id every provenance-tracing finding must use.
    """
    return {candidate_species_antimony_id(sid): sid for sid in species_ids}


__all__ = [
    "build_species_antimony_id_map",
    "candidate_parameter_antimony_id",
    "candidate_species_antimony_id",
    "sanitize_base",
]
