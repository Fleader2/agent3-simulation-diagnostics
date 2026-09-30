# Agent 3 — Responsibility Boundary

Agent 3 is the **Simulation and Model Diagnostics Agent** in the five-agent biochemical-modeling
pipeline (Agent 1 curation → Agent 2 model assembly → **Agent 3 simulation/diagnostics** →
Agent 4 calibration → Agent 5, not yet built). This document states what Agent 3 is responsible
for, what it explicitly refuses to do, and how it relates to its neighbors.

## Central rule

> Agent 3 analyzes the model it is given; it does not invent biology, silently repair
> parameters, or recalibrate the model.

Every design decision in this repository traces back to this one sentence. Agent 3 is a reader
and a reporter, never a writer, of biochemical content.

## What Agent 3 does

1. **Consumes** a plain, JSON-serializable handoff dict produced by (or standing in for) Agent 2
   — see `docs/02_agent2_to_agent3_contract.md` for the exact shape.
2. **Loads and compiles** the handoff's own `antimony_text` into a runnable simulation engine,
   reporting compilation failure as data, never raising it as an uncaught exception.
3. **Runs a deterministic baseline time-course simulation** at an explicit, recorded
   configuration (integrator, tolerances, horizon, step count).
4. **Attempts steady-state detection** against the model's own current (baseline) state.
5. **Detects and classifies numerical and structural pathology**: solver/integration failure,
   NaN/Inf, divergent/runaway trajectories, negative concentrations, trivial (unmoving)
   trajectories, missing initial conditions, and stoichiometry-implied conservation-law
   violations.
6. **Runs modest, deterministic perturbation smoke tests** (±10% on a small, fixed selection of
   parameters/initial concentrations) to check numerical stability under small nudges — not to
   fit or calibrate anything.
7. **Traces every finding back to the Agent 2 entity responsible** (species/reaction/parameter/
   assumption id, and any `provenance_refs` Agent 2 itself already recorded).
8. **Assembles a single structured `Agent3Report`** for Agent 4 or a human reviewer, disclosing
   overall status, every diagnostic finding, perturbation results, and Agent 2's own declared
   parameter-provenance breakdown (heuristic/placeholder counts) — as data, never as a pass/fail
   verdict on the science.

## What Agent 3 explicitly does NOT do

- **Does not alter kinetic laws, parameter values, or initial concentrations** to make a failing
  simulation pass. If the model fails, Agent 3 reports and traces the failure; it never patches
  around it.
- **Does not calibrate or optimize** anything. Perturbation smoke tests check stability and
  report magnitude of change — they never search for, or converge toward, a "better" parameter
  value. That is Agent 4's job entirely.
- **Does not invent missing biology.** A species with no declared initial condition is reported
  as a `missing-initial-conditions` finding; Agent 3 never assigns it a guessed value, not even a
  conventional default like `1.0`, beyond whatever SBML/Antimony itself defaults an unset species
  to (0), which is the simulation engine's behavior, not Agent 3's own choice.
- **Does not modify Agent 1 or Agent 2 code or output.** Every interface friction Agent 3 hit
  during Version 1 development (see `docs/02_agent2_to_agent3_contract.md` for the two concrete
  cases) was resolved entirely within Agent 3's own code — by re-deriving Agent 2's already-
  documented Antimony identifier convention and by relabeling trajectory keys — never by editing
  the sibling `agent2-antimony-builder` repository.
- **Does not import Agent 2's Python package.** Agent 3 consumes only the plain dict contract
  described in `docs/02_agent2_to_agent3_contract.md`, mirroring the existing Agent 1 → Agent 2
  boundary's own decoupling precedent (`app.agent2.handoff.translate_agent1_view_to_agent2`).
- **Does not make a scientific judgment about whether the model is "good."** A model that is
  100% heuristic-initialized and biologically trivial (e.g. the current real `sce00061` model,
  whose species all start at zero) can still be reported `sufficient_for_agent4=True`, because
  every reason for its triviality is fully disclosed with provenance. "Ran without lying about
  what happened" and "is scientifically mature" are deliberately different questions.
- **Does not decide when a model is "done."** Agent 3's `sufficient_for_agent4` flag means "this
  report carries enough structured, traceable information for Agent 4 to act on" — never
  "Agent 4 will succeed" or "no further curation is needed."

## Relationship to neighboring agents

| Agent | Relationship to Agent 3 |
|---|---|
| Agent 1 (curation) | Two hops upstream. Agent 3 never reads Agent 1 output directly. |
| Agent 2 (model assembly) | Directly upstream. Agent 3 consumes Agent 2's handoff contract (§02) and never imports Agent 2's Python package. |
| Agent 3 (this repository) | Simulates and diagnoses; never edits the model. |
| Agent 4 (calibration, not yet built) | Directly downstream. Consumes `Agent3Report` (§ types in `app/agent3/types.py`) to decide what to calibrate and how — Agent 3 hands it traceable findings, not fixes. |

## Distinguishing four classes of outcome

Version 1's own explicit requirement is that Agent 3 never conflates these:

1. **Model-structure failure** — the Antimony/SBML text itself could not be compiled
   (`SimulationStatus.MODEL_LOAD_FAILED`). Nothing about kinetics was ever evaluated.
2. **Numerical/solver failure** — the model compiled, but the ODE integrator could not produce a
   usable trajectory, or produced one that is pathological (`SIMULATION_FAILED`,
   `NUMERICAL_INSTABILITY`).
3. **Biologically questionable but numerically valid behavior** — the integrator succeeded with
   finite, bounded numbers, but something nonphysical happened (a negative concentration, a
   trivial unmoving trajectory) (`NONPHYSICAL_STATE`, or a `BIOLOGICALLY_QUESTIONABLE`-category
   finding alongside an otherwise-`SUCCESS` status).
4. **Heuristic-heavy but executable behavior** — the model runs cleanly, but a large fraction of
   its parameters are `HEURISTIC_INITIALIZATION`/`PLACEHOLDER` rather than evidence-backed
   (`DiagnosticCategory.HEURISTIC_PROVENANCE`, never itself a failure status).

See `docs/03_diagnostic_semantics.md` for the full rule-by-rule detail behind each of these.
