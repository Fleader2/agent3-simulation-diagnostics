"""Agent 3's own output contract: simulation/diagnostic/perturbation/report types.

Every type here is a plain, frozen, JSON-friendly dataclass -- consistent with every other
package in this project's own family (``app.agent1.types``, ``app.agent2.types``). Numeric
simulation data (time series, trajectories, perturbed values) is kept as ``float``, not
``Decimal``: this is a deliberate, narrow divergence from the Agent 1/Agent 2 convention,
justified because this data is produced by, and only ever consumed by, real numerical ODE
integration (``roadrunner``), which itself operates in IEEE double precision throughout --
representing it as ``Decimal`` would imply a false exactness this package never has. Agent 2's
own contract values (parameter values, stoichiometry) remain ``Decimal`` all the way through
``app.agent3.handoff``; they are converted to ``float`` only at the point they are actually
handed to the simulation engine (``app.agent3.loader``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SimulationStatus(StrEnum):
    """The overall outcome of one Agent 3 run against one Agent 2 handoff.

    A small, closed, mutually-exclusive vocabulary -- exactly the six values the Version 1
    instructions name, no more. Distinguishes four qualitatively different situations a
    downstream consumer (Agent 4, or a human reviewer) must never conflate:

    * a **model-structure** failure (``MODEL_LOAD_FAILED``) -- the Antimony/SBML text itself
      could not be compiled; nothing about its kinetics was ever evaluated numerically.
    * a **numerical/solver** failure (``SIMULATION_FAILED``, ``NUMERICAL_INSTABILITY``) -- the
      model compiled and its structure is well-formed, but the ODE integrator itself could not
      produce a usable trajectory (an integration error, or a NaN/Inf/divergent one).
    * **biologically questionable but numerically valid** behavior (``NONPHYSICAL_STATE``) --
      the integrator succeeded and produced finite, bounded numbers, but at least one species
      that should never be negative went negative, or a steady state was reached that is itself
      flagged as inconsistent with a structural conservation law.
    * **steady state was never confirmed** (``STEADY_STATE_NOT_FOUND``) -- the baseline
      time-course itself succeeded (no integration failure, no pathology), but an explicit
      steady-state attempt did not converge within this run's own tolerance/iteration budget.
    * ``SUCCESS`` -- baseline simulation completed, no pathology was detected, and (when
      attempted) steady state was found.

    This status answers "what happened," never "is the model heuristic-heavy" -- that is a
    property of Agent 2's own parameter provenance, reported separately (``Agent3Report
    .heuristic_parameter_ids``/``model_assumptions``), and a model can legitimately be
    ``SUCCESS`` while remaining almost entirely heuristic-initialized; Agent 3 never treats
    "heuristic" as a simulation failure.
    """

    SUCCESS = "SUCCESS"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    NUMERICAL_INSTABILITY = "NUMERICAL_INSTABILITY"
    NONPHYSICAL_STATE = "NONPHYSICAL_STATE"
    STEADY_STATE_NOT_FOUND = "STEADY_STATE_NOT_FOUND"


class DiagnosticSeverity(StrEnum):
    """How seriously a ``DiagnosticFinding`` should be treated by a downstream consumer."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DiagnosticCategory(StrEnum):
    """Which of Agent 3's own four distinguished failure/behavior classes a finding belongs to
    (Version 1 instructions: "Agent 3 should distinguish: model-structure failure; numerical/
    solver failure; biologically questionable but numerically valid behavior; heuristic-heavy
    but executable behavior"), plus two structural check categories this same distinction
    naturally produces findings under.
    """

    MODEL_STRUCTURE = "MODEL_STRUCTURE"
    NUMERICAL_SOLVER = "NUMERICAL_SOLVER"
    BIOLOGICALLY_QUESTIONABLE = "BIOLOGICALLY_QUESTIONABLE"
    HEURISTIC_PROVENANCE = "HEURISTIC_PROVENANCE"
    CONSERVATION = "CONSERVATION"
    PERTURBATION_SENSITIVITY = "PERTURBATION_SENSITIVITY"


@dataclass(frozen=True, slots=True)
class DiagnosticFinding:
    """One structured, traceable observation about the model or its simulated behavior.

    ``related_*_ids`` and ``provenance_refs`` are the mechanism by which a finding is traced
    back to the Agent 2 entity responsible (Version 1's own explicit requirement:
    "identification of reactions/species/parameters associated with failures" and
    "preservation of Agent 2 provenance/assumption references in diagnostic output") --
    ``provenance_refs`` specifically carries forward whatever Agent 2 itself already recorded
    on the relevant ``HandoffParameter.provenance_refs``/``HandoffModelAssumption
    .assumption_id``, never a new identifier Agent 3 invents.
    """

    finding_id: str
    category: DiagnosticCategory
    severity: DiagnosticSeverity
    summary: str
    explanation: str
    related_species_ids: tuple[str, ...] = ()
    related_reaction_ids: tuple[str, ...] = ()
    related_parameter_ids: tuple[str, ...] = ()
    related_assumption_ids: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    time_point: float | None = None


