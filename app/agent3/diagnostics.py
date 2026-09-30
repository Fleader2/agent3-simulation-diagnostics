"""Diagnostic rules: numerical pathology, structural/conservation checks, and provenance tracing.

Every function here is a pure, read-only analysis of an already-produced
``SimulationResult``/``SteadyStateResult`` plus the original ``Agent2Handoff`` -- none of them
mutate the loaded model, none of them change a parameter or initial value, and none of them
decide whether the *overall* run "passed" (that is ``app.agent3.report.determine_overall_status``
's own job, from the same inputs these functions annotate). See
``docs/03_diagnostic_semantics.md`` for the full rationale behind each rule's own threshold.
"""

from __future__ import annotations

import numpy as np

from app.agent3.handoff import Agent2Handoff
from app.agent3.simulation import DIVERGENCE_MAGNITUDE_THRESHOLD
from app.agent3.types import (
    DiagnosticCategory,
    DiagnosticFinding,
    DiagnosticSeverity,
    SimulationResult,
    SteadyStateResult,
)

#: Below this absolute drift, a quantity the stoichiometry matrix's own null space predicts
#: should be exactly conserved is treated as "held" rather than "violated" -- accounts for
#: ordinary floating-point/ODE-integrator roundoff, never a real biological tolerance.
_CONSERVATION_DRIFT_TOLERANCE = 1e-6

#: Below this absolute range (max - min) across an entire simulated horizon, a species'
#: trajectory is treated as "did not move at all" for the trivial-trajectory finding.
_TRIVIAL_TRAJECTORY_RANGE_TOLERANCE = 1e-12


def _parameter_lookup(handoff: Agent2Handoff) -> dict[str, object]:
    return {p.parameter_id: p for p in handoff.parameters}


def _species_lookup(handoff: Agent2Handoff) -> dict[str, object]:
    return {s.species_id: s for s in handoff.species}


def parameter_provenance_refs(handoff: Agent2Handoff, parameter_id: str) -> tuple[str, ...]:
    """Every provenance reference Agent 2 itself already recorded for ``parameter_id`` --
    never invented here, only looked up and carried through (this function's entire reason to
    exist: satisfy "preservation of Agent 2 provenance/assumption references in diagnostic
    output" without any finding-construction code duplicating this lookup by hand)."""
    param = _parameter_lookup(handoff).get(parameter_id)
    return param.provenance_refs if param is not None else ()


