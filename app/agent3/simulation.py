"""Baseline time-course simulation and steady-state attempt.

Both functions operate on an already-loaded ``roadrunner.RoadRunner`` instance
(``app.agent3.loader.load_antimony_model``'s own output) -- neither loads, compiles, mutates a
kinetic law, changes a parameter value, or changes an initial concentration. Every numeric
pathology this module can encounter (a solver exception, a NaN/Inf value, a raised steady-state
failure) is caught and reported as data (``SimulationStatus``/``SteadyStateResult``), never
re-raised -- these are exactly the first-class outcomes this package exists to describe.
"""

from __future__ import annotations

import math

import numpy as np
import roadrunner

from app.agent3.types import (
    SimulationRequest,
    SimulationResult,
    SimulationStatus,
    SteadyStateResult,
)

#: Below this residual norm, ``roadrunner.RoadRunner.steadyState()`` is considered to have
#: genuinely converged (Version 1's own explicit numerical policy -- ``SIMULATION_POLICY_VERSION``
#: bumps if this threshold, or the steady-state method, ever changes).
_STEADY_STATE_RESIDUAL_TOLERANCE = 1e-6

#: Above this absolute magnitude, a finite (non-NaN/Inf) value is treated as a runaway/divergent
#: trajectory rather than merely a large-but-legitimate number -- deliberately generous (12
#: orders of magnitude above a typical nM-scale concentration) so a real, large-but-bounded
#: biological value is never mistaken for divergence; see ``docs/03_diagnostic_semantics.md``.
DIVERGENCE_MAGNITUDE_THRESHOLD = 1e12


def _species_ids(rr: roadrunner.RoadRunner) -> list[str]:
    return list(rr.model.getFloatingSpeciesIds())


def run_baseline_simulation(
    rr: roadrunner.RoadRunner,
    request: SimulationRequest,
    *,
    id_map: dict[str, str] | None = None,
) -> SimulationResult:
    """Run one deterministic time-course simulation exactly as configured by ``request``.

    Uses the model's own current state (whatever initial concentrations/parameter values Agent
    2 declared, completely unmodified) -- this function never sets, resets, or perturbs
    anything before simulating; a caller wanting a specific starting state must have already
    arranged it (``app.agent3.perturbation`` does this explicitly, and restores the original
    state afterward).

    ``id_map`` (``{antimony_species_id: original_agent2_species_id}``, typically
    ``app.agent3.handoff.species_antimony_id_map``'s own output -- the reverse of Agent 2's own
    ``antimony_symbol_map`` contract field) relabels every trajectory/state dict key back to
    the original Agent 2 entity id before returning -- without it (the default), keys are
    RoadRunner's own real Antimony identifiers verbatim, which is correct for a synthetic/
    hand-written model but would break provenance tracing for a real Agent 2 handoff, whose
    own ids are rendered as human-readable Antimony symbols by Agent 2
    (``app.agent2.antimony.naming`` on the sibling repository) rather than being usable
    verbatim. A key with no entry in ``id_map`` is left as-is, never dropped.
    """
    rr.integrator.setValue("relative_tolerance", request.relative_tolerance)
    rr.integrator.setValue("absolute_tolerance", request.absolute_tolerance)
    id_map = id_map or {}

    species_ids = _species_ids(rr)
    initial_state = {
        id_map.get(sid, sid): float(value)
        for sid, value in zip(species_ids, rr.model.getFloatingSpeciesConcentrations(), strict=True)
    }

    try:
        raw = rr.simulate(request.start_time, request.end_time, request.num_points)
    except Exception as exc:  # pragma: no cover - roadrunner raises plain Exception/RuntimeError
        return SimulationResult(
            request=request,
            status=SimulationStatus.SIMULATION_FAILED,
            initial_state=initial_state,
            solver_message=f"Integration failed: {exc}",
            engine_version=roadrunner.__version__,
        )

    array = np.asarray(raw)
    colnames = list(raw.colnames)
    time_points = tuple(float(v) for v in array[:, 0])

    trajectories: dict[str, tuple[float, ...]] = {}
    for col_index, col_name in enumerate(colnames[1:], start=1):
        species_id = id_map.get(col_name.strip("[]"), col_name.strip("[]"))
        trajectories[species_id] = tuple(float(v) for v in array[:, col_index])

    final_values = array[-1, 1:]
    final_state = {
        id_map.get(col_name.strip("[]"), col_name.strip("[]")): float(v)
        for col_name, v in zip(colnames[1:], final_values, strict=True)
    }

    flat_values = array[:, 1:].astype(float).ravel()
    if np.isnan(flat_values).any() or np.isinf(flat_values).any():
        return SimulationResult(
            request=request,
            status=SimulationStatus.NUMERICAL_INSTABILITY,
            time_points=time_points,
            species_trajectories=trajectories,
            initial_state=initial_state,
            final_state=final_state,
            solver_message="Simulation produced at least one NaN or Inf value.",
            engine_version=roadrunner.__version__,
        )

    finite_values = flat_values[np.isfinite(flat_values)]
    if finite_values.size and np.abs(finite_values).max() > DIVERGENCE_MAGNITUDE_THRESHOLD:
        return SimulationResult(
            request=request,
            status=SimulationStatus.NUMERICAL_INSTABILITY,
            time_points=time_points,
            species_trajectories=trajectories,
            initial_state=initial_state,
            final_state=final_state,
            solver_message=(
                f"Simulation produced a value exceeding the divergence threshold "
                f"({DIVERGENCE_MAGNITUDE_THRESHOLD:g}): max |value| = {finite_values.max():g}."
            ),
            engine_version=roadrunner.__version__,
        )

    return SimulationResult(
        request=request,
        status=SimulationStatus.SUCCESS,
        time_points=time_points,
        species_trajectories=trajectories,
        initial_state=initial_state,
        final_state=final_state,
        solver_message=None,
        engine_version=roadrunner.__version__,
    )


