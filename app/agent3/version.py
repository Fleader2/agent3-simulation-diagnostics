"""Agent 3 version/policy markers.

These are architecture/contract-shape version markers, not claims of scientific maturity
or simulation correctness. Bump a constant only when the shape or policy it names actually
changes -- mirrors ``app.agent2.version``'s own identical convention on the sibling
``agent2-antimony-builder`` repository.

* ``AGENT3_CONTRACT_VERSION`` -- the version of Agent 3's own output contract
  (``app.agent3.types``: ``Agent3Report`` and the rest).
* ``AGENT2_HANDOFF_CONTRACT_VERSION`` -- the version of the Agent 2 -> Agent 3 handoff
  contract this repository was built against (``app.agent3.handoff``, ``docs/
  02_agent2_to_agent3_contract.md``). Not a guarantee that every Agent 2 contract version is
  compatible -- version reconciliation is deferred, exactly as the Agent 1 -> Agent 2
  boundary's own ``AGENT1_HANDOFF_VERSION`` documents.
* ``SIMULATION_POLICY_VERSION`` -- the version of the baseline-simulation configuration
  policy (integrator choice, tolerances, default horizon/step count).
* ``DIAGNOSTIC_POLICY_VERSION`` -- the version of the diagnostic rule set (numerical
  pathology detection, conservation/mass-balance checks, provenance-tracing rules).
* ``PERTURBATION_POLICY_VERSION`` -- the version of the Version 1 perturbation smoke-test
  policy (which quantities are perturbed, by how much, and what "materially different" means).
"""

from __future__ import annotations

AGENT3_CONTRACT_VERSION = "0.1"
AGENT2_HANDOFF_CONTRACT_VERSION = "agent2-to-agent3-v1"
SIMULATION_POLICY_VERSION = "simulation-v1"
DIAGNOSTIC_POLICY_VERSION = "diagnostic-v1"
PERTURBATION_POLICY_VERSION = "perturbation-v1"

__all__ = [
    "AGENT2_HANDOFF_CONTRACT_VERSION",
    "AGENT3_CONTRACT_VERSION",
    "DIAGNOSTIC_POLICY_VERSION",
    "PERTURBATION_POLICY_VERSION",
    "SIMULATION_POLICY_VERSION",
]
