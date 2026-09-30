"""Assembling the single, top-level ``Agent3Report`` from every stage's own output.

``determine_overall_status`` is the one place the whole run's own single, most-informative
status is decided -- deliberately centralized so no two call sites can ever disagree about
what "the run's status" means.
"""

from __future__ import annotations

from app.agent3.diagnostics import heuristic_and_placeholder_parameters
from app.agent3.handoff import Agent2Handoff, handoff_contract_version_mismatch
from app.agent3.types import (
    Agent3Report,
    DiagnosticFinding,
    DiagnosticSeverity,
    PerturbationResult,
    SimulationResult,
    SimulationStatus,
    SteadyStateResult,
)
from app.agent3.version import AGENT3_CONTRACT_VERSION


def determine_overall_status(
    load_succeeded: bool,
    simulation: SimulationResult | None,
    steady_state: SteadyStateResult | None,
) -> SimulationStatus:
    """The single, most-informative ``SimulationStatus`` for the whole run.

    Precedence (most to least severe, matching the Version 1 vocabulary's own ordering):
    a load failure always wins; then a baseline simulation failure/instability; then, only if
    baseline simulation itself succeeded cleanly, a failed steady-state attempt; otherwise
    ``SUCCESS``.
    """
    if not load_succeeded:
        return SimulationStatus.MODEL_LOAD_FAILED
    if simulation is None:
        return SimulationStatus.MODEL_LOAD_FAILED
    if simulation.status is not SimulationStatus.SUCCESS:
        return simulation.status
    if steady_state is not None and steady_state.attempted and not steady_state.converged:
        return SimulationStatus.STEADY_STATE_NOT_FOUND
    return SimulationStatus.SUCCESS


def determine_agent4_sufficiency(
    overall_status: SimulationStatus, diagnostics: tuple[DiagnosticFinding, ...]
) -> tuple[bool, str]:
    """Whether this report carries enough structured information for Agent 4 to act on, and a
    one-sentence explanation -- **never** a judgment about whether the model is scientifically
    good; a model that is entirely heuristic and biologically trivial (e.g. this session's own
    real all-zero-initial-condition sce00061 run) is still fully sufficient for Agent 4 to
    consume, exactly because every reason it is trivial is disclosed with full provenance."""
    if overall_status is SimulationStatus.MODEL_LOAD_FAILED:
        return (
            False,
            "The model never compiled; there is no simulation/diagnostic content for Agent 4 "
            "to calibrate against beyond the load failure message itself.",
        )
    critical = [f for f in diagnostics if f.severity is DiagnosticSeverity.CRITICAL]
    if critical and overall_status in (
        SimulationStatus.SIMULATION_FAILED,
        SimulationStatus.NUMERICAL_INSTABILITY,
    ):
        return (
            True,
            "The model loaded and produced traceable diagnostic findings even though baseline "
            "simulation itself failed -- sufficient for Agent 4 to know which reactions/"
            "parameters to inspect before attempting calibration, though calibration cannot "
            "proceed until the underlying numerical failure is addressed.",
        )
    return (
        True,
        "The model loaded, a baseline simulation was produced (or its failure fully traced), "
        "every declared parameter's provenance is carried through, and perturbation smoke "
        "tests were run -- sufficient structured input for Agent 4's own, separate calibration "
        "process.",
    )


def build_agent3_report(
    *,
    report_id: str,
    handoff: Agent2Handoff,
    load_succeeded: bool,
    load_message: str | None,
    simulation: SimulationResult | None,
    steady_state: SteadyStateResult | None,
    diagnostics: tuple[DiagnosticFinding, ...],
    perturbations: tuple[PerturbationResult, ...],
) -> Agent3Report:
    overall_status = determine_overall_status(load_succeeded, simulation, steady_state)
    heuristic_ids, placeholder_ids = heuristic_and_placeholder_parameters(handoff)
    sufficient, sufficiency_note = determine_agent4_sufficiency(overall_status, diagnostics)
    return Agent3Report(
        report_id=report_id,
        agent3_contract_version=AGENT3_CONTRACT_VERSION,
        agent2_model_id=handoff.model_id,
        agent2_contract_version=handoff.contract_version,
        handoff_version_note=handoff_contract_version_mismatch(handoff),
        overall_status=overall_status,
        load_succeeded=load_succeeded,
        load_message=load_message,
        simulation=simulation,
        steady_state=steady_state,
        diagnostics=diagnostics,
        perturbations=perturbations,
        heuristic_parameter_ids=heuristic_ids,
        placeholder_parameter_ids=placeholder_ids,
        agent2_unresolved_reaction_ids=handoff.unresolved_reaction_ids,
        agent2_unresolved_kinetic_law_ids=handoff.unresolved_kinetic_law_ids,
        sufficient_for_agent4=sufficient,
        sufficiency_note=sufficiency_note,
    )


__all__ = ["build_agent3_report", "determine_agent4_sufficiency", "determine_overall_status"]
