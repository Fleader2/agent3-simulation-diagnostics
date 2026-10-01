"""Real, bounded integration tests against the current, actual ``sce00061`` Agent 2 handoff.

This is the one test module allowed to be genuinely slow/real (it runs the full baseline
workflow, including 10 perturbation smoke tests, against the real 53-species/38-reaction/
115-parameter model, produced by Agent 2's own canonical ``run_agent2_pipeline`` entrypoint --
Five-Agent Workflow V1 Hardening increment) -- everything else in this suite uses small,
synthetic fixtures.
"""

from __future__ import annotations

import copy

from app.agent3.handoff import parse_agent2_handoff
from app.agent3.pipeline import run_agent3_pipeline
from app.agent3.types import DiagnosticCategory, SimulationStatus
from tests.agent3.fixtures import load_real_sce00061_handoff


def test_real_sce00061_handoff_parses():
    data = load_real_sce00061_handoff()
    handoff = parse_agent2_handoff(data)
    assert len(handoff.species) == 53
    assert len(handoff.reactions) == 38
    assert len(handoff.parameters) == 115
    assert handoff.readiness == "EXECUTABLE"


def test_full_pipeline_runs_against_the_real_model():
    handoff = parse_agent2_handoff(load_real_sce00061_handoff())
    report = run_agent3_pipeline(handoff)

    assert report.load_succeeded
    assert report.simulation is not None
    assert report.simulation.status is SimulationStatus.SUCCESS
    # Real, confirmed finding for the current model: steady state is attempted but does not
    # converge (singular Jacobian at the all-zero origin) -- see the completion report.
    assert report.overall_status is SimulationStatus.STEADY_STATE_NOT_FOUND
    assert report.steady_state is not None
    assert report.steady_state.attempted
    assert not report.steady_state.converged

    categories = {f.category for f in report.diagnostics}
    assert DiagnosticCategory.MODEL_STRUCTURE in categories
    assert DiagnosticCategory.BIOLOGICALLY_QUESTIONABLE in categories
    assert DiagnosticCategory.HEURISTIC_PROVENANCE in categories

    assert len(report.perturbations) == 10
    assert all(p.remained_numerically_stable for p in report.perturbations)

    assert report.sufficient_for_agent4


def test_pipeline_never_mutates_the_input_handoff_dict():
    data = load_real_sce00061_handoff()
    original = copy.deepcopy(data)
    handoff = parse_agent2_handoff(data)
    run_agent3_pipeline(handoff, run_perturbations=False)
    assert data == original
    assert handoff.antimony_text == original["antimony_text"]


def test_heuristic_and_placeholder_counts_match_the_real_agent2_declaration():
    handoff = parse_agent2_handoff(load_real_sce00061_handoff())
    report = run_agent3_pipeline(handoff, run_perturbations=False)
    assert len(report.heuristic_parameter_ids) == 107
    assert len(report.placeholder_parameter_ids) == 0
