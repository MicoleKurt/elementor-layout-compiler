"""Structural validation of an ``_elementor_data`` tree.

These are the rules that keep a generated page editable. The same rules are
re-implemented in PHP in the companion plugin (wp-staging-bridge) so a payload
is checked on both sides of the wire.

Structure (Elementor developer docs, "Data Structure"):
    every element has id, elType, isInner, settings, elements;
    a widget also has widgetType; settings is an object, or an empty list when
    the element has no settings.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import TreeValidationError
from .ids import ELEMENT_ID_RE, REPEATER_ID_RE

ALLOWED_WIDGETS = frozenset({"heading", "text-editor", "button", "image", "accordion", "divider", "spacer"})
MAX_DEPTH = 8
MAX_NODES = 2000
MAX_BYTES = 1_500_000

_FORBIDDEN_SUBSTRINGS = ("<script", "javascript:", "onerror=", "onload=", "<iframe", "data:text/html")
_URL_OK = re.compile(r"^(https?://|mailto:|tel:|#|/)", re.IGNORECASE)


def _walk_strings(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        for bad in _FORBIDDEN_SUBSTRINGS:
            if bad in lowered:
                errors.append(f"{path}: contains forbidden content {bad!r}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str) and item and not _URL_OK.match(item):
                errors.append(f"{path}.url: scheme not allowed")
            _walk_strings(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_strings(item, f"{path}[{index}]", errors)


def validate_tree(tree: Any) -> list[str]:
    """Return a list of problems; an empty list means the tree is safe to write."""
    errors: list[str] = []
    if not isinstance(tree, list) or not tree:
        return ["root: _elementor_data must be a non-empty array of top-level elements"]

    seen: set[str] = set()
    count = 0

    def visit(node: Any, path: str, depth: int, parent_type: str | None) -> None:
        nonlocal count
        count += 1
        if depth > MAX_DEPTH:
            errors.append(f"{path}: nesting deeper than {MAX_DEPTH}")
            return
        if not isinstance(node, dict):
            errors.append(f"{path}: element must be an object")
            return

        for key in ("id", "elType", "isInner", "settings", "elements"):
            if key not in node:
                errors.append(f"{path}: missing key {key!r}")
        node_id, el_type = node.get("id"), node.get("elType")

        if not isinstance(node_id, str) or not ELEMENT_ID_RE.match(node_id):
            errors.append(f"{path}: id must be 8 lowercase hex characters, got {node_id!r}")
        elif node_id in seen:
            errors.append(f"{path}: duplicate id {node_id!r}")
        else:
            seen.add(node_id)

        if el_type not in ("container", "widget"):
            errors.append(f"{path}: elType must be 'container' or 'widget', got {el_type!r}")
            return

        # Nested containers are inner; widgets and top-level containers are not.
        expected_inner = el_type == "container" and parent_type is not None
        if node.get("isInner") is not expected_inner:
            errors.append(f"{path}: isInner must be {str(expected_inner).lower()}")

        settings = node.get("settings")
        if not (isinstance(settings, dict) or settings == []):
            errors.append(f"{path}: settings must be an object or an empty array")
        elif isinstance(settings, dict):
            _walk_strings(settings, f"{path}.settings", errors)
            for rows in settings.values():
                if isinstance(rows, list) and rows and all(isinstance(r, dict) and "_id" in r for r in rows):
                    for row in rows:
                        if not REPEATER_ID_RE.match(str(row["_id"])):
                            errors.append(f"{path}: repeater _id must be 7 lowercase hex characters")

        children = node.get("elements")
        if not isinstance(children, list):
            errors.append(f"{path}: elements must be an array")
            return

        if el_type == "widget":
            widget = node.get("widgetType")
            if widget not in ALLOWED_WIDGETS:
                errors.append(f"{path}: widgetType {widget!r} is not in the allowlist")
            if children:
                errors.append(f"{path}: a widget cannot contain elements")
        else:
            if "widgetType" in node:
                errors.append(f"{path}: a container must not carry widgetType")
            for index, child in enumerate(children):
                visit(child, f"{path}.elements[{index}]", depth + 1, "container")

    for index, node in enumerate(tree):
        visit(node, f"[{index}]", 1, None)

    if count > MAX_NODES:
        errors.append(f"root: {count} elements exceeds the limit of {MAX_NODES}")
    try:
        size = len(json.dumps(tree, ensure_ascii=False).encode("utf-8"))
        if size > MAX_BYTES:
            errors.append(f"root: tree is {size} bytes, limit is {MAX_BYTES}")
    except (TypeError, ValueError) as exc:
        errors.append(f"root: tree is not JSON serialisable ({exc})")
    return errors


def assert_valid(tree: Any) -> None:
    problems = validate_tree(tree)
    if problems:
        raise TreeValidationError(problems)
