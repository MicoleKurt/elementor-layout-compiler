import json

import pytest

from elementor_layout_compiler import (
    ApprovalMachine, SchemaError, StateError, TokenLockedError, TokenTamperError, assert_unchanged, lock_tokens,
    verify_locked,
)
from elementor_layout_compiler.tokens import canonical_json


def test_lock_records_hash_and_approver(blueprint):
    doc = lock_tokens(blueprint, approved_by="  Dr. L. Cruz  ")
    assert doc["locked"] is True
    assert doc["approved_by"] == "Dr. L. Cruz"
    assert len(doc["tokens_sha256"]) == 64
    assert set(doc["tokens"]) == {"colors", "typography", "spacing", "radii", "buttons"}
    assert "brand_name" not in doc["tokens"]


def test_lock_requires_a_named_approver(blueprint):
    with pytest.raises(ValueError):
        lock_tokens(blueprint, approved_by="   ")


def test_invalid_blueprint_is_rejected_with_every_problem(blueprint):
    blueprint["colors"]["primary"] = "blue"
    blueprint["radii"]["button"] = 999
    with pytest.raises(SchemaError) as info:
        lock_tokens(blueprint, approved_by="x")
    assert len(info.value.errors) >= 2


def test_unknown_blueprint_keys_are_rejected(blueprint):
    blueprint["colors"]["neon"] = "#00FF00"
    with pytest.raises(SchemaError):
        lock_tokens(blueprint, approved_by="x")


def test_hash_is_stable_regardless_of_key_order(blueprint, clone):
    reordered = json.loads(json.dumps(blueprint, sort_keys=True))
    assert lock_tokens(blueprint, approved_by="a")["tokens_sha256"] == lock_tokens(reordered, approved_by="a")["tokens_sha256"]
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_edited_tokens_are_detected(locked):
    locked["tokens"]["colors"]["primary"] = "#FF0000"
    with pytest.raises(TokenTamperError):
        verify_locked(locked)


def test_unlocked_document_is_refused(locked):
    locked["locked"] = False
    with pytest.raises(TokenLockedError):
        verify_locked(locked)


def test_new_blueprint_after_approval_is_rejected(locked, blueprint, clone):
    changed = clone(blueprint)
    changed["colors"]["accent"] = "#FF00AA"
    with pytest.raises(TokenLockedError):
        assert_unchanged(locked, changed)
    assert_unchanged(locked, blueprint)  # the approved blueprint itself is fine


# ----------------------------------------------------------------------- state machine


def _machine(blueprint):
    machine = ApprovalMachine(client_id=blueprint["client_id"])
    machine.set_blueprint(blueprint)
    return machine


def test_happy_path_locks_on_approval(blueprint):
    m = _machine(blueprint)
    assert not m.rollout_allowed()
    m.propose("designer")
    locked = m.approve("client")
    assert m.state == "approved" and locked["locked"]
    assert m.rollout_allowed()
    m.start_rollout("engine")
    m.complete("engine")
    assert [h["to"] for h in m.history] == ["proposed", "approved", "rolling_out", "complete"]


def test_rollout_is_refused_before_approval(blueprint):
    m = _machine(blueprint)
    with pytest.raises(StateError):
        m.tokens_for_rollout()
    m.propose("designer")
    with pytest.raises(StateError):
        m.tokens_for_rollout()


def test_tokens_cannot_change_after_proposal(blueprint, clone):
    m = _machine(blueprint)
    m.propose("designer")
    with pytest.raises(TokenLockedError):
        m.set_blueprint(clone(blueprint))


def test_request_changes_reopens_the_draft(blueprint):
    m = _machine(blueprint)
    m.propose("designer")
    m.request_changes("client")
    assert m.state == "draft"
    m.set_blueprint(blueprint)  # editable again


def test_cannot_approve_a_draft_or_skip_states(blueprint):
    m = _machine(blueprint)
    with pytest.raises(StateError):
        m.approve("client")
    with pytest.raises(StateError):
        m.complete("engine")


def test_blueprint_for_another_client_is_rejected(blueprint, clone):
    other = clone(blueprint)
    other["client_id"] = "someone-else"
    m = ApprovalMachine(client_id=blueprint["client_id"])
    with pytest.raises(StateError):
        m.set_blueprint(other)


def test_state_round_trips_and_detects_tampering(blueprint, tmp_path):
    m = _machine(blueprint)
    m.propose("designer")
    m.approve("client")
    path = tmp_path / "state.json"
    m.save(path)
    restored = ApprovalMachine.load(path)
    assert restored.state == "approved" and restored.rollout_allowed()

    data = json.loads(path.read_text(encoding="utf-8"))
    data["locked_tokens"]["tokens"]["colors"]["primary"] = "#000000"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TokenTamperError):
        ApprovalMachine.load(path)