@dataclass(frozen=True, slots=True)
class SimulationRequest:
    """Deterministic configuration for one baseline time-course simulation.

    Every field is explicit -- there is no hidden global integrator state and no random seed
    consulted anywhere in this package's own simulation path (``roadrunner``'s default CVODE
    integrator is itself a deterministic ODE solver: identical inputs always produce identical
    outputs on the same platform/library version, which is recorded in the result for exactly
    this reason).
    """

    request_id: str
    start_time: float
    end_time: float
    num_points: int
    integrator: str = "cvode"
    absolute_tolerance: float = 1e-10
    relative_tolerance: float = 1e-8


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """The outcome of one ``SimulationRequest`` against one loaded model."""

    request: SimulationRequest
    status: SimulationStatus
    time_points: tuple[float, ...] = ()
    species_trajectories: dict[str, tuple[float, ...]] | None = None
    initial_state: dict[str, float] | None = None
    final_state: dict[str, float] | None = None
    solver_message: str | None = None
    engine_name: str = "libRoadRunner"
    engine_version: str | None = None


@dataclass(frozen=True, slots=True)
class SteadyStateResult:
    """The outcome of one steady-state attempt against one loaded model.

    ``attempted`` is always ``True`` for a model that reached baseline simulation ``SUCCESS``
    and ``False`` only when steady state was never even attempted (e.g. because baseline
    simulation itself already failed) -- never conflated with ``converged=False`` (attempted,
    but did not reach steady state), which is its own distinct, reportable outcome.
    """

    attempted: bool
    converged: bool
    method: str | None = None
    max_abs_rate_of_change: float | None = None
    steady_state_values: dict[str, float] | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PerturbationSpec:
    """One Version-1 perturbation smoke test to run: a +/-10%-style nudge to exactly one
    already-declared parameter value or species initial concentration, never a combination of
    several at once (keeps each perturbation's own effect attributable to one changed quantity).
    """

    target_kind: str  # "PARAMETER" | "INITIAL_CONCENTRATION"
    target_id: str
    fraction: float


@dataclass(frozen=True, slots=True)
class PerturbationResult:
    """The outcome of one ``PerturbationSpec`` smoke test.

    ``relative_change_by_species`` (Functional Modularity Criteria increment) discloses the
    identical per-species relative-change values ``max_relative_change_in_final_state`` was
    always already computed from, before collapsing them to that one scalar -- never a new
    computation, only exposing data this package already derived internally. Agent 2's own
    dynamic-isolation/sensitivity-coherence criteria need the *per-species* breakdown (which
    species moved, not just how much the single worst one moved) to distinguish effects that
    stay within one candidate module from effects that spill into another. ``None`` only when
    no final-state comparison was possible at all (identical condition to
    ``max_relative_change_in_final_state is None``).
    """

    spec: PerturbationSpec
    baseline_value: float
    perturbed_value: float
    simulation_status: SimulationStatus
    remained_numerically_stable: bool
    max_relative_change_in_final_state: float | None = None
    relative_change_by_species: dict[str, float] | None = None
    findings: tuple[DiagnosticFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class Agent3Report:
    """The single, top-level structured output Agent 3 hands to Agent 4 (or a human reviewer).

    ``overall_status`` is the single most severe/informative status across load, baseline
    simulation, and steady-state attempt (never a separate, re-derived judgment) --
    ``app.agent3.report.determine_overall_status`` computes it deterministically from the
    other fields, so this is never set independently of them.
    """

    report_id: str
    agent3_contract_version: str
    agent2_model_id: str
    agent2_contract_version: str
    handoff_version_note: str | None
    overall_status: SimulationStatus
    load_succeeded: bool
    load_message: str | None
    simulation: SimulationResult | None
    steady_state: SteadyStateResult | None
    diagnostics: tuple[DiagnosticFinding, ...]
    perturbations: tuple[PerturbationResult, ...]
    heuristic_parameter_ids: tuple[str, ...]
    placeholder_parameter_ids: tuple[str, ...]
    agent2_unresolved_reaction_ids: tuple[str, ...]
    agent2_unresolved_kinetic_law_ids: tuple[str, ...]
    sufficient_for_agent4: bool
    sufficiency_note: str


__all__ = [
    "Agent3Report",
    "DiagnosticCategory",
    "DiagnosticFinding",
    "DiagnosticSeverity",
    "PerturbationResult",
    "PerturbationSpec",
    "SimulationRequest",
    "SimulationResult",
    "SimulationStatus",
    "SteadyStateResult",
]
