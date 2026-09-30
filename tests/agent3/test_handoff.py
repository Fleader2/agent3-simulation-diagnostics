"""Tests for ``app.agent3.handoff``: contract parsing/validation."""

from __future__ import annotations

import copy

import pytest

from app.agent3.errors import HandoffContractError
from app.agent3.handoff import handoff_contract_version_mismatch, parse_agent2_handoff
from tests.agent3.fixtures import minimal_handoff_dict


def test_valid_handoff_parses():
    handoff = parse_agent2_handoff(minimal_handoff_dict())
    assert handoff.model_id == "test-model-1"
    assert len(handoff.species) == 1
    assert len(handoff.parameters) == 1
    assert handoff_contract_version_mismatch(handoff) is None


def test_missing_required_field_raises_contract_error():
    data = minimal_handoff_dict()
    del data["antimony_text"]
    with pytest.raises(HandoffContractError):
        parse_agent2_handoff(data)


def test_not_a_dict_raises_contract_error():
    with pytest.raises(HandoffContractError):
        parse_agent2_handoff(["not", "a", "dict"])


def test_wrong_type_field_raises_contract_error():
    data = minimal_handoff_dict()
    data["unresolved_reaction_ids"] = "should-be-a-list"
    with pytest.raises(HandoffContractError):
        parse_agent2_handoff(data)


def test_version_mismatch_is_disclosed_not_raised():
    data = minimal_handoff_dict(contract_version="some-other-version")
    handoff = parse_agent2_handoff(data)  # never raises for a version mismatch
    note = handoff_contract_version_mismatch(handoff)
    assert note is not None
    assert "some-other-version" in note


def test_parsing_never_mutates_the_input_dict():
    data = minimal_handoff_dict()
    original = copy.deepcopy(data)
    parse_agent2_handoff(data)
    assert data == original
