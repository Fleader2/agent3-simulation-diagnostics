"""Loading/compiling an Antimony model into a runnable simulation engine.

Uses the ``antimony`` (Antimony -> SBML translation) and ``libroadrunner`` (SBML -> ODE
simulation, imported as ``roadrunner``) packages directly -- the smallest credible,
purpose-built pair for this job, rather than the much heavier ``tellurium`` convenience
meta-package (which additionally pulls in ``jupyter``, ``matplotlib``, ``pandas``, ``plotly``
and more -- none of which this package needs). See ``docs/03_diagnostic_semantics.md`` and the
completion report for the full dependency-choice rationale.

A compilation failure (malformed Antimony text, or -- defensively -- a downstream SBML/
RoadRunner rejection of otherwise-valid-looking Antimony) is **never** raised as a Python
exception here: it is exactly the kind of first-class, expected outcome this package exists to
report (``SimulationStatus.MODEL_LOAD_FAILED``), returned as data in ``ModelLoadResult``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import antimony
import roadrunner

#: ``antimony``'s own module-level parser state is a single, process-global, non-reentrant
#: resource (confirmed by direct inspection of its own C-extension API: ``loadAntimonyString``/
#: ``getSBMLString``/``clearPreviousLoads`` all operate on one shared, unparameterized global
#: state, never an instance or handle this caller could hold separately). A lock serializes every
#: load through this module so two concurrent callers (e.g. a test suite run with parallel
#: workers) can never interleave one one call's ``loadAntimonyString`` with another's
#: ``getSBMLString`` and silently read the wrong model.
_ANTIMONY_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ModelLoadResult:
    """The outcome of one attempt to compile Antimony text into a runnable model."""

    succeeded: bool
    roadrunner_instance: roadrunner.RoadRunner | None
    sbml_text: str | None
    message: str | None
    antimony_version: str
    roadrunner_version: str


def _antimony_version() -> str:
    # The ``antimony`` python package does not expose a version accessor on every release
    # (confirmed by direct inspection this session: no ``getAntimonyVersion``-style function
    # exists on the installed build) -- the installed *distribution* version (from
    # ``importlib.metadata``, the actual installed-package version, never guessed) is reported
    # instead, which is what matters for reproducibility anyway.
    try:
        from importlib.metadata import version

        return version("antimony")
    except Exception:  # pragma: no cover - defensive only, never expected in a real install
        return "unknown"


def load_antimony_model(antimony_text: str) -> ModelLoadResult:
    """Compile ``antimony_text`` (Antimony syntax) into a loaded ``roadrunner.RoadRunner``
    instance, or report exactly why compilation failed.

    Never mutates ``antimony_text`` itself, never retries with a "repaired" variant, and never
    falls back to a partially-loaded model -- either the full text compiles to valid SBML and
    RoadRunner accepts it, or this reports failure with Antimony's/RoadRunner's own error text
    preserved verbatim.
    """
    with _ANTIMONY_LOCK:
        antimony.clearPreviousLoads()
        antimony.freeAll()
        load_code = antimony.loadAntimonyString(antimony_text)
        if load_code < 0:
            message = antimony.getLastError()
            antimony.clearPreviousLoads()
            return ModelLoadResult(
                succeeded=False,
                roadrunner_instance=None,
                sbml_text=None,
                message=f"Antimony compilation failed: {message}",
                antimony_version=_antimony_version(),
                roadrunner_version=roadrunner.__version__,
            )

        main_module = antimony.getMainModuleName()
        try:
            sbml_text = antimony.getSBMLString(main_module)
        except Exception as exc:  # pragma: no cover - defensive; not expected for valid antimony
            antimony.clearPreviousLoads()
            return ModelLoadResult(
                succeeded=False,
                roadrunner_instance=None,
                sbml_text=None,
                message=f"Antimony->SBML conversion failed for module {main_module!r}: {exc}",
                antimony_version=_antimony_version(),
                roadrunner_version=roadrunner.__version__,
            )
        antimony.clearPreviousLoads()

    if not sbml_text:
        return ModelLoadResult(
            succeeded=False,
            roadrunner_instance=None,
            sbml_text=None,
            message="Antimony compiled with no error, but produced an empty SBML document.",
            antimony_version=_antimony_version(),
            roadrunner_version=roadrunner.__version__,
        )

    try:
        rr = roadrunner.RoadRunner(sbml_text)
    except Exception as exc:
        return ModelLoadResult(
            succeeded=False,
            roadrunner_instance=None,
            sbml_text=sbml_text,
            message=f"RoadRunner rejected the compiled SBML: {exc}",
            antimony_version=_antimony_version(),
            roadrunner_version=roadrunner.__version__,
        )

    return ModelLoadResult(
        succeeded=True,
        roadrunner_instance=rr,
        sbml_text=sbml_text,
        message=None,
        antimony_version=_antimony_version(),
        roadrunner_version=roadrunner.__version__,
    )


__all__ = ["ModelLoadResult", "load_antimony_model"]
