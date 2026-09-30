# Agent 3 — Diagnostic Semantics (`diagnostic-v1`)

This document formalizes every threshold, rule, and status-precedence decision implemented in
`app.agent3.simulation`, `app.agent3.diagnostics`, `app.agent3.perturbation`, and
`app.agent3.report`. It exists so a threshold change is a deliberate, documented, version-bumped
decision, never a silent drift between code and explanation.

## Simulation engine and configuration (`simulation-v1`)

- **Engine**: `antimony` (Antimony → SBML translation) + `libroadrunner` (SBML → ODE simulation,
  imported as `roadrunner`), not the heavier `tellurium` meta-package. See "Simulator dependency
  choice" below.
- **Integrator**: CVODE (RoadRunner's default), explicitly configured per `SimulationRequest`
  with `absolute_tolerance=1e-10`, `relative_tolerance=1e-8` by default.
- **Default baseline horizon** (`app.agent3.pipeline.DEFAULT_SIMULATION_REQUEST`):
  `start_time=0.0`, `end_time=1000.0`, `num_points=200` — a generic, unit-agnostic window chosen
  because the handoff contract carries no per-reaction characteristic timescale to derive a
  better one from. Bump `SIMULATION_POLICY_VERSION` if this default changes.
- **Determinism**: no random seed is consulted anywhere in the simulation path; identical inputs
  produce identical outputs on the same platform/library version (recorded via `engine_version`
  on every `SimulationResult`).

## Simulation outcome classification (`app.agent3.simulation.run_baseline_simulation`)

Evaluated in this fixed order, first match wins:

1. **`rr.simulate(...)` raises** → `SimulationStatus.SIMULATION_FAILED`, with the exception text
   preserved verbatim in `solver_message` as `"Integration failed: {exc}"`. This is the "solver/
   integration failure" case — the integrator never produced a usable trajectory at all.
2. **Any NaN or Inf appears anywhere in the returned trajectory** →
   `SimulationStatus.NUMERICAL_INSTABILITY`, `solver_message="Simulation produced at least one
   NaN or Inf value."` In practice (confirmed empirically across many fixture constructions this
   session), CVODE tends to *raise* (case 1) rather than silently propagate NaN/Inf through an
   otherwise-successful trajectory — this branch exists and is tested via a hand-constructed
   `SimulationResult` for the cases where it does not.
3. **Any finite value's absolute magnitude exceeds `DIVERGENCE_MAGNITUDE_THRESHOLD = 1e12`** →
   `SimulationStatus.NUMERICAL_INSTABILITY`, with the offending max value reported in
   `solver_message`. `1e12` is deliberately generous — 12 orders of magnitude above a typical
   nanomolar-scale concentration — so a real, large-but-bounded biological value is never
   mistaken for divergence.
4. **Otherwise** → `SimulationStatus.SUCCESS`.

A **negative concentration is not itself a `SimulationStatus` outcome** — it is numerically valid
(no integration error, finite value) and is instead surfaced as a `BIOLOGICALLY_QUESTIONABLE`
diagnostic finding (below) while the simulation status itself remains `SUCCESS`. This is the
deliberate split Version 1 requires: "numerical/solver failure" and "biologically questionable
but numerically valid" are different axes and must never be conflated into one status value.

## Steady-state attempt (`app.agent3.simulation.attempt_steady_state`)

- Uses RoadRunner's own NLEQ-based `rr.steadyState()` against the model's *current* state (never
  resets or re-simulates first).
- `attempted=True` whenever the attempt is made at all (i.e. baseline load succeeded);
  `converged=True` iff `rr.steadyState()` returns without raising **and** the returned residual
  is finite **and** `abs(residual) <= _STEADY_STATE_RESIDUAL_TOLERANCE (1e-6)`.
- A raised exception (e.g. a singular Jacobian — the real, reproduced `sce00061` case) is caught
  and reported as `converged=False` with the solver's own exception text preserved verbatim in
  `message`, never re-raised.
- `attempted=False` only when steady state was never even tried (e.g. because baseline load
  itself already failed) — never conflated with `attempted=True, converged=False`.

## Overall run status precedence (`app.agent3.report.determine_overall_status`)

Most to least severe, first match wins:

1. Load failed, or no simulation was ever produced → `MODEL_LOAD_FAILED`.
2. Baseline simulation's own status is not `SUCCESS` → that status (`SIMULATION_FAILED` or
   `NUMERICAL_INSTABILITY`) is propagated as the overall status.
