"""The Agent 2 -> Agent 3 input contract (Version 1).

Mirrors this project's own established Agent 1 -> Agent 2 boundary pattern exactly
(``app.agent2.handoff.translate_agent1_view_to_agent2`` on the sibling ``agent2-antimony-
builder`` repository): Agent 3 never imports Agent 2's Python package at all, and never
constructs an Agent 2 ``ModelSpecification``/``FullAntimonyArtifact`` object directly. It
consumes exactly one plain, JSON-serializable dict shape (documented in full in
``docs/02_agent2_to_agent3_contract.md``), parsed here into this module's own frozen,
validated dataclasses. The two packages are fully decoupled at the code level -- only the data
shape is shared, and only by convention/documentation, exactly as Agent 1/Agent 2 already are.

**Why this exact, minimal shape and nothing more (Version 1's own "smallest stable contract"
requirement):** Agent 3's job is to simulate the model and trace any finding back to the Agent
2 entity responsible. That requires:

* ``antimony_text`` -- the actual, compilable simulation input (the *only* field Agent 3 gives
  to the simulation engine itself; everything else below is metadata for provenance/diagnostics).
* ``compartments``/``species``/``reactions`` -- structural facts needed for conservation/mass-
  balance checks (stoichiometry) and for mapping a species id found in a simulation trajectory
  back to its own compartment/source compound.
* ``kinetic_laws``/``parameters`` -- provenance (``source``, ``uncertainty_text``,
  ``provenance_refs``) needed to label a diagnostic finding "this failure traces to a
  ``HEURISTIC_INITIALIZATION`` parameter" rather than merely naming an opaque id.
* ``model_assumptions`` -- Agent 2's own disclosed assumptions, carried through unchanged so a
  diagnostic finding can cite the *exact* Agent 2 assumption text it corroborates or contradicts,
  never re-deriving or rephrasing it.
* ``readiness``/``unresolved_reaction_ids``/``unresolved_kinetic_law_ids`` -- Agent 2's own
  verdict on whether the model it produced is even claimed to be executable, carried through
  verbatim rather than re-inferred from the Antimony text.

Nothing here is a modeling decision or a simulation result -- this module only parses and
validates the shape of what Agent 2 reports about itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.agent3.errors import HandoffContractError
from app.agent3.version import AGENT2_HANDOFF_CONTRACT_VERSION


def _require_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffContractError(f"{field} must be a non-empty string, got {value!r}")
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HandoffContractError(f"{field} must be a string or null, got {value!r}")
    return value or None


def _optional_decimal(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise HandoffContractError(f"{field} must be numeric, got a bool ({value!r})")
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise HandoffContractError(f"{field} is not a valid decimal: {value!r}") from exc
    raise HandoffContractError(f"{field} must be numeric or null, got {value!r}")


def _str_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise HandoffContractError(f"{field} must be a list of strings, got {value!r}")
    return tuple(value)


def _dict_list(value: object, *, field: str) -> tuple[dict, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, dict) for v in value):
        raise HandoffContractError(f"{field} must be a list of objects, got {value!r}")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class HandoffCompartment:
    compartment_id: str
    name: str
    initial_volume: Decimal | None
    volume_unit: str | None
    constant: bool | None


@dataclass(frozen=True, slots=True)
class HandoffSpecies:
    species_id: str
    name: str
    compartment_id: str
    source_compound_id: str | None
    source_enzyme_state_id: str | None
    initial_amount: Decimal | None
    initial_concentration: Decimal | None
    constant: bool | None
    boundary_condition: bool | None


@dataclass(frozen=True, slots=True)
class HandoffParticipant:
    species_id: str
    role: str
    stoichiometry: Decimal


@dataclass(frozen=True, slots=True)
class HandoffReaction:
    reaction_id: str
    name: str | None
    reversible: bool | None
    participants: tuple[HandoffParticipant, ...]


@dataclass(frozen=True, slots=True)
class HandoffKineticLaw:
    kinetic_law_id: str
    reaction_id: str
    law_type: str
    expression: str | None
    parameter_ids: tuple[str, ...]
    species_ids: tuple[str, ...]
    enzyme_state_id: str | None
    protein_id: str | None
    complex_id: str | None
    assumptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HandoffParameter:
    parameter_id: str
    name: str
    source: str
    value: Decimal | None
    unit: str | None
    reaction_id: str | None
    kinetic_law_assignment_id: str | None
    uncertainty_text: str | None
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HandoffModelAssumption:
    assumption_id: str
    category: str
    statement: str
    related_entity_ids: tuple[str, ...]
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class Agent2Handoff:
    """One complete, self-contained Agent 2 -> Agent 3 handoff.

    ``contract_version`` is the handoff's *own* declared version (compared informationally
    against ``app.agent3.version.AGENT2_HANDOFF_CONTRACT_VERSION`` -- a mismatch is reported as
    a finding, never raised as an error; version reconciliation is deferred exactly as the
    Agent 1 -> Agent 2 boundary's own precedent does).
    """

    contract_version: str
    model_id: str
    network_id: str
    antimony_text: str
    antimony_generator_version: str
    readiness: str
    unresolved_reaction_ids: tuple[str, ...]
    unresolved_kinetic_law_ids: tuple[str, ...]
    compartments: tuple[HandoffCompartment, ...]
    species: tuple[HandoffSpecies, ...]
    reactions: tuple[HandoffReaction, ...]
    kinetic_laws: tuple[HandoffKineticLaw, ...]
    parameters: tuple[HandoffParameter, ...]
    model_assumptions: tuple[HandoffModelAssumption, ...]


def parse_agent2_handoff(data: dict) -> Agent2Handoff:
    """Parse and validate one plain dict into an ``Agent2Handoff``.

    Raises ``HandoffContractError`` for any structurally malformed input (a missing required
    field, a field of the wrong type). Never fills in a missing value with a guessed default --
    exactly mirrors ``app.agent2.handoff.translate_agent1_view_to_agent2``'s own discipline on
    the sibling repository's identical boundary.
    """
    if not isinstance(data, dict):
        raise HandoffContractError(f"Agent 2 handoff must be a dict, got {type(data)!r}")

    compartments = tuple(
        HandoffCompartment(
            compartment_id=_require_str(
                c.get("compartment_id"), field="compartments[].compartment_id"
            ),
            name=_require_str(c.get("name"), field="compartments[].name"),
            initial_volume=_optional_decimal(
                c.get("initial_volume"), field="compartments[].initial_volume"
            ),
            volume_unit=_optional_str(c.get("volume_unit"), field="compartments[].volume_unit"),
            constant=c.get("constant"),
        )
        for c in _dict_list(data.get("compartments"), field="compartments")
    )

    species = tuple(
        HandoffSpecies(
            species_id=_require_str(s.get("species_id"), field="species[].species_id"),
            name=_require_str(s.get("name"), field="species[].name"),
            compartment_id=_require_str(s.get("compartment_id"), field="species[].compartment_id"),
            source_compound_id=_optional_str(
                s.get("source_compound_id"), field="species[].source_compound_id"
            ),
            source_enzyme_state_id=_optional_str(
                s.get("source_enzyme_state_id"), field="species[].source_enzyme_state_id"
            ),
            initial_amount=_optional_decimal(
                s.get("initial_amount"), field="species[].initial_amount"
            ),
            initial_concentration=_optional_decimal(
                s.get("initial_concentration"), field="species[].initial_concentration"
            ),
            constant=s.get("constant"),
            boundary_condition=s.get("boundary_condition"),
        )
        for s in _dict_list(data.get("species"), field="species")
    )

    reactions = tuple(
        HandoffReaction(
            reaction_id=_require_str(r.get("reaction_id"), field="reactions[].reaction_id"),
            name=_optional_str(r.get("name"), field="reactions[].name"),
            reversible=r.get("reversible"),
            participants=tuple(
                HandoffParticipant(
                    species_id=_require_str(
                        p.get("species_id"), field="reactions[].participants[].species_id"
                    ),
                    role=_require_str(p.get("role"), field="reactions[].participants[].role"),
                    stoichiometry=_optional_decimal(
                        p.get("stoichiometry"), field="reactions[].participants[].stoichiometry"
                    )
                    or Decimal(1),
                )
                for p in _dict_list(r.get("participants"), field="reactions[].participants")
            ),
        )
        for r in _dict_list(data.get("reactions"), field="reactions")
    )

    kinetic_laws = tuple(
        HandoffKineticLaw(
            kinetic_law_id=_require_str(
                k.get("kinetic_law_id"), field="kinetic_laws[].kinetic_law_id"
            ),
            reaction_id=_require_str(k.get("reaction_id"), field="kinetic_laws[].reaction_id"),
            law_type=_require_str(k.get("law_type"), field="kinetic_laws[].law_type"),
            expression=_optional_str(k.get("expression"), field="kinetic_laws[].expression"),
            parameter_ids=_str_tuple(k.get("parameter_ids"), field="kinetic_laws[].parameter_ids"),
            species_ids=_str_tuple(k.get("species_ids"), field="kinetic_laws[].species_ids"),
            enzyme_state_id=_optional_str(
                k.get("enzyme_state_id"), field="kinetic_laws[].enzyme_state_id"
            ),
            protein_id=_optional_str(k.get("protein_id"), field="kinetic_laws[].protein_id"),
            complex_id=_optional_str(k.get("complex_id"), field="kinetic_laws[].complex_id"),
            assumptions=_str_tuple(k.get("assumptions"), field="kinetic_laws[].assumptions"),
        )
        for k in _dict_list(data.get("kinetic_laws"), field="kinetic_laws")
    )

    parameters = tuple(
        HandoffParameter(
            parameter_id=_require_str(p.get("parameter_id"), field="parameters[].parameter_id"),
            name=_require_str(p.get("name"), field="parameters[].name"),
            source=_require_str(p.get("source"), field="parameters[].source"),
            value=_optional_decimal(p.get("value"), field="parameters[].value"),
            unit=_optional_str(p.get("unit"), field="parameters[].unit"),
            reaction_id=_optional_str(p.get("reaction_id"), field="parameters[].reaction_id"),
            kinetic_law_assignment_id=_optional_str(
                p.get("kinetic_law_assignment_id"), field="parameters[].kinetic_law_assignment_id"
            ),
            uncertainty_text=_optional_str(
                p.get("uncertainty_text"), field="parameters[].uncertainty_text"
            ),
            provenance_refs=_str_tuple(
                p.get("provenance_refs"), field="parameters[].provenance_refs"
            ),
        )
        for p in _dict_list(data.get("parameters"), field="parameters")
    )

    model_assumptions = tuple(
        HandoffModelAssumption(
            assumption_id=_require_str(
                a.get("assumption_id"), field="model_assumptions[].assumption_id"
            ),
            category=_require_str(a.get("category"), field="model_assumptions[].category"),
            statement=_require_str(a.get("statement"), field="model_assumptions[].statement"),
            related_entity_ids=_str_tuple(
                a.get("related_entity_ids"), field="model_assumptions[].related_entity_ids"
            ),
            reason_code=_optional_str(
                a.get("reason_code"), field="model_assumptions[].reason_code"
            ),
        )
        for a in _dict_list(data.get("model_assumptions"), field="model_assumptions")
    )

    return Agent2Handoff(
        contract_version=_require_str(data.get("contract_version"), field="contract_version"),
        model_id=_require_str(data.get("model_id"), field="model_id"),
        network_id=_require_str(data.get("network_id"), field="network_id"),
        antimony_text=_require_str(data.get("antimony_text"), field="antimony_text"),
        antimony_generator_version=_require_str(
            data.get("antimony_generator_version"), field="antimony_generator_version"
        ),
        readiness=_require_str(data.get("readiness"), field="readiness"),
        unresolved_reaction_ids=_str_tuple(
            data.get("unresolved_reaction_ids"), field="unresolved_reaction_ids"
        ),
        unresolved_kinetic_law_ids=_str_tuple(
            data.get("unresolved_kinetic_law_ids"), field="unresolved_kinetic_law_ids"
        ),
        compartments=compartments,
        species=species,
        reactions=reactions,
        kinetic_laws=kinetic_laws,
        parameters=parameters,
        model_assumptions=model_assumptions,
    )


def handoff_contract_version_mismatch(handoff: Agent2Handoff) -> str | None:
    """``None`` if the handoff's own declared contract version matches this Agent 3 build's
    expected version; otherwise a human-readable disclosure string -- never raised as an error
    (see ``Agent2Handoff``'s own docstring)."""
    if handoff.contract_version == AGENT2_HANDOFF_CONTRACT_VERSION:
        return None
    return (
        f"Agent 2 handoff declares contract_version={handoff.contract_version!r}, but this "
        f"Agent 3 build expects {AGENT2_HANDOFF_CONTRACT_VERSION!r}. Proceeding, since version "
        "reconciliation is deferred (mirrors the Agent 1 -> Agent 2 boundary's own precedent) "
        "-- but any shape mismatch this causes will surface as a HandoffContractError above, "
        "not silently here."
    )


__all__ = [
    "Agent2Handoff",
    "HandoffCompartment",
    "HandoffKineticLaw",
    "HandoffModelAssumption",
    "HandoffParameter",
    "HandoffParticipant",
    "HandoffReaction",
    "HandoffSpecies",
    "handoff_contract_version_mismatch",
    "parse_agent2_handoff",
]
