"""Version 1 perturbation/sensitivity smoke tests.

Deliberately modest and deterministic, exactly as the Version 1 instructions specify: a fixed,
small, sorted-by-id selection of parameters and/or species initial concentrations, each nudged
by one fixed fraction (+/-10% by default), one target at a time. This is **not** calibration or
optimization (that is explicitly Agent 4's job) -- it only checks whether the perturbed model
remains numerically stable and reports how much the final state changed, never fitting anything
to a target.

Every perturbation loads a **fresh** model instance from the same, unmodified
``Agent2Handoff.antimony_text`` (never reusing, and therefore never risking leaking state into,
the instance any other perturbation or the baseline run used) -- this is also what guarantees
"no mutation of Agent 2 input artifacts": the original Antimony text is only ever read, never
written, and each perturbation's change lives solely in its own throwaway RoadRunner instance.
"""

from __future__ import annotations

from app.agent3.diagnostics import run_all_diagnostics
from app.agent3.handoff import Agent2Handoff, species_antimony_id_map
from app.agent3.loader import load_antimony_model
from app.agent3.simulation import run_baseline_simulation
from app.agent3.types import (
    DiagnosticCategory,
    DiagnosticFinding,
    DiagnosticSeverity,
    PerturbationResult,
    PerturbationSpec,
    SimulationRequest,
    SimulationStatus,
)

#: Version 1's own default perturbation fraction (+/-10%, per the instructions' own example).
DEFAULT_PERTURBATION_FRACTION = 0.10

#: How many parameters/species this Version 1 policy selects by default -- "intentionally
#: modest" per the instructions; bump ``PERTURBATION_POLICY_VERSION`` if this changes.
DEFAULT_MAX_TARGETS_PER_KIND = 5

#: Above this relative change in final state, a perturbation's output is reported as
#: "materially different" rather than "no material change."
_MATERIAL_CHANGE_RELATIVE_THRESHOLD = 1e-3


def select_default_perturbation_targets(
    handoff: Agent2Handoff,
    *,
    max_parameters: int = DEFAULT_MAX_TARGETS_PER_KIND,
    max_species: int = DEFAULT_MAX_TARGETS_PER_KIND,
    fraction: float = DEFAULT_PERTURBATION_FRACTION,
) -> tuple[PerturbationSpec, ...]:
    """A fixed, deterministic selection: the first ``max_parameters`` parameters (sorted by
    ``parameter_id``) that carry a real, nonzero numeric value, and the first ``max_species``
    species (sorted by ``species_id``), regardless of their own initial value -- the latter is
    deliberately unfiltered even though every species in the current real handoff has no
    declared initial value (see the report's own disclosure of what that makes of these
    specific perturbations): Version 1's own selection policy is structural, not tuned per run.
    """
    parameter_candidates = sorted(
        (p for p in handoff.parameters if p.value is not None and p.value != 0),
        key=lambda p: p.parameter_id,
    )
    species_candidates = sorted(handoff.species, key=lambda s: s.species_id)

    specs = [
        PerturbationSpec(target_kind="PARAMETER", target_id=p.parameter_id, fraction=fraction)
        for p in parameter_candidates[:max_parameters]
    ]
    specs += [
        PerturbationSpec(
            target_kind="INITIAL_CONCENTRATION", target_id=s.species_id, fraction=fraction
        )
        for s in species_candidates[:max_species]
    ]
    return tuple(specs)


def _baseline_value_for(handoff: Agent2Handoff, spec: PerturbationSpec) -> float:
    if spec.target_kind == "PARAMETER":
        for p in handoff.parameters:
            if p.parameter_id == spec.target_id:
                return float(p.value) if p.value is not None else 0.0
        return 0.0
    for s in handoff.species:
        if s.species_id == spec.target_id:
            if s.initial_concentration is not None:
                return float(s.initial_concentration)
            if s.initial_amount is not None:
                return float(s.initial_amount)
            return 0.0
    return 0.0


