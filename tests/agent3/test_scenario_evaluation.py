"""Tests for ``app.agent3.scenario_evaluation``: the whole-model experimental-scenario
evaluation primitive (prediction, never fitting)."""

from __future__ import annotations

import math

import pytest

from app.agent3.scenario_evaluation import (
    ScenarioEvaluationRequest,
    ScenarioEvaluationStatus,
    StepIntervention,
    evaluate_scenario,
)
from tests.agent3.fixtures import (
    DIVERGENT_ANTIMONY,
    INVALID_ANTIMONY,
    SOLVER_FAILURE_ANTIMONY,
    VALID_DECAY_ANTIMONY,
)


def _decay(s0: float, k: float, t: float) -> float:
    """The exact analytic solution of ``ds/dt = -k*s`` -- what ``VALID_DECAY_ANTIMONY``'s own
    reaction is, so every prediction below is checked against a closed-form value, never just
    "the solver returned something."""
    return s0 * math.exp(-k * t)


def test_a_simple_time_course_matches_the_analytic_solution():
    request = ScenarioEvaluationRequest(
        request_id="t1",
        requested_times=(0.0, 1.0, 2.0, 5.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    assert result.predictions is not None
    for t, predicted in zip(request.requested_times, result.predictions["s_S1"], strict=True):
        assert predicted == pytest.approx(_decay(10.0, 0.5, t))


def test_a_candidate_parameter_override_changes_the_decay_rate():
    request = ScenarioEvaluationRequest(
        request_id="t2",
        parameter_overrides={"p_k1": 2.0},
        requested_times=(0.0, 1.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    assert result.predictions["s_S1"][1] == pytest.approx(_decay(10.0, 2.0, 1.0))


def test_an_initial_value_override_changes_the_starting_state():
    request = ScenarioEvaluationRequest(
        request_id="t3",
        initial_value_overrides={"s_S1": 50.0},
        requested_times=(0.0, 1.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    assert result.predictions["s_S1"][0] == pytest.approx(50.0)
    assert result.predictions["s_S1"][1] == pytest.approx(_decay(50.0, 0.5, 1.0))


def test_a_step_intervention_restarts_decay_from_its_own_new_value():
    """A step dose of s_S1=100 at t=5 -- the trajectory from t=5 onward must follow the decay
    law from the *new* value, never the value it would have had without the intervention."""
    request = ScenarioEvaluationRequest(
        request_id="t4",
        interventions=(
            StepIntervention(target_kind="SPECIES", target_id="s_S1", time=5.0, value=100.0),
        ),
        requested_times=(0.0, 5.0, 6.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    predictions = result.predictions["s_S1"]
    # At t=5, the reported value is the state *before* the intervention (module docstring's own
    # documented convention) -- the natural decay from s0=10.
    assert predictions[1] == pytest.approx(_decay(10.0, 0.5, 5.0))
    # At t=6, one second of decay from the *post-intervention* value of 100.
    assert predictions[2] == pytest.approx(_decay(100.0, 0.5, 1.0))


def test_a_parameter_targeted_intervention_changes_the_rate_mid_trajectory():
    request = ScenarioEvaluationRequest(
        request_id="t5",
        interventions=(
            StepIntervention(target_kind="PARAMETER", target_id="p_k1", time=2.0, value=0.0),
        ),
        requested_times=(0.0, 2.0, 10.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    predictions = result.predictions["s_S1"]
    value_at_2 = _decay(10.0, 0.5, 2.0)
    assert predictions[1] == pytest.approx(value_at_2)
    # k1 is set to 0 at t=2 -- the species must stay exactly constant afterward.
    assert predictions[2] == pytest.approx(value_at_2)


def test_irregular_and_repeated_requested_times_are_aligned_exactly():
    request = ScenarioEvaluationRequest(
        request_id="t6",
        requested_times=(3.0, 0.0, 3.0, 7.5, 1.0),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    predictions = result.predictions["s_S1"]
    assert len(predictions) == len(request.requested_times)
    for t, predicted in zip(request.requested_times, predictions, strict=True):
        assert predicted == pytest.approx(_decay(10.0, 0.5, t))
    # The two requests for t=3.0 (indices 0 and 2) must agree exactly with each other.
    assert predictions[0] == predictions[2]


def test_repeated_calls_never_leak_state_a_then_b_then_a():
    """A -> B -> A: three separate evaluations with different candidate parameter values must
    each produce the value that parameter alone implies -- never inheriting anything from the
    call before it."""
    request_a = ScenarioEvaluationRequest(
        request_id="a",
        parameter_overrides={"p_k1": 0.5},
        requested_times=(1.0,),
        requested_output_ids=("s_S1",),
    )
    request_b = ScenarioEvaluationRequest(
        request_id="b",
        parameter_overrides={"p_k1": 5.0},
        requested_times=(1.0,),
        requested_output_ids=("s_S1",),
    )

    result_a1 = evaluate_scenario(VALID_DECAY_ANTIMONY, request_a)
    result_b = evaluate_scenario(VALID_DECAY_ANTIMONY, request_b)
    result_a2 = evaluate_scenario(VALID_DECAY_ANTIMONY, request_a)

    expected_a = _decay(10.0, 0.5, 1.0)
    expected_b = _decay(10.0, 5.0, 1.0)
    assert result_a1.predictions["s_S1"][0] == pytest.approx(expected_a)
    assert result_b.predictions["s_S1"][0] == pytest.approx(expected_b)
    assert result_a2.predictions["s_S1"][0] == pytest.approx(expected_a)
    assert result_a1.predictions["s_S1"][0] == result_a2.predictions["s_S1"][0]


def test_an_unresolved_parameter_override_is_an_invalid_request_not_a_crash():
    request = ScenarioEvaluationRequest(
        request_id="t7",
        parameter_overrides={"p_not_real": 1.0},
        requested_times=(0.0,),
        requested_output_ids=("s_S1",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.INVALID_REQUEST
    assert any("p_not_real" in e for e in result.validation_errors)
    assert result.predictions is None


def test_every_unresolved_identifier_is_reported_together_not_just_the_first():
    request = ScenarioEvaluationRequest(
        request_id="t8",
        parameter_overrides={"p_not_real": 1.0},
        initial_value_overrides={"s_not_real": 1.0},
        requested_times=(0.0,),
        requested_output_ids=("s_also_not_real",),
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.INVALID_REQUEST
    assert len(result.validation_errors) == 3
    joined = " ".join(result.validation_errors)
    assert "p_not_real" in joined
    assert "s_not_real" in joined
    assert "s_also_not_real" in joined


def test_a_negative_requested_time_is_rejected():
    request = ScenarioEvaluationRequest(
        request_id="t9", requested_times=(-1.0, 0.0), requested_output_ids=("s_S1",)
    )
    result = evaluate_scenario(VALID_DECAY_ANTIMONY, request)
    assert result.status is ScenarioEvaluationStatus.INVALID_REQUEST
    assert any("negative" in e for e in result.validation_errors)


def test_empty_requested_times_and_outputs_are_each_rejected():
    result = evaluate_scenario(
        VALID_DECAY_ANTIMONY,
        ScenarioEvaluationRequest(request_id="t10", requested_times=(), requested_output_ids=()),
    )
    assert result.status is ScenarioEvaluationStatus.INVALID_REQUEST
    assert len(result.validation_errors) == 2


def test_malformed_antimony_text_reports_model_load_failed_not_an_exception():
    result = evaluate_scenario(
        INVALID_ANTIMONY,
        ScenarioEvaluationRequest(
            request_id="t11", requested_times=(0.0,), requested_output_ids=("s_S1",)
        ),
    )
    assert result.status is ScenarioEvaluationStatus.MODEL_LOAD_FAILED
    assert result.solver_message is not None


def test_solver_failure_is_reported_not_raised():
    result = evaluate_scenario(
        SOLVER_FAILURE_ANTIMONY,
        ScenarioEvaluationRequest(
            request_id="t12", requested_times=(0.0, 1.0), requested_output_ids=("s_S1",)
        ),
    )
    assert result.status is ScenarioEvaluationStatus.SIMULATION_FAILED


def test_a_divergent_trajectory_is_reported_as_numerical_instability():
    result = evaluate_scenario(
        DIVERGENT_ANTIMONY,
        ScenarioEvaluationRequest(
            request_id="t13", requested_times=(0.0, 1.0), requested_output_ids=("s_S1",)
        ),
    )
    assert result.status is ScenarioEvaluationStatus.NUMERICAL_INSTABILITY


def test_multiple_outputs_are_each_reported_aligned_to_the_same_times():
    """Two species from a slightly richer model, both requested as outputs."""
    text = """
    model two_species
      compartment C = 1
      species s_A in C
      species s_B in C
      s_A = 10
      s_B = 0
      J1: s_A -> s_B;
      J1 = p_k1 * s_A
      p_k1 = 1.0
    end
    """
    request = ScenarioEvaluationRequest(
        request_id="t14",
        requested_times=(0.0, 1.0, 2.0),
        requested_output_ids=("s_A", "s_B"),
    )
    result = evaluate_scenario(text, request)
    assert result.status is ScenarioEvaluationStatus.SUCCESS
    assert set(result.predictions) == {"s_A", "s_B"}
    assert len(result.predictions["s_A"]) == 3
    assert len(result.predictions["s_B"]) == 3
    # Mass conservation: s_A + s_B stays at 10 throughout.
    for i in range(3):
        assert result.predictions["s_A"][i] + result.predictions["s_B"][i] == pytest.approx(10.0)