3. Baseline simulation succeeded, but steady state was attempted and did not converge →
   `STEADY_STATE_NOT_FOUND`.
4. Otherwise → `SUCCESS`.

A model can be `SUCCESS` overall while still carrying `WARNING`/`ERROR`-severity diagnostic
findings (e.g. a negative concentration, or a heuristic-provenance disclosure) — `overall_status`
answers "did the simulation and steady-state machinery itself work," never "is everything about
this model fine."

## Diagnostic findings (`app.agent3.diagnostics`)

Each rule below is a pure function of an already-produced `SimulationResult`/`SteadyStateResult`
plus the original `Agent2Handoff` — none of them mutate the model or decide the overall status.

| Finding | Category | Severity | Trigger |
|---|---|---|---|
| `heuristic-provenance-summary` | `HEURISTIC_PROVENANCE` | INFO | Always emitted when `handoff.parameters` is non-empty; discloses `(heuristic + placeholder) / total` fraction. Never a failure signal — a model can be `SUCCESS` and 100% heuristic at once. |
| `missing-initial-conditions` | `MODEL_STRUCTURE` | WARNING | At least one species has both `initial_amount` and `initial_concentration` null. |
| `trivial-trajectory` | `BIOLOGICALLY_QUESTIONABLE` | WARNING | Every species' trajectory range (`max - min`) is below `1e-12` across the whole horizon (and all values finite) — the system never leaves its initial state, despite no integration error. |
| `solver-message` | `NUMERICAL_SOLVER` | CRITICAL (if `SIMULATION_FAILED`) or ERROR (if `NUMERICAL_INSTABILITY`) | `sim.solver_message` is set. Reported verbatim; Agent 3 never re-interprets or retries with different tolerances. |
| `negative-concentration:{species_id}` | `BIOLOGICALLY_QUESTIONABLE` | ERROR | A species' trajectory's finite minimum is `< 0`. One finding per affected species, each tracing to every reaction that has that species as a participant. |
| `divergent-trajectory:{species_id}` | `NUMERICAL_SOLVER` | CRITICAL | A species' finite trajectory values exceed `DIVERGENCE_MAGNITUDE_THRESHOLD (1e12)` in absolute value. Complements the aggregate `NUMERICAL_INSTABILITY` status by naming exactly which species runs away. |
| `nan-inf:{species_id}` | `NUMERICAL_SOLVER` | CRITICAL | A species' trajectory contains any NaN or Inf value. |
| `conservation-none-found` | `CONSERVATION` | INFO | The stoichiometry matrix's left null space is trivial — no structural conservation law is implied by the network topology. Not a failure; a statement about topology. |
| `conservation-held` | `CONSERVATION` | INFO | Every stoichiometry-implied conserved quantity drifted by no more than `_CONSERVATION_DRIFT_TOLERANCE (1e-6)` across the simulated trajectory. |
| `conservation-violated` | `CONSERVATION` | ERROR | At least one stoichiometry-implied conserved quantity drifted by more than `1e-6` — a genuine solver-precision or model-construction inconsistency, never a biological judgment. |
| `steady-state-not-found` | `NUMERICAL_SOLVER` | WARNING | `SteadyStateResult.attempted=True, converged=False`. Emitted only when a steady-state attempt actually ran and failed; `None` when it converged. |
| `perturbation-target-unresolved:{kind}:{id}` | `MODEL_STRUCTURE` | WARNING | A perturbation's candidate Antimony identifier was not found among the loaded model's own real identifiers. No perturbation is applied for this target. |
| `perturbation-apply-error:{kind}:{id}` | `NUMERICAL_SOLVER` | ERROR | RoadRunner raised while setting an already-verified target identifier (defensive; not expected in practice). |

### Conservation-law derivation

`app.agent3.diagnostics.build_stoichiometry_matrix` builds the (species × reaction) matrix purely
from `HandoffReaction.participants` (reactant role → `-stoichiometry`, product role →
`+stoichiometry`, any other role → `0`) — a pure structural fact, no kinetics involved. Its left
null space (`scipy.linalg.null_space` on the matrix transpose) gives every linear combination of
species concentrations that stoichiometry alone guarantees must stay constant regardless of rate
law choice. `conservation_findings` then checks whether each such combination actually did stay
constant (within `1e-6`) across the real simulated trajectory — a genuine numerical/model-
construction consistency check, never a claim about whether the biology itself is correct.