def run_perturbation(
    handoff: Agent2Handoff, spec: PerturbationSpec, baseline_request: SimulationRequest
) -> PerturbationResult:
    """Run one perturbation smoke test against a fresh copy of the model.

    Never touches ``handoff.antimony_text`` itself -- a brand-new RoadRunner instance is
    compiled from it, exactly as the unperturbed baseline was, and only that one throwaway
    instance's own in-memory state is changed.
    """
    baseline_value = _baseline_value_for(handoff, spec)
    perturbed_value = baseline_value * (1.0 + spec.fraction)

    load_result = load_antimony_model(handoff.antimony_text)
    if not load_result.succeeded or load_result.roadrunner_instance is None:
        return PerturbationResult(
            spec=spec,
            baseline_value=baseline_value,
            perturbed_value=perturbed_value,
            simulation_status=SimulationStatus.MODEL_LOAD_FAILED,
            remained_numerically_stable=False,
        )

    rr = load_result.roadrunner_instance
    if spec.target_kind == "PARAMETER":
        candidate = handoff.antimony_symbol_map.parameters.get(spec.target_id)
        real_ids = set(rr.model.getGlobalParameterIds())
    else:
        candidate = handoff.antimony_symbol_map.species.get(spec.target_id)
        real_ids = set(rr.model.getFloatingSpeciesIds())

    if candidate is None or candidate not in real_ids:
        unresolved_finding = DiagnosticFinding(
            finding_id=f"perturbation-target-unresolved:{spec.target_kind}:{spec.target_id}",
            category=DiagnosticCategory.MODEL_STRUCTURE,
            severity=DiagnosticSeverity.WARNING,
            summary=(
                f"Could not resolve perturbation target {spec.target_id!r} "
                f"(candidate Antimony id {candidate!r}) against the loaded model."
            ),
            explanation=(
                "Agent 2's own antimony_symbol_map carried no entry for this handoff entity "
                "id (or the entry it carried does not appear among the loaded model's own "
                "real identifiers). This is reported rather than "
                "guessed at -- no perturbation was applied for this target."
            ),
            related_parameter_ids=(spec.target_id,) if spec.target_kind == "PARAMETER" else (),
            related_species_ids=(spec.target_id,)
            if spec.target_kind == "INITIAL_CONCENTRATION"
            else (),
        )
        return PerturbationResult(
            spec=spec,
            baseline_value=baseline_value,
            perturbed_value=perturbed_value,
            simulation_status=SimulationStatus.SIMULATION_FAILED,
            remained_numerically_stable=False,
            findings=(unresolved_finding,),
        )

    try:
        rr[candidate] = perturbed_value
    except Exception as exc:  # pragma: no cover - defensive; candidate is now a verified real id
        return PerturbationResult(
            spec=spec,
            baseline_value=baseline_value,
            perturbed_value=perturbed_value,
            simulation_status=SimulationStatus.SIMULATION_FAILED,
            remained_numerically_stable=False,
            findings=(
                DiagnosticFinding(
                    finding_id=f"perturbation-apply-error:{spec.target_kind}:{spec.target_id}",
                    category=DiagnosticCategory.NUMERICAL_SOLVER,
                    severity=DiagnosticSeverity.ERROR,
                    summary=f"Failed to apply perturbation: {exc}",
                    explanation="RoadRunner raised while setting the verified target identifier.",
                ),
            ),
        )

    id_map = species_antimony_id_map(handoff)
    sim = run_baseline_simulation(rr, baseline_request, id_map=id_map)
    findings = run_all_diagnostics(handoff, sim)

    remained_stable = sim.status in (
        SimulationStatus.SUCCESS,
        SimulationStatus.STEADY_STATE_NOT_FOUND,
    )

    max_relative_change: float | None = None
    if sim.final_state is not None:
        # Compare against the *unperturbed* baseline final state by running it once more under
        # identical conditions from a second fresh instance -- never reusing a cached baseline
        # result from elsewhere, so each perturbation's own comparison is fully self-contained.
        baseline_load = load_antimony_model(handoff.antimony_text)
        if baseline_load.succeeded and baseline_load.roadrunner_instance is not None:
            baseline_sim = run_baseline_simulation(
                baseline_load.roadrunner_instance, baseline_request, id_map=id_map
            )
            if baseline_sim.final_state is not None:
                diffs = []
                for species_id, perturbed_final in sim.final_state.items():
                    base_final = baseline_sim.final_state.get(species_id, 0.0)
                    denom = abs(base_final) if base_final != 0 else 1.0
                    diffs.append(abs(perturbed_final - base_final) / denom)
                max_relative_change = max(diffs) if diffs else 0.0

    return PerturbationResult(
        spec=spec,
        baseline_value=baseline_value,
        perturbed_value=perturbed_value,
        simulation_status=sim.status,
        remained_numerically_stable=remained_stable,
        max_relative_change_in_final_state=max_relative_change,
        findings=findings,
    )


def run_perturbation_smoke_tests(
    handoff: Agent2Handoff,
    baseline_request: SimulationRequest,
    specs: tuple[PerturbationSpec, ...] | None = None,
) -> tuple[PerturbationResult, ...]:
    """Run every perturbation in ``specs`` (or Version 1's own default selection) and return
    the results in the same, deterministic order they were specified."""
    if specs is None:
        specs = select_default_perturbation_targets(handoff)
    return tuple(run_perturbation(handoff, spec, baseline_request) for spec in specs)


__all__ = [
    "DEFAULT_MAX_TARGETS_PER_KIND",
    "DEFAULT_PERTURBATION_FRACTION",
    "run_perturbation",
    "run_perturbation_smoke_tests",
    "select_default_perturbation_targets",
]
