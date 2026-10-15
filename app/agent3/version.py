"""Agent 3 version/policy markers.

These are architecture/contract-shape version markers, not claims of scientific maturity
or simulation correctness. Bump a constant only when the shape or policy it names actually
changes -- mirrors ``app.agent2.version``'s own identical convention on the sibling
``agent2-antimony-builder`` repository.

* ``AGENT3_CONTRACT_VERSION`` -- the version of Agent 3's own output contract
  (``app.agent3.types``: ``Agent3Report`` and the rest).
* ``AGENT2_HANDOFF_CONTRACT_VERSION`` -- the version of the Agent 2 downstream handoff
  contract this repository was built against (``app.agent3.handoff``, ``docs/
  02_agent2_to_agent3_contract.md``). Five-Agent Workflow V1 Hardening increment: this is now
  ``"agent2-downstream-v1"``, the one canonical name Agent 2's own
  ``AGENT2_DOWNSTREAM_CONTRACT_VERSION`` emits and Agents 3, 4, and 5 all consume unchanged --
  replacing this repository's own previously-divergent ``"agent2-to-agent3-v1"`` name for what
  was already the identical real artifact shape. Not a guarantee that every Agent 2 contract
  version is compatible -- version reconciliation is deferred, exactly as the Agent 1 -> Agent 2
  boundary's own ``AGENT1_HANDOFF_VERSION`` documents.

  **Human-Readable Antimony Naming and Provenance Separation increment (Agent 2):** bumped
  ``"agent2-downstream-v1"`` -> ``"agent2-downstream-v2"``. Agent 2's generated Antimony symbols
  now prefer a curated biological name over a bare id, which this repository's own former
  ``app.agent3.antimony_ids`` module -- an independent re-implementation of Agent 2's *old*
  id-only naming rule -- could no longer resolve correctly. That module is removed entirely:
  Agent 2's own ``antimony_symbol_map`` field (new in v2) is the one source of truth for
  resolving a handoff entity id to its real, compiled Antimony identifier. See
  ``app.agent3.handoff.Agent2Handoff.antimony_symbol_map``.

  **Explicit Enzyme Concentration Representation increment (Agent 2):** bumped
  ``"agent2-downstream-v2"`` -> ``"agent2-downstream-v3"``, mirroring Agent 2's own real bump.
  Agent 2's handoff ``species[]`` gained ``source_protein_id`` (set only for an explicit
  catalytic-enzyme species) and ``kinetic_laws[]`` gained ``rate_law_scope``
  (``"EXPLICIT_ENZYME_CONCENTRATION"``/``"LUMPED_EFFECTIVE_RATE"``) -- both purely additive;
  this repository's own ``app.agent3.handoff`` parses every species/kinetic-law dict via
  ``.get(...)`` with no extra-key rejection, so the version bump alone (this repository does
  not yet read either new field) keeps parsing correct. Consuming them for Agent 3's own
  diagnostics is deferred to a future increment.
* ``SIMULATION_POLICY_VERSION`` -- the version of the baseline-simulation configuration
  policy (integrator choice, tolerances, default horizon/step count).
* ``DIAGNOSTIC_POLICY_VERSION`` -- the version of the diagnostic rule set (numerical
  pathology detection, conservation/mass-balance checks, provenance-tracing rules).
* ``PERTURBATION_POLICY_VERSION`` -- the version of the Version 1 perturbation smoke-test
  policy (which quantities are perturbed, by how much, and what "materially different" means).

**Functional Modularity Criteria from Agents 3 and 4 increment:** ``PerturbationResult`` gained
one new, additive field, ``relative_change_by_species`` -- the per-species relative-change
values ``max_relative_change_in_final_state`` was already computing internally and discarding
down to one scalar. No new computation: the identical ``diffs`` this module already derived is
now kept and returned instead of only its own ``max()``. ``AGENT3_CONTRACT_VERSION`` bumped
``"0.1"`` -> ``"0.2"`` (a real, if additive, ``Agent3Report``-nested shape change).
``PERTURBATION_POLICY_VERSION`` bumped ``"perturbation-v1"`` -> ``"perturbation-v2"`` -- the
policy of *what this module discloses* about an already-run perturbation changed, even though
the perturbation itself runs identically. ``run_agent3_pipeline`` itself (``app.agent3
.pipeline``) is unchanged -- it already accepted an explicit ``perturbation_specs`` override;
Agent 2's own new functional-evaluation requests (routed through a new, focused Harness-side
runner, never through this repository's own existing ``run_agent3.py`` whole-pipeline script)
simply supply their own target battery through that already-existing parameter.
"""

from __future__ import annotations

AGENT3_CONTRACT_VERSION = "0.2"
AGENT2_HANDOFF_CONTRACT_VERSION = "agent2-downstream-v3"
SIMULATION_POLICY_VERSION = "simulation-v1"
DIAGNOSTIC_POLICY_VERSION = "diagnostic-v1"
PERTURBATION_POLICY_VERSION = "perturbation-v2"

__all__ = [
    "AGENT2_HANDOFF_CONTRACT_VERSION",
    "AGENT3_CONTRACT_VERSION",
    "DIAGNOSTIC_POLICY_VERSION",
    "PERTURBATION_POLICY_VERSION",
    "SIMULATION_POLICY_VERSION",
]
