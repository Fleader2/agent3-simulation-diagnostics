"""Tests for ``app.agent3.perturbation``: deterministic Version 1 smoke tests."""

from __future__ import annotations

from app.agent3.handoff import parse_agent2_handoff
from app.agent3.perturbation import (
    run_perturbation,
    run_perturbation_smoke_tests,
    select_default_perturbation_targets,
)
from app.agent3.pipeline import DEFAULT_SIMULATION_REQUEST
from app.agent3.types import PerturbationSpec, SimulationStatus
from tests.agent3.fixtures import minimal_handoff_dict


def test_default_target_selection_is_deterministic():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    first = select_default_perturbation_targets(handoff)
    second = select_default_perturbation_targets(handoff)
    assert first == second


def test_default_target_selection_includes_the_one_real_parameter_and_species():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    specs = select_default_perturbation_targets(handoff)
    kinds = {s.target_kind for s in specs}
    assert "PARAMETER" in kinds
    assert "INITIAL_CONCENTRATION" in kinds
    assert any(s.target_id == "k1" for s in specs)
    assert any(s.target_id == "S1" for s in specs)


def test_parameter_perturbation_changes_the_decay_rate_and_final_state():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    spec = PerturbationSpec(target_kind="PARAMETER", target_id="k1", fraction=0.10)
    result = run_perturbation(handoff, spec, DEFAULT_SIMULATION_REQUEST)
    assert result.simulation_status is SimulationStatus.SUCCESS
    assert result.remained_numerically_stable
    assert result.baseline_value == 0.5
    assert abs(result.perturbed_value - 0.55) < 1e-9
    # A faster decay rate (+10%) must produce a materially different final state on this
    # simple, genuinely-nonzero-initial-condition model.
    assert result.max_relative_change_in_final_state is not None
    assert result.max_relative_change_in_final_state > 0


def test_relative_change_by_species_is_consistent_with_the_max_scalar():
    """Functional Modularity Criteria increment: ``relative_change_by_species`` discloses the
    exact per-species values ``max_relative_change_in_final_state`` was already derived from --
    never a second, independently-computed number."""
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    spec = PerturbationSpec(target_kind="PARAMETER", target_id="k1", fraction=0.10)
    result = run_perturbation(handoff, spec, DEFAULT_SIMULATION_REQUEST)
    assert result.relative_change_by_species is not None
    assert "S1" in result.relative_change_by_species
    assert (
        max(result.relative_change_by_species.values())
        == result.max_relative_change_in_final_state
    )


def test_perturbation_is_deterministic_across_repeated_runs():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    spec = PerturbationSpec(target_kind="PARAMETER", target_id="k1", fraction=0.10)
    first = run_perturbation(handoff, spec, DEFAULT_SIMULATION_REQUEST)
    second = run_perturbation(handoff, spec, DEFAULT_SIMULATION_REQUEST)
    assert first.perturbed_value == second.perturbed_value
    assert first.max_relative_change_in_final_state == second.max_relative_change_in_final_state
    assert first.simulation_status == second.simulation_status


def test_unresolvable_target_is_reported_never_guessed():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    spec = PerturbationSpec(target_kind="PARAMETER", target_id="does-not-exist", fraction=0.10)
    result = run_perturbation(handoff, spec, DEFAULT_SIMULATION_REQUEST)
    assert not result.remained_numerically_stable
    assert len(result.findings) == 1
    assert "Could not resolve" in result.findings[0].summary


def test_run_perturbation_smoke_tests_preserves_spec_order():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    specs = (
        PerturbationSpec(target_kind="PARAMETER", target_id="k1", fraction=0.10),
        PerturbationSpec(target_kind="INITIAL_CONCENTRATION", target_id="S1", fraction=-0.10),
    )
    results = run_perturbation_smoke_tests(handoff, DEFAULT_SIMULATION_REQUEST, specs)
    assert len(results) == 2
    assert results[0].spec == specs[0]
    assert results[1].spec == specs[1]
