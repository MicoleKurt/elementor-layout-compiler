import json

import pytest

from elementor_layout_compiler import (
    LayoutCompiler, SchemaError, TokenTamperError, TreeValidationError, assert_valid, build_payload, compile_manifest,
    contrast_ratio, validate_tree,
)
from elementor_layout_compiler.validator import ALLOWED_WIDGETS


def walk(tree):
    for node in tree:
        yield node
        yield from walk(node["elements"])


def test_example_manifest_compiles_to_a_valid_tree(manifest, locked):
    tree = compile_manifest(manifest, locked)
    assert validate_tree(tree) == []
    assert len(tree) == len(manifest["sections"])
    assert all(node["elType"] == "container" and node["isInner"] is False for node in tree)


def test_output_is_deterministic(manifest, locked):
    first = json.dumps(compile_manifest(manifest, locked), sort_keys=True)
    second = json.dumps(compile_manifest(manifest, locked), sort_keys=True)
    assert first == second


def test_ids_are_unique_eight_hex_characters(manifest, locked):
    ids = [n["id"] for n in walk(compile_manifest(manifest, locked))]
    assert len(ids) == len(set(ids))
    assert all(len(i) == 8 and set(i) <= set("0123456789abcdef") for i in ids)


def test_ids_change_with_the_page_slug_not_with_content(manifest, locked, clone):
    other = clone(manifest)
    other["sections"][0]["heading"] = "A different headline"
    a = [n["id"] for n in walk(compile_manifest(manifest, locked))]
    b = [n["id"] for n in walk(compile_manifest(other, locked))]
    assert a == b  # content edits do not reshuffle ids, so diffs stay small


def test_nesting_flags_follow_elementor_conventions(manifest, locked):
    for outer in compile_manifest(manifest, locked):
        for node in walk([outer]):
            if node["elType"] == "widget":
                assert node["isInner"] is False and node["elements"] == []
            elif node is not outer:
                assert node["isInner"] is True


def test_only_allowlisted_widgets_are_emitted(manifest, locked):
    kinds = {n["widgetType"] for n in walk(compile_manifest(manifest, locked)) if n["elType"] == "widget"}
    assert kinds <= ALLOWED_WIDGETS and {"heading", "text-editor", "button", "image", "accordion"} <= kinds


def test_styling_comes_from_the_locked_tokens(manifest, locked):
    tree = compile_manifest(manifest, locked)
    colors = locked["tokens"]["colors"]
    used = {n["settings"].get("background_color") for n in walk(tree) if n["elType"] == "container"}
    assert colors["primary"] in used and colors["surface"] in used
    buttons = [n for n in walk(tree) if n.get("widgetType") == "button"]
    assert all(b["settings"]["border_radius"]["top"] == str(locked["tokens"]["radii"]["button"]) for b in buttons)
    fonts = {n["settings"].get("typography_font_family") for n in walk(tree) if n["elType"] == "widget" and "typography_font_family" in n["settings"]}
    assert fonts == {locked["tokens"]["typography"]["heading_font"], locked["tokens"]["typography"]["body_font"]}


def test_text_stays_readable_on_every_coloured_background(manifest, locked):
    tree = compile_manifest(manifest, locked)

    def check(node, background):
        if node["elType"] == "container":
            background = node["settings"].get("background_color", background)
            for child in node["elements"]:
                check(child, background)
        elif node["widgetType"] == "heading":
            assert contrast_ratio(background, node["settings"]["title_color"]) >= 4.5, node["id"]

    for section in tree:
        check(section, locked["tokens"]["colors"]["background"])


def test_model_text_is_escaped_not_trusted_as_markup(manifest, locked, clone):
    hostile = clone(manifest)
    hostile["sections"][0]["heading"] = 'Hello <script>alert(1)</script>'
    tree = compile_manifest(hostile, locked)
    title = next(n for n in walk(tree) if n.get("widgetType") == "heading")["settings"]["title"]
    assert "<script" not in title and "&lt;script&gt;" in title


def test_manifest_with_extra_keys_is_rejected(manifest, locked, clone):
    bad = clone(manifest)
    bad["sections"][0]["raw_elementor"] = {"id": "deadbeef"}
    with pytest.raises(SchemaError):
        compile_manifest(bad, locked)


