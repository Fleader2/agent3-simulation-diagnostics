"""Tests for ``app.agent3.simulation``: baseline simulation and steady-state attempts."""

from __future__ import annotations

from app.agent3.loader import load_antimony_model
from app.agent3.simulation import attempt_steady_state, run_baseline_simulation
from app.agent3.types import SimulationRequest, SimulationStatus
from tests.agent3.fixtures import (
    DIVERGENT_ANTIMONY,
    NEGATIVE_CONCENTRATION_ANTIMONY,
    SOLVER_FAILURE_ANTIMONY,
    VALID_DECAY_ANTIMONY,
)


def _load(text):
    result = load_antimony_model(text)
    assert result.succeeded, result.message
    return result.roadrunner_instance


def test_successful_baseline_simulation():
    rr = _load(VALID_DECAY_ANTIMONY)
    request = SimulationRequest(request_id="t1", start_time=0, end_time=10, num_points=11)
    result = run_baseline_simulation(rr, request)
    assert result.status is SimulationStatus.SUCCESS
    assert result.time_points[0] == 0
    assert result.time_points[-1] == 10
    assert result.initial_state["s_S1"] == 10
    assert result.final_state["s_S1"] < result.initial_state["s_S1"]
    assert result.solver_message is None


def test_solver_failure_is_reported_not_raised():
    rr = _load(SOLVER_FAILURE_ANTIMONY)
    request = SimulationRequest(request_id="t2", start_time=0, end_time=1, num_points=5)
    result = run_baseline_simulation(rr, request)
    assert result.status is SimulationStatus.SIMULATION_FAILED
    assert result.solver_message is not None
    assert "Integration failed" in result.solver_message


def test_divergent_trajectory_detected_as_numerical_instability():
    rr = _load(DIVERGENT_ANTIMONY)
    request = SimulationRequest(request_id="t3", start_time=0, end_time=1, num_points=6)
    result = run_baseline_simulation(rr, request)
    assert result.status is SimulationStatus.NUMERICAL_INSTABILITY
    assert result.species_trajectories is not None
    assert max(result.species_trajectories["s_S1"]) > 1e12


def test_negative_concentration_still_reports_success_status():
    """A negative concentration is numerically valid (no integration error) -- the
    SimulationStatus itself stays SUCCESS; detecting that the value is biologically
    nonphysical is app.agent3.diagnostics' own job, not simulation.py's."""
    rr = _load(NEGATIVE_CONCENTRATION_ANTIMONY)
    request = SimulationRequest(request_id="t4", start_time=0, end_time=2, num_points=5)
    result = run_baseline_simulation(rr, request)
    assert result.status is SimulationStatus.SUCCESS
    assert result.final_state["s_S1"] < 0


def test_steady_state_success_on_a_simple_decay_model():
    rr = _load(VALID_DECAY_ANTIMONY)
    result = attempt_steady_state(rr)
    assert result.attempted
    assert result.converged
    assert result.steady_state_values is not None


def test_steady_state_failure_is_reported_not_raised():
    """The real sce00061 model (all species at 0, singular Jacobian at the origin) is this
    package's own real, confirmed steady-state-failure case -- loaded from the same fixture
    the bounded integration run uses."""
    import json
    from pathlib import Path

    fixture_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / "sce00061_agent2_handoff.json"
    )
    with open(fixture_path) as f:
        data = json.load(f)
    rr = _load(data["antimony_text"])
    result = attempt_steady_state(rr)
    assert result.attempted
    assert not result.converged
    assert result.message is not None
