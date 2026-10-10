"""Deterministic element ids.

Elementor expects every element id to be unique inside a page and to look like
an 8-character lowercase hex string. Random ids work, but they make every
recompile a full diff. Deriving the id from the page slug and the element's
position in the tree means the same manifest always produces the same JSON,
so a re-run is idempotent and a change shows up as a small, reviewable diff.
"""

from __future__ import annotations

import hashlib
import re

ELEMENT_ID_RE = re.compile(r"^[0-9a-f]{8}$")
REPEATER_ID_RE = re.compile(r"^[0-9a-f]{7}$")


def element_id(page_slug: str, path: str) -> str:
    """8-hex id for the element at ``path`` (for example ``0.1.2``) on a page."""
    return hashlib.sha1(f"el:{page_slug}:{path}".encode("utf-8")).hexdigest()[:8]


def repeater_id(page_slug: str, path: str) -> str:
    """7-hex ``_id`` used by repeater rows (accordion tabs and similar)."""
    return hashlib.sha1(f"rep:{page_slug}:{path}".encode("utf-8")).hexdigest()[:7]
