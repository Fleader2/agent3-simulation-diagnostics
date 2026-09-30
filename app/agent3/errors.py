"""Agent 3's own exception hierarchy.

Mirrors the sibling repositories' own per-package error convention (e.g.
``app.agent2.parameters.errors``, ``app.pathway_curation.errors``): a narrow, typed hierarchy
raised only for genuine structural/contract problems Agent 3 itself detects -- never used to
represent a *simulation* finding (a failed integration, a NaN, a negative concentration are
all reported as data -- ``DiagnosticFinding``/``SimulationStatus`` -- never raised as Python
exceptions, since they are expected, first-class outcomes this package exists to describe, not
programming errors).
"""

from __future__ import annotations


class Agent3Error(Exception):
    """Base class for every exception this package raises."""


class HandoffContractError(Agent3Error):
    """The supplied Agent 2 -> Agent 3 handoff dict is missing a required field, has a field
    of the wrong type, or otherwise fails to satisfy ``app.agent3.handoff``'s own contract.

    Never raised for a handoff that is merely *unhelpful* (e.g. ``antimony_text`` describing a
    non-executable model, or zero kinetic laws) -- those are legitimate, if limited, inputs
    Agent 3 loads and then reports on. Raised only when the data cannot be parsed into the
    contract's own required shape at all.
    """


class ModelLoadError(Agent3Error):
    """Raised only when constructing a ``SimulationRequest``/running the pipeline is impossible
    before any simulation attempt -- e.g. no handoff was supplied at all. A genuine Antimony/
    SBML compilation failure during loading is **not** raised as this exception; it is reported
    as ``SimulationStatus.MODEL_LOAD_FAILED`` in the result, since a real Agent 2 output that
    fails to compile is exactly the kind of finding Agent 3 exists to surface, not an internal
    programming error.
    """


__all__ = ["Agent3Error", "HandoffContractError", "ModelLoadError"]
