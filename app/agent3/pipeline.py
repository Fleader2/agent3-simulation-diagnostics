"""The Version 1 baseline workflow, end to end.

``Agent 2 Antimony/ModelSpecification -> load/compile -> baseline simulation -> steady-state
check -> diagnostics -> small perturbation/sensitivity smoke tests -> structured Agent 3
report``

This is the one function a caller (a script, a test, a future Agent 3 service entrypoint)
needs to run the whole Version 1 pipeline against one ``Agent2Handoff``. Every stage's own
module (``loader``, ``simulation``, ``diagnostics``, ``perturbation``, ``report``) remains
independently callable and independently testable; this module only sequences them.
"""

from __future__ import annotations

import uuid

from app.agent3.antimony_ids import build_species_antimony_id_map
from app.agent3.diagnostics import run_all_diagnostics
from app.agent3.handoff import Agent2Handoff
from app.agent3.loader import load_antimony_model
from app.agent3.perturbation import (
    run_perturbation_smoke_tests,
    select_default_perturbation_targets,
)
from app.agent3.report import build_agent3_report
from app.agent3.simulation import attempt_steady_state, run_baseline_simulation
from app.agent3.types import Agent3Report, PerturbationSpec, SimulationRequest

#: Version 1's own default baseline-simulation horizon/step configuration. Deliberately modest
#: (a generic, unit-agnostic 0-1000 "time unit" horizon at 200 points) since no per-reaction
#: characteristic timescale is available in the handoff contract to choose a better one from --
#: bump ``SIMULATION_POLICY_VERSION`` if this default, or the policy for choosing it, changes.
DEFAULT_SIMULATION_REQUEST = SimulationRequest(
    request_id="agent3-baseline-default",
    start_time=0.0,
    end_time=1000.0,
    num_points=200,
)


def run_agent3_pipeline(
    handoff: Agent2Handoff,
    *,
    request: SimulationRequest | None = None,
    perturbation_specs: tuple[PerturbationSpec, ...] | None = None,
    run_perturbations: bool = True,
) -> Agent3Report:
    """Run the full Version 1 workflow against ``handoff`` and return one ``Agent3Report``.

    Never raises for a real simulation/diagnostic failure -- every such outcome is captured in
    the returned report. May raise ``app.agent3.errors.HandoffContractError`` only if ``handoff``
    was not actually a valid, already-parsed ``Agent2Handoff`` (a caller error, not a modeling
    one) -- ``handoff`` here is always the already-parsed dataclass, never a raw dict (parse it
    first via ``app.agent3.handoff.parse_agent2_handoff``).
    """
    request = request or DEFAULT_SIMULATION_REQUEST
    report_id = f"agent3-report-{uuid.uuid4()}"

    load_result = load_antimony_model(handoff.antimony_text)
    if not load_result.succeeded or load_result.roadrunner_instance is None:
        diagnostics = run_all_diagnostics(handoff, sim=None)
        return build_agent3_report(
            report_id=report_id,
            handoff=handoff,
            load_succeeded=False,
            load_message=load_result.message,
            simulation=None,
            steady_state=None,
            diagnostics=diagnostics,
            perturbations=(),
        )

    id_map = build_species_antimony_id_map([s.species_id for s in handoff.species])
    simulation = run_baseline_simulation(load_result.roadrunner_instance, request, id_map=id_map)
    steady_state = attempt_steady_state(load_result.roadrunner_instance, id_map=id_map)
    diagnostics = run_all_diagnostics(handoff, simulation, steady_state)

    perturbations = ()
    if run_perturbations:
        specs = perturbation_specs or select_default_perturbation_targets(handoff)
        perturbations = run_perturbation_smoke_tests(handoff, request, specs)

    return build_agent3_report(
        report_id=report_id,
        handoff=handoff,
        load_succeeded=True,
        load_message=None,
        simulation=simulation,
        steady_state=steady_state,
        diagnostics=diagnostics,
        perturbations=perturbations,
    )


__all__ = ["DEFAULT_SIMULATION_REQUEST", "run_agent3_pipeline"]