def test_javascript_urls_are_rejected_by_the_schema(manifest, locked, clone):
    bad = clone(manifest)
    bad["sections"][0]["cta"]["url"] = "javascript:alert(1)"
    with pytest.raises(SchemaError):
        compile_manifest(bad, locked)


def test_compiler_refuses_tampered_tokens(manifest, locked):
    locked["tokens"]["colors"]["primary"] = "#123456"
    with pytest.raises(TokenTamperError):
        LayoutCompiler(locked, "home")


def test_slug_mismatch_is_an_error(manifest, locked):
    with pytest.raises(ValueError):
        LayoutCompiler(locked, "about").compile(manifest)


def test_faq_rows_carry_seven_hex_repeater_ids(manifest, locked):
    accordion = next(n for n in walk(compile_manifest(manifest, locked)) if n.get("widgetType") == "accordion")
    ids = [row["_id"] for row in accordion["settings"]["tabs"]]
    assert len(ids) == len(set(ids)) == 2 and all(len(i) == 7 for i in ids)


# ----------------------------------------------------------------------- validator rules


@pytest.fixture
def tree(manifest, locked):
    return compile_manifest(manifest, locked)


def test_validator_flags_duplicate_ids(tree):
    tree[1]["id"] = tree[0]["id"]
    assert any("duplicate id" in e for e in validate_tree(tree))


def test_validator_flags_bad_id_format(tree):
    tree[0]["id"] = "NOT-HEX!"
    assert any("8 lowercase hex" in e for e in validate_tree(tree))


def test_validator_flags_unknown_widgets(tree):
    next(n for n in walk(tree) if n["elType"] == "widget")["widgetType"] = "shell-exec"
    assert any("allowlist" in e for e in validate_tree(tree))


def test_validator_flags_widget_children_and_wrong_inner_flags(tree):
    widget = next(n for n in walk(tree) if n["elType"] == "widget")
    widget["elements"] = [{"id": "aaaaaaaa", "elType": "widget", "widgetType": "heading", "isInner": False, "settings": [], "elements": []}]
    tree[0]["isInner"] = True
    errors = validate_tree(tree)
    assert any("cannot contain elements" in e for e in errors) and any("isInner must be false" in e for e in errors)


def test_validator_flags_scripts_hidden_in_settings(tree):
    widget = next(n for n in walk(tree) if n.get("widgetType") == "text-editor")
    widget["settings"]["editor"] = "<p>ok</p><script>steal()</script>"
    assert any("forbidden content" in e for e in validate_tree(tree))


def test_validator_flags_dangerous_link_schemes(tree):
    button = next(n for n in walk(tree) if n.get("widgetType") == "button")
    button["settings"]["link"]["url"] = "ftp://example.com"
    assert any("scheme not allowed" in e for e in validate_tree(tree))


def test_validator_accepts_empty_settings_array_as_documented(tree):
    widget = next(n for n in walk(tree) if n["elType"] == "widget")
    widget["settings"] = []
    assert validate_tree(tree) == []


def test_validator_rejects_garbage_roots():
    assert validate_tree([]) and validate_tree({}) and validate_tree("[]")
    with pytest.raises(TreeValidationError):
        assert_valid([{"id": "x"}])


def test_payload_has_stable_idempotency_key_and_native_array(manifest, locked, tree):
    a = build_payload(title="Home", slug="home", tree=tree, tenant_id="brightside-dental", locked_tokens=locked)
    b = build_payload(title="Home", slug="home", tree=tree, tenant_id="brightside-dental", locked_tokens=locked)
    assert a["idempotency_key"] == b["idempotency_key"]
    assert isinstance(a["elementor_data"], list) and a["status"] == "draft"
    c = build_payload(title="Home", slug="home", tree=tree, tenant_id="another-client", locked_tokens=locked)
    assert c["idempotency_key"] != a["idempotency_key"]
    assert a["design_tokens_sha256"] == locked["tokens_sha256"]


def test_whole_number_sizes_are_ints_so_they_survive_php_json_round_trips(tree):
    """PHP's json_encode writes 48.0 as 48; an int in the payload keeps both sides byte-identical."""
    floats = [
        (node["id"], key)
        for node in walk(tree)
        for key, value in node["settings"].items()
        if isinstance(value, dict) and isinstance(value.get("size"), float) and value["size"].is_integer()
    ]
    assert floats == []
