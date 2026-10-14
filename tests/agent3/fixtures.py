"""Shared, hand-crafted fixtures for Agent 3's own test suite.

Every Antimony snippet here was verified, in this session, against the real installed
``antimony``/``libroadrunner`` versions to actually produce the behavior its name claims
(confirmed empirically before being written into this file -- never assumed from documentation
alone; CVODE is a robust integrator that raises on many more classes of numerical failure than
it silently tolerates, so each fixture below was chosen specifically because it was observed to
produce its own named outcome).
"""

from __future__ import annotations

import json
from pathlib import Path

#: Identifiers here deliberately mirror Agent 2's own real Antimony naming convention
#: (``p_<parameter_id>``/``s_<species_id>``, ``app.agent2.antimony.naming`` on the sibling
#: ``agent2-antimony-builder`` repository) rather than the bare ``S1``/``k1`` a human would
#: write by hand -- so ``minimal_handoff_dict``'s own ``antimony_symbol_map`` below resolves
#: these fixtures' targets exactly as the real sce00061 integration does, never bypassing it.
VALID_DECAY_ANTIMONY = """
model valid_decay
  compartment C = 1
  species s_S1 in C
  s_S1 = 10
  J1: s_S1 -> ;
  J1 = p_k1 * s_S1
  p_k1 = 0.5
end
"""

INVALID_ANTIMONY = "this is not $$$ valid antimony ### @@@ syntax at all"

#: Negative production rate -- s_S1 starts at 1 and is driven to a real, sustained negative
#: concentration by a constant-rate reaction with no lower bound. Confirmed empirically:
#: SUCCESS status (CVODE integrates this cleanly), final s_S1 ~= -9.
NEGATIVE_CONCENTRATION_ANTIMONY = """
model negative_concentration
  compartment C = 1
  species s_S1 in C
  s_S1 = 1
  J1: -> s_S1;
  J1 = -5
end
"""

#: Autocatalytic growth (s_S1 -> 2 s_S1 at rate p_k1*s_S1, p_k1=50) -- confirmed empirically to
#: exceed app.agent3.simulation.DIVERGENCE_MAGNITUDE_THRESHOLD (1e12) well within a short time
#: horizon while still integrating to SUCCESS (finite at every reported point, just very large).
DIVERGENT_ANTIMONY = """
model divergent
  compartment C = 1
  species s_S1 in C
  s_S1 = 1
  J1: s_S1 -> 2 s_S1;
  J1 = p_k1 * s_S1
  p_k1 = 50
end
"""

#: A production rate that is already non-finite (1e300 squared) from t=0 -- confirmed
#: empirically to make CVODE raise CV_CONV_FAILURE immediately, i.e. SimulationStatus
#: .SIMULATION_FAILED (the "solver failure" case), never NUMERICAL_INSTABILITY (which requires
#: the integrator to have actually produced reportable values first).
SOLVER_FAILURE_ANTIMONY = """
model solver_failure
  compartment C = 1
  species s_S1 in C
  s_S1 = 1
  p_k1 = 1e300
  J1: -> s_S1;
  J1 = p_k1 * p_k1
end
"""


def load_real_sce00061_handoff() -> dict:
    """The real, saved Agent 2 handoff for the current ``sce00061`` model -- built once, in
    this session, from the real committed Agent 2 pipeline's own output (see the completion
    report for exactly how). Used for this package's own bounded real-integration tests."""
    fixture_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / "sce00061_agent2_handoff.json"
    )
    with open(fixture_path) as f:
        return json.load(f)


def minimal_handoff_dict(**overrides) -> dict:
    """The smallest valid Agent 2 -> Agent 3 handoff dict, for synthetic unit tests that don't
    need the full real ``sce00061`` fixture. One reaction, one species, one parameter, one
    model assumption -- enough to exercise provenance tracing end to end."""
    base = {
        "contract_version": "agent2-downstream-v2",
        "model_id": "test-model-1",
        "network_id": "test-network-1",
        "antimony_text": VALID_DECAY_ANTIMONY,
        "antimony_generator_version": "test-generator-v0",
        "antimony_symbol_map": {
            "species": {"S1": "s_S1"},
            "reactions": {"reaction-1": "J1"},
            "parameters": {"k1": "p_k1"},
        },
        "readiness": "EXECUTABLE",
        "unresolved_reaction_ids": [],
        "unresolved_kinetic_law_ids": [],
        "compartments": [
            {
                "compartment_id": "C",
                "name": "C",
                "initial_volume": "1",
                "volume_unit": "L",
                "constant": True,
            }
        ],
        "species": [
            {
                "species_id": "S1",
                "name": "S1",
                "compartment_id": "C",
                "source_compound_id": "compound-1",
                "source_enzyme_state_id": None,
                "initial_amount": None,
                "initial_concentration": "10",
                "constant": False,
                "boundary_condition": False,
            }
        ],
        "reactions": [
            {
                "reaction_id": "reaction-1",
                "name": "decay",
                "reversible": False,
                "participants": [{"species_id": "S1", "role": "REACTANT", "stoichiometry": "1"}],
            }
        ],
        "kinetic_laws": [
            {
                "kinetic_law_id": "reaction-1::kinetic-law::none",
                "reaction_id": "reaction-1",
                "law_type": "MASS_ACTION",
                "expression": "k1 * S1",
                "parameter_ids": ["k1"],
                "species_ids": ["S1"],
                "enzyme_state_id": None,
                "protein_id": None,
                "complex_id": None,
                "assumptions": [],
            }
        ],
        "parameters": [
            {
                "parameter_id": "k1",
                "name": "k1",
                "source": "HEURISTIC_INITIALIZATION",
                "value": "0.5",
                "unit": "per_sec",
                "reaction_id": "reaction-1",
                "kinetic_law_assignment_id": "reaction-1::kinetic-law::none",
                "uncertainty_text": "Heuristic default; requires calibration.",
                "provenance_refs": ("measurement-abc-123",),
            }
        ],
        "model_assumptions": [
            {
                "assumption_id": "assumption-1",
                "category": "kinetics",
                "statement": "Reaction reaction-1 uses a tentative mass-action default.",
                "related_entity_ids": ["reaction-1"],
                "reason_code": "TENTATIVE_MASS_ACTION_DEFAULT",
            }
        ],
    }
    base.update(overrides)
    return base


__all__ = [
    "DIVERGENT_ANTIMONY",
    "INVALID_ANTIMONY",
    "NEGATIVE_CONCENTRATION_ANTIMONY",
    "SOLVER_FAILURE_ANTIMONY",
    "VALID_DECAY_ANTIMONY",
    "load_real_sce00061_handoff",
    "minimal_handoff_dict",
]
