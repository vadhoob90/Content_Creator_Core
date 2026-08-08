import json

import pytest

from content_creator.voice_build.models import VoiceBuildError
from content_creator.voice_evolution import (
    VoiceEvolution,
    VoiceEvolutionAction,
    VoiceEvolutionProposal,
)
from content_creator.voice_models import VoicePattern


def _pattern(pattern_id):
    return VoicePattern(
        id=pattern_id,
        name=pattern_id,
        description="Evidence-backed guidance",
        status="active",
        confidence=0.9,
        supporting_source_ids=["source-1"],
    )


def _proposal(action, *, target="base", replacement="replacement"):
    return VoiceEvolutionProposal(
        action=action,
        target_id=target,
        replacement=_pattern(replacement) if replacement else None,
        evidence_source_ids=["source-1"],
        rationale="Author-requested evidence-backed change",
    )


def _apply(proposal, *, changed=None):
    evolution = object.__new__(VoiceEvolution)
    patterns = {"base": _pattern("base")}
    order = ["base"]
    groups = {action.value: [] for action in VoiceEvolutionAction}
    evolution._apply_proposal(
        proposal,
        patterns,
        order,
        groups,
        changed or set(),
        {"source-1"},
    )
    return patterns, order, groups


@pytest.mark.parametrize(
    ("proposal", "message", "changed"),
    [
        (_proposal("retain", target="missing", replacement=None), "existing target", None),
        (_proposal("add", target="base"), "one new replacement", None),
        (_proposal("add", target=None, replacement=None), "one new replacement", None),
        (_proposal("add", target=None, replacement="base"), "one new replacement", None),
        (_proposal("remove", target="missing", replacement=None), "active target", None),
        (_proposal("remove"), "cannot include a replacement", None),
        (_proposal("modify", replacement=None), "requires a replacement", None),
        (_proposal("modify", replacement="new-id"), "retain the target id", None),
        (_proposal("supersede", replacement="base"), "requires one new id", None),
        (_proposal("modify", replacement="base"), "Duplicate evolution proposal", {"base"}),
    ],
)
def test_voice_evolution_rejects_ambiguous_or_conflicting_semantic_changes(
    proposal, message, changed
):
    with pytest.raises(VoiceBuildError, match=message):
        _apply(proposal, changed=changed)


@pytest.mark.parametrize(
    ("proposal", "expected_ids", "expected_group"),
    [
        (_proposal("retain", replacement=None), ["base"], "retain"),
        (_proposal("add", target=None, replacement="new"), ["base", "new"], "add"),
        (_proposal("modify", replacement="base"), ["base"], "modify"),
        (_proposal("supersede", replacement="new"), ["new"], "supersede"),
        (_proposal("remove", replacement=None), [], "remove"),
    ],
)
def test_voice_evolution_applies_each_explicit_semantic_action(
    proposal, expected_ids, expected_group
):
    patterns, order, groups = _apply(proposal)

    assert [item for item in order if item in patterns] == expected_ids
    if expected_group == "retain":
        assert groups[expected_group] == []
    else:
        assert len(groups[expected_group]) == 1


@pytest.mark.parametrize("evidence", [[], ["unapproved-source"]])
def test_voice_evolution_rejects_missing_or_unapproved_evidence(evidence):
    proposal = _proposal("add", target=None, replacement="new")
    proposal.evidence_source_ids = evidence

    with pytest.raises(VoiceBuildError, match="Unsupported evolution evidence"):
        _apply(proposal)


def test_voice_evolution_rejects_conflicting_modes_and_missing_change_sets(tmp_path):
    change_set = tmp_path / "changes.json"
    change_set.write_text(json.dumps({"changes": []}), encoding="utf-8")

    with pytest.raises(VoiceBuildError, match="cannot be combined"):
        VoiceEvolution(tmp_path, "voice", full_regenerate=True, change_set_path=change_set)
    with pytest.raises(VoiceBuildError, match="requires an active baseline"):
        VoiceEvolution(tmp_path, "voice", change_set_path=change_set)
    with pytest.raises(VoiceBuildError, match="does not exist"):
        VoiceEvolution(tmp_path, "voice", change_set_path=tmp_path / "missing.json")


def test_voice_evolution_requires_an_active_baseline_for_baseline_operations(tmp_path):
    evolution = VoiceEvolution(tmp_path, "voice")

    with pytest.raises(VoiceBuildError, match="Active voice baseline is unavailable"):
        evolution._required_baseline()
    with pytest.raises(VoiceBuildError, match="Active voice baseline is unavailable"):
        evolution._required_baseline_dir()