def heuristic_and_placeholder_parameters(
    handoff: Agent2Handoff,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(heuristic_parameter_ids, placeholder_parameter_ids)`` -- a pure classification of
    Agent 2's own already-declared ``source`` field, never a new judgment. Used both to
    populate ``Agent3Report``'s own dedicated fields and to build the one summary
    ``HEURISTIC_PROVENANCE`` finding below."""
    heuristic = tuple(
        p.parameter_id for p in handoff.parameters if p.source == "HEURISTIC_INITIALIZATION"
    )
    placeholder = tuple(p.parameter_id for p in handoff.parameters if p.source == "PLACEHOLDER")
    return heuristic, placeholder


def heuristic_provenance_finding(handoff: Agent2Handoff) -> DiagnosticFinding | None:
    """One summary finding disclosing how heuristic-dependent the model is -- Version 1's own
    explicit "heuristic-heavy but executable behavior" distinction, reported as data, never as
    a reason to treat the run as failed (a model can be ``SUCCESS`` and 100% heuristic at once)."""
    heuristic, placeholder = heuristic_and_placeholder_parameters(handoff)
    total = len(handoff.parameters)
    if total == 0:
        return None
    fraction = (len(heuristic) + len(placeholder)) / total
    return DiagnosticFinding(
        finding_id="heuristic-provenance-summary",
        category=DiagnosticCategory.HEURISTIC_PROVENANCE,
        severity=DiagnosticSeverity.INFO,
        summary=(
            f"{len(heuristic)} of {total} parameters are HEURISTIC_INITIALIZATION and "
            f"{len(placeholder)} are PLACEHOLDER ({fraction:.0%} non-evidence-backed)."
        ),
        explanation=(
            "This is a disclosure of Agent 2's own declared parameter provenance, carried "
            "through unchanged -- never a simulation failure. A model may be numerically "
            "SUCCESS and almost entirely heuristic-initialized at the same time; this finding "
            "exists so a downstream consumer never conflates 'ran without error' with "
            "'evidence-backed.'"
        ),
        related_parameter_ids=heuristic + placeholder,
    )


def missing_initial_condition_finding(handoff: Agent2Handoff) -> DiagnosticFinding | None:
    """Flags species with neither ``initial_amount`` nor ``initial_concentration`` declared --
    a real, structural Agent 2 (upstream: Agent 1) gap, never repaired or guessed at here."""
    missing = tuple(
        s.species_id
        for s in handoff.species
        if s.initial_amount is None and s.initial_concentration is None
    )
    if not missing:
        return None
    return DiagnosticFinding(
        finding_id="missing-initial-conditions",
        category=DiagnosticCategory.MODEL_STRUCTURE,
        severity=DiagnosticSeverity.WARNING,
        summary=f"{len(missing)} of {len(handoff.species)} species have no declared initial value.",
        explanation=(
            "Neither SpeciesSpecification.initial_amount nor .initial_concentration is set for "
            "these species in the Agent 2 handoff -- SBML/Antimony defaults an unset species to "
            "0. This is a genuine, disclosed upstream scope gap (no increment in this "
            "pipeline currently assigns a species initial condition), not something Agent 3 "
            "invents a value for. Its direct consequence -- if every reactant of every reaction "
            "starts at 0, essentially all mass-action/Michaelis-Menten rate laws evaluate to 0 "
            "and the whole system never leaves its initial state -- is reported separately as "
            "its own finding when it is actually observed in a simulated trajectory."
        ),
        related_species_ids=missing,
    )


def trivial_trajectory_finding(sim: SimulationResult) -> DiagnosticFinding | None:
    """Flags a baseline simulation in which every species' trajectory is constant across the
    entire simulated horizon -- numerically valid (no solver error, no NaN/Inf), but
    biologically uninformative: the system never moves from its initial state at all."""
    if sim.species_trajectories is None:
        return None
    unmoved = []
    for species_id, values in sim.species_trajectories.items():
        arr = np.asarray(values, dtype=float)
        if np.isfinite(arr).all() and (arr.max() - arr.min()) < _TRIVIAL_TRAJECTORY_RANGE_TOLERANCE:
            unmoved.append(species_id)
    if len(unmoved) != len(sim.species_trajectories):
        return None
    return DiagnosticFinding(
        finding_id="trivial-trajectory",
        category=DiagnosticCategory.BIOLOGICALLY_QUESTIONABLE,
        severity=DiagnosticSeverity.WARNING,
        summary=(
            f"All {len(unmoved)} simulated species remain at a constant value for the entire "
            f"{sim.request.start_time}-{sim.request.end_time} time horizon."
        ),
        explanation=(
            "Numerically valid (no integration error, no NaN/Inf, no divergence) but "
            "biologically uninformative: the simulated system never leaves its own initial "
            "state. On the current real sce00061 model this traces directly to the "
            "missing-initial-conditions finding above (every species starts at 0, so every "
            "reactant-dependent rate law evaluates to exactly 0)."
        ),
        related_species_ids=tuple(unmoved),
    )


def solver_failure_finding(sim: SimulationResult) -> DiagnosticFinding | None:
    if sim.solver_message is None:
        return None
    from app.agent3.types import SimulationStatus  # local import: avoid a module-level cycle

    if sim.status is SimulationStatus.SIMULATION_FAILED:
        severity = DiagnosticSeverity.CRITICAL
    elif sim.status is SimulationStatus.NUMERICAL_INSTABILITY:
        severity = DiagnosticSeverity.ERROR
    else:
        return None
    return DiagnosticFinding(
        finding_id="solver-message",
        category=DiagnosticCategory.NUMERICAL_SOLVER,
        severity=severity,
        summary=sim.solver_message,
        explanation=(
            "Reported verbatim from the simulation engine (libRoadRunner/CVODE) -- Agent 3 "
            "never re-interprets, retries with different tolerances, or alters the model to "
            "avoid this message; if the model fails, this finding is the trace of why."
        ),
    )


def negative_concentration_findings(
    sim: SimulationResult, handoff: Agent2Handoff
) -> tuple[DiagnosticFinding, ...]:
    """One finding per species that ever goes negative during the simulated horizon.

    Every species in this contract is a chemical concentration -- SBML/biochemical semantics
    both require nonnegativity always; this check is never skipped for any species (Agent 2's
    own handoff carries no per-species "negative is allowed" flag, and none is invented here)."""
    if sim.species_trajectories is None:
        return ()
    species_by_id = _species_lookup(handoff)
    findings = []
    for species_id, values in sim.species_trajectories.items():
        arr = np.asarray(values, dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size and finite.min() < 0:
            species = species_by_id.get(species_id)
            findings.append(
                DiagnosticFinding(
                    finding_id=f"negative-concentration:{species_id}",
                    category=DiagnosticCategory.BIOLOGICALLY_QUESTIONABLE,
                    severity=DiagnosticSeverity.ERROR,
                    summary=(
                        f"Species {species_id!r} reaches a negative concentration "
                        f"({finite.min():g})."
                    ),
                    explanation=(
                        "A concentration can never be physically negative. This traces to the "
                        "reaction(s)/kinetic law(s) that produce or consume this species -- see "
                        "related_reaction_ids -- and never to Agent 3 itself, which does not "
                        "alter any rate law or parameter."
                    ),
                    related_species_ids=(species_id,),
                    related_reaction_ids=tuple(
                        r.reaction_id
                        for r in handoff.reactions
                        if any(p.species_id == species_id for p in r.participants)
                    ),
                    provenance_refs=species.provenance_refs
                    if hasattr(species, "provenance_refs")
                    else (),
                )
            )
    return tuple(findings)


def divergent_trajectory_findings(sim: SimulationResult) -> tuple[DiagnosticFinding, ...]:
    """One finding per species whose trajectory exceeds the divergence magnitude threshold --
    complements the aggregate ``SimulationStatus.NUMERICAL_INSTABILITY`` verdict by naming
    exactly which species runs away, rather than leaving a downstream consumer to re-derive it."""
    if sim.species_trajectories is None:
        return ()
    findings = []
    for species_id, values in sim.species_trajectories.items():
        arr = np.asarray(values, dtype=float)
        finite = arr[np.isfinite(arr)]
        if finite.size and np.abs(finite).max() > DIVERGENCE_MAGNITUDE_THRESHOLD:
            findings.append(
                DiagnosticFinding(
                    finding_id=f"divergent-trajectory:{species_id}",
                    category=DiagnosticCategory.NUMERICAL_SOLVER,
                    severity=DiagnosticSeverity.CRITICAL,
                    summary=(
                        f"Species {species_id!r} exceeds the divergence threshold "
                        f"({DIVERGENCE_MAGNITUDE_THRESHOLD:g}): "
                        f"max |value| = {np.abs(finite).max():g}."
                    ),
                    explanation=(
                        "Runaway/unbounded growth detected in this species' own trajectory."
                    ),
                    related_species_ids=(species_id,),
                )
            )
    return tuple(findings)


def nan_inf_findings(sim: SimulationResult) -> tuple[DiagnosticFinding, ...]:
    """One finding per species whose trajectory contains a NaN or Inf value."""
    if sim.species_trajectories is None:
        return ()
    findings = []
    for species_id, values in sim.species_trajectories.items():
        arr = np.asarray(values, dtype=float)
        has_nan = bool(np.isnan(arr).any())
        has_inf = bool(np.isinf(arr).any())
        if has_nan or has_inf:
            kind = (
                "NaN"
                if has_nan and not has_inf
                else ("Inf" if has_inf and not has_nan else "NaN and Inf")
            )
            findings.append(
                DiagnosticFinding(
                    finding_id=f"nan-inf:{species_id}",
                    category=DiagnosticCategory.NUMERICAL_SOLVER,
                    severity=DiagnosticSeverity.CRITICAL,
                    summary=f"Species {species_id!r} produced {kind} during simulation.",
                    explanation="A non-finite value appeared in this species' own trajectory.",
                    related_species_ids=(species_id,),
                )
            )
    return tuple(findings)


def build_stoichiometry_matrix(
    handoff: Agent2Handoff,
) -> tuple[np.ndarray, list[str], list[str]]:
    """The (species x reaction) stoichiometry matrix implied purely by
    ``HandoffReaction.participants`` -- reactants negative, products positive, modifiers 0 --
    plus the species/reaction id ordering it uses. Pure structural fact, no kinetics involved."""
    species_ids = [s.species_id for s in handoff.species]
    reaction_ids = [r.reaction_id for r in handoff.reactions]
    species_index = {sid: i for i, sid in enumerate(species_ids)}
    matrix = np.zeros((len(species_ids), len(reaction_ids)), dtype=float)
    for col, reaction in enumerate(handoff.reactions):
        for participant in reaction.participants:
            row = species_index.get(participant.species_id)
            if row is None:
                continue
            signed = float(participant.stoichiometry)
            if participant.role == "REACTANT":
                matrix[row, col] -= signed
            elif participant.role == "PRODUCT":
                matrix[row, col] += signed
    return matrix, species_ids, reaction_ids


def conservation_findings(
    handoff: Agent2Handoff, sim: SimulationResult
) -> tuple[DiagnosticFinding, ...]:
    """Mass-balance/conservation checks inferable purely from reaction stoichiometry: every
    vector in the left null space of the stoichiometry matrix names a linear combination of
    species concentrations that *must* stay constant over time regardless of kinetics (a
    structural conservation law) -- this function checks whether it actually did, in the
    simulated trajectory, within numerical tolerance. A violation here is a genuine solver/
    model-construction inconsistency, never a biological judgment.
    """
    if sim.species_trajectories is None or not sim.time_points:
        return ()
    matrix, species_ids, _reaction_ids = build_stoichiometry_matrix(handoff)
    if matrix.size == 0:
        return ()
    try:
        from scipy.linalg import null_space

        conserved_vectors = null_space(matrix.T)
    except Exception:  # pragma: no cover - defensive; scipy is a declared dependency
        return ()
    if conserved_vectors.size == 0:
        return (
            DiagnosticFinding(
                finding_id="conservation-none-found",
                category=DiagnosticCategory.CONSERVATION,
                severity=DiagnosticSeverity.INFO,
                summary="No linear conservation law is implied by this model's own stoichiometry.",
                explanation=(
                    "The left null space of the (species x reaction) stoichiometry matrix is "
                    "trivial -- every species can, in principle, be independently produced or "
                    "consumed without violating any structural conservation law. This is a "
                    "statement about the network's own topology, not a failure."
                ),
            ),
        )

    trajectory_matrix = np.array(
        [sim.species_trajectories[sid] for sid in species_ids if sid in sim.species_trajectories]
    )
    present_ids = [sid for sid in species_ids if sid in sim.species_trajectories]
    if trajectory_matrix.shape[0] != len(species_ids):
        # Some species missing from the trajectory (should not happen for a SUCCESS baseline run,
        # but this check is defensive and never assumes the shapes line up).
        index_map = [species_ids.index(sid) for sid in present_ids]
        conserved_vectors = conserved_vectors[index_map, :]

    n_laws = conserved_vectors.shape[1]
    violations = 0
    max_drift = 0.0
    for law_index in range(n_laws):
        coefficients = conserved_vectors[:, law_index]
        conserved_quantity = coefficients @ trajectory_matrix
        drift = float(conserved_quantity.max() - conserved_quantity.min())
        max_drift = max(max_drift, drift)
        if drift > _CONSERVATION_DRIFT_TOLERANCE:
            violations += 1

    if violations == 0:
        return (
            DiagnosticFinding(
                finding_id="conservation-held",
                category=DiagnosticCategory.CONSERVATION,
                severity=DiagnosticSeverity.INFO,
                summary=(
                    f"All {n_laws} stoichiometry-implied conservation law(s) held within "
                    f"tolerance (max drift {max_drift:.3g})."
                ),
                explanation=(
                    "Computed from the left null space of the reaction stoichiometry matrix; "
                    "each law's own conserved linear combination of species concentrations "
                    "stayed constant across the simulated trajectory within numerical tolerance."
                ),
            ),
        )
    return (
        DiagnosticFinding(
            finding_id="conservation-violated",
            category=DiagnosticCategory.CONSERVATION,
            severity=DiagnosticSeverity.ERROR,
            summary=(
                f"{violations} of {n_laws} stoichiometry-implied conservation law(s) drifted "
                f"by more than {_CONSERVATION_DRIFT_TOLERANCE:g} (max drift {max_drift:.3g})."
            ),
            explanation=(
                "A quantity the model's own reaction stoichiometry structurally guarantees "
                "should be exactly conserved was not, within this run's own numerical "
                "tolerance -- a genuine solver-precision or model-construction inconsistency, "
                "never a biological judgment Agent 3 is making."
            ),
        ),
    )


def steady_state_finding(steady_state: SteadyStateResult) -> DiagnosticFinding | None:
    """Discloses a failed/non-attempted steady-state search -- ``None`` when it converged
    (nothing to report beyond the ``SteadyStateResult`` itself)."""
    if not steady_state.attempted or steady_state.converged:
        return None
    return DiagnosticFinding(
        finding_id="steady-state-not-found",
        category=DiagnosticCategory.NUMERICAL_SOLVER,
        severity=DiagnosticSeverity.WARNING,
        summary="Steady-state search did not converge.",
        explanation=steady_state.message or "No further detail was reported by the solver.",
    )


def run_all_diagnostics(
    handoff: Agent2Handoff,
    sim: SimulationResult | None,
    steady_state: SteadyStateResult | None = None,
) -> tuple[DiagnosticFinding, ...]:
    """The full Version 1 diagnostic sweep, in a fixed, deterministic order."""
    findings: list[DiagnosticFinding] = []
    heuristic_finding = heuristic_provenance_finding(handoff)
    if heuristic_finding is not None:
        findings.append(heuristic_finding)
    missing_ic = missing_initial_condition_finding(handoff)
    if missing_ic is not None:
        findings.append(missing_ic)

    if sim is not None:
        solver_finding = solver_failure_finding(sim)
        if solver_finding is not None:
            findings.append(solver_finding)
        findings.extend(nan_inf_findings(sim))
        findings.extend(divergent_trajectory_findings(sim))
        findings.extend(negative_concentration_findings(sim, handoff))
        trivial = trivial_trajectory_finding(sim)
        if trivial is not None:
            findings.append(trivial)
        findings.extend(conservation_findings(handoff, sim))

    if steady_state is not None:
        ss_finding = steady_state_finding(steady_state)
        if ss_finding is not None:
            findings.append(ss_finding)

    return tuple(findings)


__all__ = [
    "build_stoichiometry_matrix",
    "conservation_findings",
    "divergent_trajectory_findings",
    "heuristic_and_placeholder_parameters",
    "heuristic_provenance_finding",
    "missing_initial_condition_finding",
    "nan_inf_findings",
    "negative_concentration_findings",
    "parameter_provenance_refs",
    "run_all_diagnostics",
    "solver_failure_finding",
    "steady_state_finding",
    "trivial_trajectory_finding",
]
