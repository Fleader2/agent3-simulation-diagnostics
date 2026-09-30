"""Tests for ``app.agent3.loader``: valid/invalid Antimony compilation."""

from __future__ import annotations

from app.agent3.loader import load_antimony_model
from tests.agent3.fixtures import INVALID_ANTIMONY, VALID_DECAY_ANTIMONY


def test_valid_antimony_loads_successfully():
    result = load_antimony_model(VALID_DECAY_ANTIMONY)
    assert result.succeeded
    assert result.roadrunner_instance is not None
    assert result.sbml_text is not None
    assert result.message is None


def test_invalid_antimony_reports_failure_not_an_exception():
    result = load_antimony_model(INVALID_ANTIMONY)
    assert not result.succeeded
    assert result.roadrunner_instance is None
    assert result.message is not None
    assert "Antimony compilation failed" in result.message


def test_two_consecutive_loads_do_not_interfere():
    """The module-level antimony parser lock/state-clearing must not leak one load's model
    into the next -- confirmed by loading an invalid model, then a valid one, then checking
    the valid one is unaffected."""
    bad = load_antimony_model(INVALID_ANTIMONY)
    assert not bad.succeeded
    good = load_antimony_model(VALID_DECAY_ANTIMONY)
    assert good.succeeded
    assert good.roadrunner_instance is not None
    assert "s_S1" in good.roadrunner_instance.model.getFloatingSpeciesIds()
