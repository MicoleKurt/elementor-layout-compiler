"""Build the request body for the wp-staging-bridge REST endpoint.

The tree is sent as a real JSON array, not as a pre-encoded string. The plugin
is the one place that encodes and slashes it for ``update_post_meta``, so the
double-encoding mistake that corrupts ``_elementor_data`` cannot happen here.
"""

from __future__ import annotations

from typing import Any

from .tokens import canonical_json, sha256_hex, verify_locked
from .validator import assert_valid

# Meta that makes WordPress treat the post as an Elementor-managed page.
ELEMENTOR_PAGE_META = {
    "_elementor_edit_mode": "builder",
    "_elementor_template_type": "wp-page",
}


def build_payload(*, title: str, slug: str, tree: list[dict[str, Any]], tenant_id: str,
                  locked_tokens: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON body for ``POST /wp-json/staging-bridge/v1/pages``."""
    verify_locked(locked_tokens)
    assert_valid(tree)
    # The key is derived from content, so retrying the same request never creates a second page.
    idempotency_key = sha256_hex({"tenant": tenant_id, "slug": slug, "tree": canonical_json(tree)})
    return {
        "title": title,
        "slug": slug,
        "status": "draft",
        "tenant_id": tenant_id,
        "design_tokens_sha256": locked_tokens["tokens_sha256"],
        "idempotency_key": idempotency_key,
        "elementor_data": tree,
    }
