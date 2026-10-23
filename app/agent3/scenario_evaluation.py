"""Whole-model experimental-scenario evaluation: the reliable prediction primitive a future
Agent 4 joint-optimization loop will call once per experiment, per candidate parameter vector.

This is **not** calibration or optimization -- it never fits anything, never holds an
optimizer loop, and never decides what to simulate; it takes an already-fully-resolved
scenario (explicit candidate parameter values, explicit initial-condition/step-intervention
overrides, explicit requested output times) and reports exactly what the model predicts.
Mirrors ``app.agent3.simulation``/``app.agent3.perturbation``'s own established discipline:
every numeric pathology is caught and reported as data (``ScenarioEvaluationStatus``), never
raised; every evaluation loads a fresh model instance (``app.agent3.loader
.load_antimony_model``) and never reuses or caches a ``roadrunner.RoadRunner`` instance across
calls, so two calls can never leak state into each other -- confirmed empirically (see
``tests/agent3/test_scenario_evaluation.py``'s own A->B->A isolation tests).

**Identifier validation happens here, against the real, compiled model** -- never trusted from
a caller's own catalog, which could in principle be stale relative to the actual artifact
(``ScenarioEvaluationStatus.INVALID_REQUEST``, carrying every unresolved identifier found,
never just the first). **Conflicting-assignment/dosing-schedule rejection is the caller's own
responsibility** (the Workbench validates its own configuration against its own catalogs and
dataset rows before ever building a request here) -- this module trusts that an already-built
``ScenarioEvaluationRequest`` represents one, single, already-resolved scenario; it applies
exactly what it is given, in the order described below, and never second-guesses it.

**Precedence/ordering, stated explicitly**: ``parameter_overrides``/``initial_value_overrides``
are applied once, before any integration begins (the trajectory's own starting state).
``interventions`` are step changes applied *during* the trajectory, each at its own declared
``time`` -- sorted ascending and applied in that order. A value requested at exactly the same
time an intervention takes effect is reported as the state *immediately before* that
intervention is applied (the "already observed, then the dose was given" reading) -- disclosed
here, once, as the one documented convention for this edge case, never left ambiguous per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import roadrunner

from app.agent3.loader import load_antimony_model
from app.agent3.simulation import DIVERGENCE_MAGNITUDE_THRESHOLD


class ScenarioEvaluationStatus(StrEnum):
    """The outcome of one ``ScenarioEvaluationRequest`` against one Antimony model.

    Deliberately distinct from ``app.agent3.types.SimulationStatus`` (which describes an
    *unmodified-model* baseline run) -- ``INVALID_REQUEST`` has no baseline-simulation analog
    at all, since a baseline run never takes explicit identifier-naming input to get wrong.

    ``SUCCESS`` -- the model loaded, every identifier resolved, and the integrator produced a
    finite, bounded trajectory for every requested time/output.
    ``MODEL_LOAD_FAILED`` -- the Antimony/SBML text itself could not be compiled; nothing about
    overrides, interventions, or outputs was ever checked.
    ``INVALID_REQUEST`` -- the model loaded, but at least one requested identifier (an override
    target, an intervention target, or a requested output) does not exist in the real, compiled
    model, or the request's own shape is otherwise unusable (e.g. a negative requested time, or
    no requested times/outputs at all) -- never guessed at or silently dropped; every such
    problem is collected and returned together, never just the first.
    ``SIMULATION_FAILED`` -- every identifier resolved, but the integrator itself raised (a
    solver exception, never a NaN/Inf/divergent value it actually produced -- that is
    ``NUMERICAL_INSTABILITY``).
    ``NUMERICAL_INSTABILITY`` -- the integrator produced at least one NaN/Inf value, or a value
    exceeding ``app.agent3.simulation.DIVERGENCE_MAGNITUDE_THRESHOLD``.
    """

    SUCCESS = "SUCCESS"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    NUMERICAL_INSTABILITY = "NUMERICAL_INSTABILITY"


@dataclass(frozen=True, slots=True)
class StepIntervention:
    """One step change applied *during* a trajectory, at its own declared ``time`` -- never
    merely the starting state (that is ``initial_value_overrides``/``parameter_overrides`` on
    ``ScenarioEvaluationRequest`` itself). ``target_kind`` names which real identifier
    namespace ``target_id`` is resolved against: ``"SPECIES"`` (a floating species' own current
    amount/concentration is set directly, exactly like a bolus dose) or ``"PARAMETER"`` (a
    global parameter's own value is set, exactly like ``parameter_overrides`` but taking effect
    partway through the trajectory instead of at its start)."""

    target_kind: str  # "SPECIES" | "PARAMETER"
    target_id: str
    time: float
    value: float


@dataclass(frozen=True, slots=True)
class ScenarioEvaluationRequest:
    """Deterministic configuration for one whole-model scenario evaluation. Every identifier
    field (``parameter_overrides``/``initial_value_overrides`` keys, every
    ``StepIntervention.target_id``, every ``requested_output_ids`` entry) must already be a
    real Antimony identifier of the model this request is evaluated against -- this module
    validates that, but never resolves a human-facing/catalog name on the caller's behalf.

    ``requested_times`` may be in any order, and may repeat a value (an irregular or
    duplicated-timepoint real dataset) -- predictions are returned in exactly this same order,
    one value per entry, never deduplicated or resorted.
    """

    request_id: str
    parameter_overrides: dict[str, float] = field(default_factory=dict)
    initial_value_overrides: dict[str, float] = field(default_factory=dict)
    interventions: tuple[StepIntervention, ...] = ()
    requested_times: tuple[float, ...] = ()
    requested_output_ids: tuple[str, ...] = ()
    integrator: str = "cvode"
    absolute_tolerance: float = 1e-10
    relative_tolerance: float = 1e-8


@dataclass(frozen=True, slots=True)
class ScenarioEvaluationResult:
    """The outcome of one ``ScenarioEvaluationRequest``.

    ``predictions`` is ``{output_id: (value_at_requested_times[0], value_at_requested_times[1],
    ...)}`` -- one tuple per requested output, each exactly as long as ``request
    .requested_times`` and in the identical order (including repeats) -- set only for
    ``SUCCESS``. ``validation_errors`` is set only for ``INVALID_REQUEST``, one human-readable
    string per distinct problem found.
    """

    request: ScenarioEvaluationRequest
    status: ScenarioEvaluationStatus
    predictions: dict[str, tuple[float, ...]] | None = None
    validation_errors: tuple[str, ...] = ()
    solver_message: str | None = None
    antimony_version: str | None = None
    engine_version: str | None = None


def _validate_request(
    rr: roadrunner.RoadRunner, request: ScenarioEvaluationRequest
) -> tuple[str, ...]:
    """Every distinct, actionable problem with ``request`` against the real, loaded model --
    empty means the request is usable. Never raises; collects every problem, not just the
    first (module docstring)."""
    errors: list[str] = []
    real_species = set(rr.model.getFloatingSpeciesIds())
    real_parameters = set(rr.model.getGlobalParameterIds())

    for pid in request.parameter_overrides:
        if pid not in real_parameters:
            errors.append(f"parameter_overrides names unresolved parameter id {pid!r}")
    for sid in request.initial_value_overrides:
        if sid not in real_species:
            errors.append(f"initial_value_overrides names unresolved species id {sid!r}")
    for iv in request.interventions:
        if iv.target_kind == "SPECIES" and iv.target_id not in real_species:
            errors.append(
                f"intervention names unresolved species id {iv.target_id!r} at time {iv.time!r}"
            )
        elif iv.target_kind == "PARAMETER" and iv.target_id not in real_parameters:
            errors.append(
                f"intervention names unresolved parameter id {iv.target_id!r} at time {iv.time!r}"
            )
        elif iv.target_kind not in ("SPECIES", "PARAMETER"):
            errors.append(
                f"intervention at time {iv.time!r} has unrecognized target_kind {iv.target_kind!r}"
            )
    for oid in request.requested_output_ids:
        if oid not in real_species:
            errors.append(f"requested_output_ids names unresolved species id {oid!r}")

    if not request.requested_output_ids:
        errors.append("requested_output_ids must not be empty")
    if not request.requested_times:
        errors.append("requested_times must not be empty")
    elif any(t < 0 for t in request.requested_times):
        errors.append("requested_times must not contain a negative value")
    if any(iv.time < 0 for iv in request.interventions):
        errors.append("every intervention's own time must not be negative")

    return tuple(errors)


def evaluate_scenario(
    antimony_text: str, request: ScenarioEvaluationRequest
) -> ScenarioEvaluationResult:
    """Evaluate one whole-model experimental scenario: load a fresh model, apply the
    request's own starting-state overrides, integrate through every requested time and every
    declared step intervention (in time order), and report the requested outputs aligned
    exactly to ``request.requested_times`` -- see module docstring for the full precedence/
    ordering contract.
    """
    load_result = load_antimony_model(antimony_text)
    if not load_result.succeeded or load_result.roadrunner_instance is None:
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.MODEL_LOAD_FAILED,
            solver_message=load_result.message,
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )
    rr = load_result.roadrunner_instance

    validation_errors = _validate_request(rr, request)
    if validation_errors:
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.INVALID_REQUEST,
            validation_errors=validation_errors,
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )

    rr.integrator.setValue("relative_tolerance", request.relative_tolerance)
    rr.integrator.setValue("absolute_tolerance", request.absolute_tolerance)

    try:
        for pid, value in request.parameter_overrides.items():
            rr[pid] = value
        for sid, value in request.initial_value_overrides.items():
            rr[sid] = value
    except Exception as exc:  # pragma: no cover - defensive; targets were just validated real
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.SIMULATION_FAILED,
            solver_message=f"Failed to apply a starting-state override: {exc}",
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )

    output_ids = list(request.requested_output_ids)
    rr.selections = ["time", *output_ids]

    # One evaluation moment per distinct requested time or intervention time, ascending --
    # t=0.0 is always included (the model's own integration-clock start), so the very first
    # segment's own starting state is always well-defined.
    interventions_by_time: dict[float, list[StepIntervention]] = {}
    for iv in request.interventions:
        interventions_by_time.setdefault(iv.time, []).append(iv)
    breakpoints = sorted({0.0, *request.requested_times, *interventions_by_time})

    collected: dict[float, dict[str, float]] = {}
    current_time = 0.0
    requested_time_set = set(request.requested_times)
    if 0.0 in requested_time_set:
        collected[0.0] = {oid: float(rr[oid]) for oid in output_ids}

    try:
        for breakpoint in breakpoints:
            if breakpoint > current_time:
                raw = rr.simulate(times=[current_time, breakpoint])
                array = np.asarray(raw)
                if breakpoint in requested_time_set:
                    collected[breakpoint] = {
                        oid: float(array[-1, i + 1]) for i, oid in enumerate(output_ids)
                    }
                current_time = breakpoint
            for iv in interventions_by_time.get(breakpoint, ()):
                rr[iv.target_id] = iv.value
    except Exception as exc:  # pragma: no cover - roadrunner raises plain Exception/RuntimeError
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.SIMULATION_FAILED,
            solver_message=f"Integration failed: {exc}",
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )

    all_values = np.array(
        [collected[t][oid] for t in request.requested_times for oid in output_ids], dtype=float
    )
    if np.isnan(all_values).any() or np.isinf(all_values).any():
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.NUMERICAL_INSTABILITY,
            solver_message="Simulation produced at least one NaN or Inf value.",
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )
    finite = all_values[np.isfinite(all_values)]
    if finite.size and np.abs(finite).max() > DIVERGENCE_MAGNITUDE_THRESHOLD:
        return ScenarioEvaluationResult(
            request=request,
            status=ScenarioEvaluationStatus.NUMERICAL_INSTABILITY,
            solver_message=(
                f"Simulation produced a value exceeding the divergence threshold "
                f"({DIVERGENCE_MAGNITUDE_THRESHOLD:g}): max |value| = {finite.max():g}."
            ),
            antimony_version=load_result.antimony_version,
            engine_version=roadrunner.__version__,
        )

    predictions = {
        oid: tuple(collected[t][oid] for t in request.requested_times) for oid in output_ids
    }
    return ScenarioEvaluationResult(
        request=request,
        status=ScenarioEvaluationStatus.SUCCESS,
        predictions=predictions,
        antimony_version=load_result.antimony_version,
        engine_version=roadrunner.__version__,
    )


__all__ = [
    "ScenarioEvaluationRequest",
    "ScenarioEvaluationResult",
    "ScenarioEvaluationStatus",
    "StepIntervention",
    "evaluate_scenario",
]
