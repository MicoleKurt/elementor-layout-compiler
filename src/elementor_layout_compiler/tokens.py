"""Design-token locking.

Once the client signs off on the homepage demo, the styling decisions must stop
moving: every interior page has to look like the page the client approved. This
module freezes the approved tokens into ``approved_design_tokens.json`` together
with a SHA-256 of the tokens themselves. Anything that later tries to change them,
or that edits the file on disk, is rejected.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .errors import TokenLockedError, TokenTamperError
from .schema import validate_blueprint

TOKEN_KEYS = ("colors", "typography", "spacing", "radii", "buttons")
LOCK_SCHEMA_VERSION = "1.0"


def canonical_json(value: Any) -> str:
    """Stable serialisation: sorted keys, no whitespace, UTF-8 characters kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def extract_tokens(blueprint: dict[str, Any]) -> dict[str, Any]:
    """The styling part of a blueprint, deep-copied."""
    return {key: copy.deepcopy(blueprint[key]) for key in TOKEN_KEYS}


def lock_tokens(blueprint: dict[str, Any], *, approved_by: str, approved_at: datetime | None = None) -> dict[str, Any]:
    """Validate ``blueprint`` and return the ``approved_design_tokens`` document."""
    validate_blueprint(blueprint)
    if not approved_by.strip():
        raise ValueError("approved_by is required: a lock without a named approver is not an approval")
    tokens = extract_tokens(blueprint)
    stamp = (approved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schema_version": LOCK_SCHEMA_VERSION,
        "client_id": blueprint["client_id"],
        "locked": True,
        "approved_by": approved_by.strip(),
        "approved_at": stamp.isoformat(timespec="seconds"),
        "tokens_sha256": sha256_hex(tokens),
        "tokens": tokens,
    }


def verify_locked(doc: dict[str, Any]) -> dict[str, Any]:
    """Return the tokens if the lock is intact, otherwise raise.

    Called by every compile and rollout, so a hand-edited file cannot leak
    unapproved styling into a page.
    """
    if not doc.get("locked"):
        raise TokenLockedError("design tokens are not locked: the client has not approved them yet")
    tokens = doc.get("tokens")
    if not isinstance(tokens, dict) or sha256_hex(tokens) != doc.get("tokens_sha256"):
        raise TokenTamperError("approved_design_tokens.json does not match its recorded hash")
    return tokens


def assert_unchanged(doc: dict[str, Any], blueprint: dict[str, Any]) -> None:
    """Reject any attempt to push a different blueprint after approval."""
    verify_locked(doc)
    if sha256_hex(extract_tokens(blueprint)) != doc["tokens_sha256"]:
        raise TokenLockedError("tokens are locked: the new blueprint differs from the approved design")
