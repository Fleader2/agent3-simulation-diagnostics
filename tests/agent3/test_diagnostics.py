"""Tests for ``app.agent3.diagnostics``.

NaN/Inf detection is tested against a hand-constructed ``SimulationResult`` rather than a real
CVODE run: this session confirmed empirically (see ``tests/agent3/fixtures.py``'s own docstring)
that CVODE robustly *raises* rather than silently propagating NaN/Inf through an otherwise-
"successful" trajectory for every model construction tried -- so this is the correct, standard
way to unit-test this specific detection rule in isolation from the integrator's own behavior.
Every other rule here is tested against a real loaded/simulated model.
"""

from __future__ import annotations

from app.agent3.antimony_ids import build_species_antimony_id_map
from app.agent3.diagnostics import (
    conservation_findings,
    divergent_trajectory_findings,
    heuristic_provenance_finding,
    missing_initial_condition_finding,
    nan_inf_findings,
    negative_concentration_findings,
    parameter_provenance_refs,
    run_all_diagnostics,
)
from app.agent3.handoff import parse_agent2_handoff
from app.agent3.loader import load_antimony_model
from app.agent3.simulation import run_baseline_simulation
from app.agent3.types import SimulationRequest
from tests.agent3.fixtures import (
    DIVERGENT_ANTIMONY,
    NEGATIVE_CONCENTRATION_ANTIMONY,
    minimal_handoff_dict,
)


def _simulate(text, *, end_time=2, num_points=5, species_ids=("S1",), **request_kwargs):
    load_result = load_antimony_model(text)
    assert load_result.succeeded
    request = SimulationRequest(
        request_id="d", start_time=0, end_time=end_time, num_points=num_points, **request_kwargs
    )
    id_map = build_species_antimony_id_map(list(species_ids))
    return run_baseline_simulation(load_result.roadrunner_instance, request, id_map=id_map)


def test_nan_inf_detection_on_synthetic_trajectory():
    from app.agent3.types import SimulationResult, SimulationStatus

    request = SimulationRequest(request_id="nan-test", start_time=0, end_time=1, num_points=3)
    sim = SimulationResult(
        request=request,
        status=SimulationStatus.NUMERICAL_INSTABILITY,
        time_points=(0.0, 0.5, 1.0),
        species_trajectories={"S1": (1.0, float("nan"), 2.0), "S2": (1.0, 1.1, 1.2)},
        initial_state={"S1": 1.0, "S2": 1.0},
        final_state={"S1": 2.0, "S2": 1.2},
    )
    findings = nan_inf_findings(sim)
    assert len(findings) == 1
    assert findings[0].related_species_ids == ("S1",)
    assert "NaN" in findings[0].summary


def test_negative_concentration_detected_with_reaction_provenance():
    handoff = parse_agent2_handoff(
        minimal_handoff_dict(antimony_text=NEGATIVE_CONCENTRATION_ANTIMONY)
    )
    sim = _simulate(NEGATIVE_CONCENTRATION_ANTIMONY)
    findings = negative_concentration_findings(sim, handoff)
    assert len(findings) == 1
    assert findings[0].related_species_ids == ("S1",)
    # Traced back to the real Agent 2 reaction that produces/consumes this species.
    assert "reaction-1" in findings[0].related_reaction_ids


def test_divergent_trajectory_detection():
    sim = _simulate(DIVERGENT_ANTIMONY, end_time=1, num_points=6)
    findings = divergent_trajectory_findings(sim)
    assert len(findings) == 1
    assert findings[0].related_species_ids == ("S1",)


def test_missing_initial_condition_finding_flags_every_unset_species():
    handoff = parse_agent2_handoff(
        minimal_handoff_dict(
            species=[
                {
                    "species_id": "S1",
                    "name": "S1",
                    "compartment_id": "C",
                    "source_compound_id": None,
                    "source_enzyme_state_id": None,
                    "initial_amount": None,
                    "initial_concentration": None,
                    "constant": None,
                    "boundary_condition": None,
                }
            ]
        )
    )
    finding = missing_initial_condition_finding(handoff)
    assert finding is not None
    assert finding.related_species_ids == ("S1",)


def test_missing_initial_condition_finding_is_none_when_all_species_have_one():
    handoff = parse_agent2_handoff(minimal_handoff_dict())  # S1 has initial_concentration="10"
    assert missing_initial_condition_finding(handoff) is None


def test_heuristic_provenance_finding_reports_fraction():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    finding = heuristic_provenance_finding(handoff)
    assert finding is not None
    assert "1 of 1" in finding.summary
    assert finding.related_parameter_ids == ("k1",)


def test_parameter_provenance_refs_traces_to_agent2_measurement_ids():
    """The one central provenance-traceability guarantee: a diagnostic finding referencing a
    parameter must be able to recover exactly the Agent 2 provenance_refs Agent 2 itself
    declared -- never invented, never dropped."""
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    refs = parameter_provenance_refs(handoff, "k1")
    assert refs == ("measurement-abc-123",)


def test_parameter_provenance_refs_empty_for_unknown_parameter():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    assert parameter_provenance_refs(handoff, "does-not-exist") == ()


def test_conservation_findings_on_a_two_species_reaction():
    """S1 -> S2 (simple, irreversible) structurally conserves S1+S2 -- verified against a real
    simulated trajectory."""
    text = """
    model conserve
      compartment C = 1
      species s_S1 in C
      species s_S2 in C
      s_S1 = 10
      s_S2 = 0
      J1: s_S1 -> s_S2;
      J1 = p_k1 * s_S1
      p_k1 = 0.5
    end
    """
    handoff = parse_agent2_handoff(
        minimal_handoff_dict(
            antimony_text=text,
            species=[
                {
                    "species_id": "S1",
                    "name": "S1",
                    "compartment_id": "C",
                    "source_compound_id": None,
                    "source_enzyme_state_id": None,
                    "initial_amount": None,
                    "initial_concentration": "10",
                    "constant": None,
                    "boundary_condition": None,
                },
                {
                    "species_id": "S2",
                    "name": "S2",
                    "compartment_id": "C",
                    "source_compound_id": None,
                    "source_enzyme_state_id": None,
                    "initial_amount": None,
                    "initial_concentration": "0",
                    "constant": None,
                    "boundary_condition": None,
                },
            ],
            reactions=[
                {
                    "reaction_id": "reaction-1",
                    "name": "S1->S2",
                    "reversible": False,
                    "participants": [
                        {"species_id": "S1", "role": "REACTANT", "stoichiometry": "1"},
                        {"species_id": "S2", "role": "PRODUCT", "stoichiometry": "1"},
                    ],
                }
            ],
        )
    )
    sim = _simulate(text, end_time=10, num_points=11, species_ids=("S1", "S2"))
    findings = conservation_findings(handoff, sim)
    assert len(findings) == 1
    assert findings[0].finding_id == "conservation-held"
    assert "1 " in findings[0].summary  # exactly one conservation law (S1 + S2 = const)


def test_run_all_diagnostics_is_deterministic():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    sim = _simulate(minimal_handoff_dict()["antimony_text"], end_time=10, num_points=11)
    first = run_all_diagnostics(handoff, sim)
    second = run_all_diagnostics(handoff, sim)
    assert first == second
