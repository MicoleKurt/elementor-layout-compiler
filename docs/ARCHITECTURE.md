# Architecture: mapping model output into `_elementor_data` without breaking the editor

## The rule

**A language model never writes Elementor JSON.** It fills in a small, closed *layout manifest*
(`schemas/layout_manifest.schema.json`). A deterministic compiler turns that manifest into
`_elementor_data`, using design tokens that were locked when the client approved the demo.

Letting a model emit raw `_elementor_data` fails in three ways: ids collide or have the wrong
format, nesting flags are wrong so the editor cannot open the page, and any string can smuggle
markup. Each is avoided by construction here.

```
discovery inputs ─▶ vision/LLM ─▶ brand_blueprint.json ─▶ schema check ─▶ approval ─▶ approved_design_tokens.json
                                                                                              │ (locked, SHA-256)
  layout_manifest.json ─▶ schema check ─▶ LayoutCompiler(tokens) ─▶ validate_tree ─▶ payload ─▶ wp-staging-bridge
        ▲                                                                                       (re-validates, writes draft)
  model output (constrained)
```

## Why the editor stays usable

| Risk | Control |
|---|---|
| Duplicate or malformed ids | Ids are derived from `sha1(page_slug + position)`, 8 lowercase hex characters, and checked for uniqueness. Repeater rows get 7-hex `_id`s. |
| Wrong nesting | Only containers hold children; widgets never do. Top-level containers and widgets carry `isInner: false`, nested containers `true`. Depth, node count and size are capped. |
| Unknown widgets | A closed allowlist (`heading`, `text-editor`, `button`, `image`, `accordion`, `divider`, `spacer`). Anything else is a validation error, not a silent pass-through. |
| `settings` shape | An object, or an empty array (Elementor writes `[]` for an element with no settings). Both are accepted; nothing else is. |
| Markup injection | Model text is HTML-escaped into paragraphs. The validator rejects `<script`, `javascript:`, inline event handlers and non-http(s)/mailto/tel URLs anywhere in `settings`. |
| Double-encoded meta | The tree travels as a JSON *array*. The plugin encodes it once and applies `wp_slash` before `update_post_meta`; sending a pre-encoded string is rejected. |
| Half-written pages | The plugin validates before it inserts, writes a **draft**, and rolls the post back if any meta write fails. |
| Retries | The payload carries a content-derived idempotency key; the plugin returns the existing page instead of creating a second one. |
| Style drift | Every compile calls `verify_locked`; a hand-edited token file fails its SHA-256 check. |

## Token locking and the approval state machine

`DRAFT → PROPOSED → APPROVED → ROLLING_OUT → COMPLETE`. Tokens can only be edited in `DRAFT`.
`approve()` is the single place the lock is taken and it requires a named approver. The locked
document stores `tokens_sha256`, the hash of the canonical (sorted-key) tokens, so ordering and
whitespace cannot change it. `ApprovalMachine.load` re-verifies the hash when state is restored.

## Child-page rollout

A wireframe is a fixed structure whose fields are literals or `slot:<name>` references. A
`ContentProvider` resolves slots for **one client only** (in production, a call to the
tenant-memory-service for that `client_id`). If a section's slot has no content the section is
*omitted and reported*; the engine never fills a gap with invented copy. The result flags
`needs_review` so a person decides what to do with the missing slots.

## What is verified and what is not

* Structure (`id`, `elType`, `isInner`, `settings`, `elements`, `widgetType`) follows Elementor's developer documentation, "Data Structure".
* Style keys (`flex_direction`, `flex_gap`, `typography_*`, and so on) follow Elementor's export conventions and are listed in [ELEMENTOR_KEYS.md](ELEMENTOR_KEYS.md). They are **not yet checked against a live Elementor install**; the unit tests pin them, so a mismatch found on a real site is a one-line change plus a test.