def attempt_steady_state(
    rr: roadrunner.RoadRunner, *, id_map: dict[str, str] | None = None
) -> SteadyStateResult:
    """Attempt RoadRunner's own steady-state solver (NLEQ) against the model's *current*
    state -- never resets or re-simulates first; a caller wanting "steady state from the
    baseline initial condition" should call this immediately after (or instead of) a baseline
    simulation on a freshly-loaded model, before any perturbation.

    ``id_map`` mirrors ``run_baseline_simulation``'s own identically-named, identically-reasoned
    parameter.
    """
    id_map = id_map or {}
    species_ids = [id_map.get(sid, sid) for sid in _species_ids(rr)]
    try:
        residual = rr.steadyState()
    except Exception as exc:
        return SteadyStateResult(
            attempted=True,
            converged=False,
            method="roadrunner.steadyState (NLEQ)",
            message=f"Steady-state solver raised: {exc}",
        )

    if not math.isfinite(residual):
        return SteadyStateResult(
            attempted=True,
            converged=False,
            method="roadrunner.steadyState (NLEQ)",
            max_abs_rate_of_change=None,
            message=f"Steady-state solver returned a non-finite residual: {residual!r}.",
        )

    converged = abs(residual) <= _STEADY_STATE_RESIDUAL_TOLERANCE
    values = dict(zip(species_ids, rr.model.getFloatingSpeciesConcentrations(), strict=True))
    return SteadyStateResult(
        attempted=True,
        converged=converged,
        method="roadrunner.steadyState (NLEQ)",
        max_abs_rate_of_change=float(abs(residual)),
        steady_state_values=values,
        message=(
            None
            if converged
            else (
                f"Steady-state solver returned without raising, but residual {residual!r} "
                f"exceeds this policy's own tolerance ({_STEADY_STATE_RESIDUAL_TOLERANCE:g})."
            )
        ),
    )


__all__ = [
    "DIVERGENCE_MAGNITUDE_THRESHOLD",
    "attempt_steady_state",
    "run_baseline_simulation",
]
