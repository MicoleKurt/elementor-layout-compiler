# elementor-layout-compiler

Turn a **validated layout manifest** and **locked design tokens** into **Elementor container JSON** (`_elementor_data`), deterministically, so AI-generated pages open cleanly in the Elementor editor.

> **Author:** Micole Kurt T. Gonda ([@MicoleKurt](https://github.com/MicoleKurt)) · MIT licensed
> Part of a three-repo toolkit for programmatic WordPress/Elementor production:
> **elementor-layout-compiler** (this repo, the JSON generator) ·
> [wp-staging-bridge](https://github.com/MicoleKurt/wp-staging-bridge) (the authenticated REST plugin that writes the page) ·
> [tenant-memory-service](https://github.com/MicoleKurt/tenant-memory-service) (the tenant-isolated vector memory that supplies client content).

## The idea

A language model should not write Elementor JSON. It emits a **small, closed manifest** (hero, feature grid, text and image, call to action, testimonials, FAQ). This package:

1. validates the manifest and the brand blueprint against JSON Schema (`additionalProperties: false` everywhere);
2. **locks** the approved design tokens into `approved_design_tokens.json` with a SHA-256, behind an approval state machine;
3. compiles the manifest into `_elementor_data` with **deterministic ids**, tokens applied, text escaped, and WCAG contrast checked;
4. validates the tree (ids, nesting, `isInner`, widget allowlist, no scripts, safe URLs) and builds the request payload for the bridge plugin;
5. rolls out **child pages** (About, Services, Case Studies, Contact) from wireframes, filling `slot:` fields from the client's own memory and **never inventing** missing content.

Details and the reasoning: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Key names and provenance: [docs/ELEMENTOR_KEYS.md](docs/ELEMENTOR_KEYS.md).

## Quick start

```bash
pip install -e .[dev]
pytest                                   # 45 tests

# 1. client signs off: lock the tokens
elc lock examples/brand_blueprint.json --approved-by "Dr. L. Cruz (client)" -o approved_design_tokens.json

# 2. compile a manifest into the payload for wp-staging-bridge
elc compile examples/homepage_manifest.json --tokens approved_design_tokens.json --tenant brightside-dental -o page.json

# 3. validate any document
elc validate manifest examples/homepage_manifest.json
elc validate tree tree.json
```

```python
from elementor_layout_compiler import ApprovalMachine, compile_manifest, rollout_child_pages

machine = ApprovalMachine(client_id="brightside-dental")
machine.set_blueprint(blueprint)
machine.propose("designer")
locked = machine.approve("Dr. L. Cruz")                 # tokens are now frozen
tree = compile_manifest(homepage_manifest, locked)       # list of containers, ready for _elementor_data

result = rollout_child_pages(machine, wireframes, provider=client_memory.lookup)
for page in result.pages:
    print(page.slug, page.missing_slots)                 # empty list means nothing was left out
```

## Guarantees (each one has a test)

* Same input, same output, byte for byte; content edits do not reshuffle ids.
* Tokens cannot change after approval, and a hand-edited token file fails its hash check.
* Rollout is refused before approval.
* Unknown keys, unknown widgets, script content and non-http(s) URLs are rejected, never passed through.
* Heading text keeps at least 4.5:1 contrast on every coloured background it is placed on.
* Missing client content is reported and omitted, not guessed.

## Status and limits

Structural keys follow Elementor's developer documentation. Style keys follow Elementor's export conventions and have **not yet been verified against a live Elementor install**; they are listed in `docs/ELEMENTOR_KEYS.md` and pinned by tests. The sample client in `examples/` is fictional.

## License

MIT, © 2026 Micole Kurt T. Gonda
