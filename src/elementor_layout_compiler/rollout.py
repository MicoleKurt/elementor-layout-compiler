"""Child-page rollout.

After the homepage is approved and the tokens are locked, the interior pages
(About, Services, Case Studies, Contact) are built from *wireframes*: a fixed
structure whose text and images are filled from the client's own memory.

A wireframe field is either a literal or a ``slot:<name>`` reference. Slots are
resolved by a ``ContentProvider`` that is scoped to one client (in production,
the tenant-memory-service). Two rules keep the output honest:

* a section whose required slot has no content is **omitted and reported**, never invented;
* every page is compiled against the verified locked tokens, so styling cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .compiler import compile_manifest
from .payload import build_payload
from .schema import validate_manifest
from .state import ApprovalMachine

ContentProvider = Callable[[str], Optional[Any]]
SLOT_PREFIX = "slot:"


@dataclass
class PageResult:
    slug: str
    payload: dict[str, Any]
    missing_slots: list[str] = field(default_factory=list)
    omitted_sections: list[int] = field(default_factory=list)


@dataclass
class RolloutResult:
    pages: list[PageResult]

    @property
    def needs_review(self) -> bool:
        return any(page.missing_slots for page in self.pages)


class _Missing(Exception):
    def __init__(self, slot: str):
        super().__init__(slot)
        self.slot = slot


def _resolve(value: Any, provider: ContentProvider) -> Any:
    """Resolve ``slot:`` references anywhere inside a wireframe field."""
    if isinstance(value, str) and value.startswith(SLOT_PREFIX):
        slot = value[len(SLOT_PREFIX):]
        content = provider(slot)
        if content in (None, "", [], {}):
            raise _Missing(slot)
        return content
    if isinstance(value, dict):
        return {key: _resolve(item, provider) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, provider) for item in value]
    return value


def build_manifest(wireframe: dict[str, Any], provider: ContentProvider) -> tuple[dict[str, Any], list[str], list[int]]:
    """Fill a wireframe from ``provider``. Returns (manifest, missing slots, omitted section indexes)."""
    sections: list[dict[str, Any]] = []
    missing: list[str] = []
    omitted: list[int] = []
    for index, section in enumerate(wireframe["sections"]):
        try:
            sections.append(_resolve(section, provider))
        except _Missing as exc:
            missing.append(exc.slot)
            omitted.append(index)
    manifest = {"schema_version": "1.0", "page": wireframe["page"], "sections": sections}
    return manifest, missing, omitted


def rollout_child_pages(machine: ApprovalMachine, wireframes: list[dict[str, Any]], provider: ContentProvider) -> RolloutResult:
    """Build every interior page, or raise if the design has not been approved."""
    locked = machine.tokens_for_rollout()  # raises StateError unless approved, verifies the lock
    results: list[PageResult] = []
    for wireframe in wireframes:
        manifest, missing, omitted = build_manifest(wireframe, provider)
        if not manifest["sections"]:
            results.append(PageResult(slug=wireframe["page"]["slug"], payload={}, missing_slots=missing, omitted_sections=omitted))
            continue
        validate_manifest(manifest)
        tree = compile_manifest(manifest, locked)
        payload = build_payload(title=manifest["page"]["title"], slug=manifest["page"]["slug"], tree=tree,
                                tenant_id=machine.client_id, locked_tokens=locked)
        results.append(PageResult(slug=manifest["page"]["slug"], payload=payload, missing_slots=missing, omitted_sections=omitted))
    return RolloutResult(pages=results)
