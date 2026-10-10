"""Approval state machine.

    DRAFT ──propose──▶ PROPOSED ──approve──▶ APPROVED ──start_rollout──▶ ROLLING_OUT ──complete──▶ COMPLETE
                          │                                   ▲
                          └──request_changes──▶ DRAFT         └── (re-runs allowed, tokens stay frozen)

Tokens may only change in DRAFT. ``approve`` is the single place where the lock
is taken, and ``rollout_allowed`` is what the child-page engine asks before it
builds anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import StateError, TokenLockedError
from .tokens import lock_tokens, verify_locked

DRAFT, PROPOSED, APPROVED, ROLLING_OUT, COMPLETE = "draft", "proposed", "approved", "rolling_out", "complete"

_TRANSITIONS: dict[str, dict[str, str]] = {
    DRAFT: {"propose": PROPOSED},
    PROPOSED: {"approve": APPROVED, "request_changes": DRAFT},
    APPROVED: {"start_rollout": ROLLING_OUT},
    ROLLING_OUT: {"start_rollout": ROLLING_OUT, "complete": COMPLETE},
    COMPLETE: {},
}


@dataclass
class ApprovalMachine:
    client_id: str
    state: str = DRAFT
    blueprint: dict[str, Any] | None = None
    locked_tokens: dict[str, Any] | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    # -- transitions -------------------------------------------------------
    def _move(self, event: str, actor: str) -> None:
        target = _TRANSITIONS[self.state].get(event)
        if target is None:
            raise StateError(f"cannot {event!r} while the design is {self.state!r}")
        self.history.append(
            {"from": self.state, "event": event, "to": target, "by": actor, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        )
        self.state = target

    def set_blueprint(self, blueprint: dict[str, Any]) -> None:
        """Replace the draft blueprint. Refused as soon as the design is proposed."""
        if self.state != DRAFT:
            raise TokenLockedError(f"tokens can only be edited in {DRAFT!r}, not {self.state!r}")
        if blueprint.get("client_id") != self.client_id:
            raise StateError("blueprint client_id does not match this project")
        self.blueprint = blueprint

    def propose(self, actor: str) -> None:
        if self.blueprint is None:
            raise StateError("nothing to propose: no blueprint has been set")
        self._move("propose", actor)

    def request_changes(self, actor: str) -> None:
        self._move("request_changes", actor)

    def approve(self, approver: str) -> dict[str, Any]:
        """Client sign-off: lock the tokens and return approved_design_tokens."""
        if self.state != PROPOSED:
            raise StateError(f"cannot 'approve' while the design is {self.state!r}")
        assert self.blueprint is not None
        locked = lock_tokens(self.blueprint, approved_by=approver)
        self._move("approve", approver)
        self.locked_tokens = locked
        return locked

    def start_rollout(self, actor: str) -> None:
        self._move("start_rollout", actor)

    def complete(self, actor: str) -> None:
        self._move("complete", actor)

    # -- queries -----------------------------------------------------------
    def rollout_allowed(self) -> bool:
        return self.state in (APPROVED, ROLLING_OUT) and self.locked_tokens is not None

    def tokens_for_rollout(self) -> dict[str, Any]:
        """Verified tokens, or an exception explaining why rollout may not run."""
        if not self.rollout_allowed():
            raise StateError(f"rollout is not allowed while the design is {self.state!r}")
        assert self.locked_tokens is not None
        verify_locked(self.locked_tokens)
        return self.locked_tokens

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "state": self.state,
            "blueprint": self.blueprint,
            "locked_tokens": self.locked_tokens,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalMachine":
        machine = cls(client_id=data["client_id"], state=data["state"], blueprint=data.get("blueprint"),
                      locked_tokens=data.get("locked_tokens"), history=list(data.get("history", [])))
        if machine.state in (APPROVED, ROLLING_OUT, COMPLETE):
            verify_locked(machine.locked_tokens or {})
        return machine

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ApprovalMachine":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
