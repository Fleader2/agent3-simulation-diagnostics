# Agent 3 — Simulation and Model Diagnostics

## Overview

Agent 3 is the third component of a multi-agent system for constructing scientifically
traceable, mechanistic models of microbial metabolism.

Agent 3 consumes the executable Antimony model produced by **Agent 2 — Antimony Builder** (a
separate repository, `agent2-antimony-builder`), simulates it deterministically, and produces a
structured diagnostic report for **Agent 4 — Calibration** (not yet built).

**Central rule:** Agent 3 analyzes the model it is given; it does not invent biology, silently
repair parameters, or recalibrate the model. If the model fails, Agent 3 reports and traces the
failure — it never edits a kinetic law, parameter value, or initial concentration to make a
simulation "pass."

Agent 3 does **not**:

- curate literature or biological database records (Agent 1's job),
- assemble a model or declare its kinetic laws/parameters (Agent 2's job),
- calibrate, fit, or optimize any parameter against experimental data (Agent 4's job),
- critique a model's biological plausibility in the full sense Agent 5 will.

Agent 3 consumes Agent 2's output through an explicit, versioned handoff contract (a plain,
JSON-serializable dict) — it never imports Agent 2's runtime code.

See `docs/01_agent3_responsibility_boundary.md`, `docs/02_agent2_to_agent3_contract.md`, and
`docs/03_diagnostic_semantics.md` for full detail.

## Canonical workflow

```text
Agent2Handoff (Antimony text + structural/provenance metadata)
        ↓
Load / compile (antimony → SBML → RoadRunner)
        ↓
Baseline deterministic simulation
        ↓
Steady-state attempt
        ↓
Diagnostics (numerical pathology, conservation checks, provenance tracing)
        ↓
Perturbation smoke tests (±10%, deterministic, one target at a time)
        ↓
Agent3Report
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Dependencies: `antimony`, `libroadrunner`, `python-libsbml`, `numpy`, `scipy` — the smallest
credible package set for headless Antimony simulation, chosen over the heavier `tellurium`
meta-package (see `docs/03_diagnostic_semantics.md`).

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```
