# Agent 2 → Agent 3 Contract (`agent2-downstream-v1`)

This is the smallest stable input shape Agent 3 Version 1 requires from Agent 2, expressed as a
plain, JSON-serializable dict (`app.agent3.handoff.parse_agent2_handoff` parses and validates it
into the frozen `Agent2Handoff` dataclass family in `app.agent3.handoff`). Agent 3 never imports
Agent 2's Python package and never constructs an Agent 2 `ModelSpecification`/
`FullAntimonyArtifact` object directly — this mirrors the existing, established Agent 1 → Agent 2
boundary pattern (`app.agent2.handoff.translate_agent1_view_to_agent2` on the sibling
`agent2-antimony-builder` repository) exactly. The two packages are decoupled at the code level;
only this documented data shape is shared, by convention.

**Five-Agent Workflow V1 Hardening increment:** this contract's own version name was
`"agent2-to-agent3-v1"` prior to this increment. It is now `"agent2-downstream-v1"` — the one
canonical name Agent 2's own `AGENT2_DOWNSTREAM_CONTRACT_VERSION`
(`app.agent2.pipeline.build_canonical_downstream_handoff` in `agent2-antimony-builder`) emits,
and the exact same name Agents 4 and 5 now also expect for what has always been the identical
real artifact shape. The shape itself is unchanged by this rename.

## Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `contract_version` | str | yes | Compared informationally against `app.agent3.version.AGENT2_HANDOFF_CONTRACT_VERSION` (`"agent2-downstream-v1"`). A mismatch is disclosed as a note on the report, never raised as an error — version reconciliation is deferred, exactly as the Agent 1 → Agent 2 boundary's own `AGENT1_HANDOFF_VERSION` precedent. |
| `model_id` | str | yes | Agent 2's own model identifier, carried through verbatim onto `Agent3Report.agent2_model_id`. |
| `network_id` | str | yes | Agent 2's own network identifier. |
| `antimony_text` | str | yes | The actual, compilable Antimony source. The *only* field handed to the simulation engine itself; everything else is metadata for provenance/diagnostics. |
| `antimony_generator_version` | str | yes | Agent 2's own generator version marker, carried through for traceability. |
| `readiness` | str | yes | Agent 2's own verdict on whether it claims this model is executable (e.g. `"EXECUTABLE"`). Carried through verbatim, never re-inferred from the Antimony text. |
| `unresolved_reaction_ids` | list[str] | no (default `[]`) | Reactions Agent 2 itself flagged as unresolved. |
| `unresolved_kinetic_law_ids` | list[str] | no (default `[]`) | Kinetic laws Agent 2 itself flagged as unresolved. |
| `compartments` | list[object] | no (default `[]`) | See below. |
| `species` | list[object] | no (default `[]`) | See below. |
| `reactions` | list[object] | no (default `[]`) | See below. |
| `kinetic_laws` | list[object] | no (default `[]`) | See below. |
| `parameters` | list[object] | no (default `[]`) | See below. |
| `model_assumptions` | list[object] | no (default `[]`) | See below. |

A missing *required* field (`contract_version`, `model_id`, `network_id`, `antimony_text`,
`antimony_generator_version`, `readiness`, or a required sub-field below) raises
`app.agent3.errors.HandoffContractError`. Agent 3 never fills in a missing value with a guessed
default.

## `compartments[]`

| Field | Type | Required |
|---|---|---|
| `compartment_id` | str | yes |
| `name` | str | yes |
| `initial_volume` | decimal-like (int/float/str) or null | no |
| `volume_unit` | str or null | no |
| `constant` | bool or null | no |

## `species[]`

| Field | Type | Required |
|---|---|---|
| `species_id` | str | yes |
| `name` | str | yes |
| `compartment_id` | str | yes |
| `source_compound_id` | str or null | no |
| `source_enzyme_state_id` | str or null | no |
| `initial_amount` | decimal-like or null | no |
| `initial_concentration` | decimal-like or null | no |
| `constant` | bool or null | no |
| `boundary_condition` | bool or null | no |

If both `initial_amount` and `initial_concentration` are null, Agent 3 flags this species in the
`missing-initial-conditions` diagnostic finding rather than assuming a value (see §03).

## `reactions[]`

| Field | Type | Required |
|---|---|---|
| `reaction_id` | str | yes |
| `name` | str or null | no |
| `reversible` | bool or null | no |
| `participants` | list[object] | no (default `[]`) |

Each `participants[]` entry:

| Field | Type | Required |
|---|---|---|
| `species_id` | str | yes |
| `role` | str (`"REACTANT"` \| `"PRODUCT"` \| other) | yes |
| `stoichiometry` | decimal-like | no (defaults to `1`) |