### Provenance tracing

`app.agent3.diagnostics.parameter_provenance_refs(handoff, parameter_id)` looks up and returns
exactly whatever `provenance_refs` Agent 2 already recorded for that parameter — never invented,
never dropped. Every finding that names a `related_parameter_ids`/`related_species_ids`/
`related_reaction_ids`/`related_assumption_ids` uses Agent 2's own already-declared ids
throughout; Agent 3 never invents a new identifier for something Agent 2 already named.

## Perturbation smoke tests (`perturbation-v1`)

- **Selection** (`select_default_perturbation_targets`): the first `DEFAULT_MAX_TARGETS_PER_KIND`
  (5) parameters, sorted by `parameter_id`, that carry a real nonzero declared value, plus the
  first 5 species, sorted by `species_id`, regardless of their own initial value. A fixed,
  structural policy — never tuned per run.
- **Magnitude**: `DEFAULT_PERTURBATION_FRACTION = 0.10` (±10%), one target changed at a time
  (never a combination), so each result is attributable to exactly one changed quantity.
- **Isolation**: each perturbation loads a **fresh** RoadRunner instance from the same,
  unmodified `Agent2Handoff.antimony_text` — never reuses or mutates a shared instance. This is
  the mechanism that guarantees Agent 3 never mutates Agent 2's own input artifacts: the original
  Antimony text is only ever read, never written.
- **Target resolution**: the candidate Antimony identifier is checked against the freshly-loaded
  model's own real identifier list (`rr.model.getGlobalParameterIds()`/
  `getFloatingSpeciesIds()`) before use — an unresolved candidate produces a `MODEL_STRUCTURE`
  finding and `SimulationStatus.SIMULATION_FAILED` for that one perturbation, never a silent skip
  or a guessed identifier.
- **Stability verdict**: `remained_numerically_stable = sim.status in (SUCCESS,
  STEADY_STATE_NOT_FOUND)` — a perturbation that still integrates cleanly (even if steady state
  itself isn't reached) counts as numerically stable; anything else does not.
- **Material-change comparison**: the perturbed run's final state is compared against a second,
  independently-loaded, unperturbed baseline run under identical `SimulationRequest` conditions
  (never a cached baseline from elsewhere) — `max_relative_change_in_final_state` is the largest
  `|perturbed - base| / max(|base|, 1.0-if-base-is-0)` across all species. This package does not
  currently classify this magnitude into a discrete "materially different" flag on
  `PerturbationResult` itself (that comparison, and any threshold on it, is left to the consuming
  report/reader); a `_MATERIAL_CHANGE_RELATIVE_THRESHOLD = 1e-3` constant is defined in
  `app.agent3.perturbation` for this purpose but not yet wired into a dedicated finding — a
  candidate for a future version, not a Version 1 gap that blocks Agent 4.
- **Never calibration**: no search, fitting, or optimization ever occurs here — a perturbation
  result only reports "stable or not, and how much the output moved," never a recommended
  parameter value.

## `sufficient_for_agent4` (`app.agent3.report.determine_agent4_sufficiency`)

- `False` only when `overall_status is MODEL_LOAD_FAILED` — there is no simulation/diagnostic
  content at all for Agent 4 to act on beyond the load failure message.
- `True` (with a note that calibration cannot proceed until the failure is fixed) when the model
  loaded but baseline simulation failed/was unstable and at least one `CRITICAL`-severity finding
  exists — Agent 4 can still see which reaction/parameter to inspect first.
- `True` (fully sufficient) otherwise — including the degenerate case where the model is
  `SUCCESS` but trivial (e.g. the real `sce00061` all-zero-initial-condition run): every reason
  for the triviality is disclosed with full provenance, which is what "sufficient" means here.
- This flag is never a scientific-quality judgment — only a completeness/traceability one.

## Simulator dependency choice

`antimony` + `libroadrunner` + `python-libsbml` were chosen over the `tellurium` convenience
meta-package. `tellurium` re-exports the same Antimony/RoadRunner functionality Agent 3 needs, but
additionally pulls in `jupyter`, `matplotlib`, `pandas`, `plotly`, and other notebook/plotting
dependencies unrelated to Agent 3's own job of headless simulation and diagnostics. Installing the
three underlying packages directly is the smallest credible dependency set that satisfies the
Version 1 requirement ("preferably Tellurium/RoadRunner... if unsuitable, use the smallest
credible alternative and explain your choice").