Used to build the (species × reaction) stoichiometry matrix for conservation checks
(`app.agent3.diagnostics.build_stoichiometry_matrix`) — reactants negative, products positive,
any other role contributes `0`.

## `kinetic_laws[]`

| Field | Type | Required |
|---|---|---|
| `kinetic_law_id` | str | yes |
| `reaction_id` | str | yes |
| `law_type` | str | yes |
| `expression` | str or null | no |
| `parameter_ids` | list[str] | no (default `[]`) |
| `species_ids` | list[str] | no (default `[]`) |
| `enzyme_state_id` | str or null | no |
| `protein_id` | str or null | no |
| `complex_id` | str or null | no |
| `assumptions` | list[str] | no (default `[]`) |

## `parameters[]`

| Field | Type | Required |
|---|---|---|
| `parameter_id` | str | yes |
| `name` | str | yes |
| `source` | str | yes |
| `value` | decimal-like or null | no |
| `unit` | str or null | no |
| `reaction_id` | str or null | no |
| `kinetic_law_assignment_id` | str or null | no |
| `uncertainty_text` | str or null | no |
| `provenance_refs` | list[str] | no (default `[]`) |

`source` is read verbatim by `app.agent3.diagnostics.heuristic_and_placeholder_parameters` to
classify every parameter as heuristic (`"HEURISTIC_INITIALIZATION"`), placeholder
(`"PLACEHOLDER"`), or evidence-backed (anything else) — a pure read of Agent 2's own declared
value, never a new judgment. `provenance_refs` is carried through unchanged onto any diagnostic
finding that cites this parameter.

## `model_assumptions[]`

| Field | Type | Required |
|---|---|---|
| `assumption_id` | str | yes |
| `category` | str | yes |
| `statement` | str | yes |
| `related_entity_ids` | list[str] | no (default `[]`) |
| `reason_code` | str or null | no |

Agent 2's own disclosed assumptions, carried through unchanged so a diagnostic finding can cite
the exact Agent 2 assumption text it corroborates, never re-deriving or rephrasing it.

## Antimony identifier sanitization (not part of the dict shape, but part of the contract)

Agent 2's Antimony generator sanitizes every entity id into an Antimony-legal identifier: strip
every character outside `[A-Za-z0-9_]` (replacing with `_`), then prefix by structural category
(`c_` compartments, `s_` species, `p_` parameters, `J_` reactions). Agent 3 re-implements this
same, documented, public rule independently in `app.agent3.antimony_ids` (never by importing
Agent 2's code) so that a diagnostic finding or perturbation target — both expressed in terms of
the raw entity ids above — can be mapped onto the identifiers the *compiled* model actually uses.
Every candidate identifier this produces is verified against the already-loaded model's own real
identifier list before being used; an unresolved candidate is reported as a
`MODEL_STRUCTURE`-category finding, never silently assumed correct or silently skipped.

## Two real interface frictions discovered and resolved (both inside Agent 3, no Agent 2 change)

1. **Antimony identifier mismatch.** Raw Agent 2 entity ids (UUID-like strings) are not valid
   Antimony identifiers and are not what the compiled model uses as symbol names — using them
   directly as RoadRunner lookup keys resolved nothing. Fixed entirely within Agent 3 by
   `app.agent3.antimony_ids`, re-deriving Agent 2's own already-documented sanitization rule.
2. **Trajectory/state key mismatch.** A loaded model's own trajectory and state dicts are keyed
   by the sanitized Antimony identifier, not the original Agent 2 entity id — left unmapped, this
   would have silently broken every `related_species_ids` provenance trace for a real handoff.
   Fixed entirely within Agent 3 by threading an `id_map` (built via
   `app.agent3.antimony_ids.build_species_antimony_id_map`) through
   `app.agent3.simulation.run_baseline_simulation`/`attempt_steady_state`.

Neither required a code change to `agent2-antimony-builder`; both are resolved by Agent 3
correctly re-deriving a convention Agent 2 already documents and exposes.

## A known, disclosed upstream scope gap (not an interface defect)

The current real `sce00061` Agent 2 output has **zero species with any declared initial
condition** (`initial_amount` and `initial_concentration` both null for all 53 species) — no
increment in the Agent 1/Agent 2 pipeline currently populates this field. This is not a defect in
the handoff contract or the Antimony generator (which does correctly emit `initial_amount`/
`initial_concentration` when Agent 2 sets them — confirmed by direct code inspection of
`app/agent2/antimony/generator.py`). Agent 3 detects and reports this
(`missing-initial-conditions`, see §03) rather than inventing a value or treating it as a defect
requiring an Agent 2 code change.
