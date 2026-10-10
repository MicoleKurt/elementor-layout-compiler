import json
from pathlib import Path

import pytest

from elementor_layout_compiler import ApprovalMachine, StateError, rollout_child_pages
from elementor_layout_compiler.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def wireframe():
    return json.loads((EXAMPLES / "about_wireframe.json").read_text(encoding="utf-8"))


@pytest.fixture
def store():
    return json.loads((EXAMPLES / "content_store.json").read_text(encoding="utf-8"))


@pytest.fixture
def approved(blueprint):
    machine = ApprovalMachine(client_id=blueprint["client_id"])
    machine.set_blueprint(blueprint)
    machine.propose("designer")
    machine.approve("client")
    return machine


def test_rollout_builds_pages_from_client_memory(approved, wireframe, store):
    result = rollout_child_pages(approved, [wireframe], store.get)
    page = result.pages[0]
    assert page.slug == "about" and not page.missing_slots and not result.needs_review
    assert page.payload["tenant_id"] == "brightside-dental"
    assert page.payload["design_tokens_sha256"] == approved.locked_tokens["tokens_sha256"]
    titles = json.dumps(page.payload["elementor_data"])
    assert "Dr. Lina Cruz" in titles and "Dentistry that starts with listening" in titles


def test_rollout_never_invents_missing_content(approved, wireframe, store):
    del store["team.members"]
    result = rollout_child_pages(approved, [wireframe], store.get)
    page = result.pages[0]
    assert page.missing_slots == ["team.members"] and page.omitted_sections == [2]
    assert result.needs_review
    assert "The team" not in json.dumps(page.payload["elementor_data"])


def test_rollout_with_no_content_builds_nothing(approved, wireframe):
    result = rollout_child_pages(approved, [wireframe], lambda slot: None)
    assert result.pages[0].payload == {} or len(result.pages[0].payload["elementor_data"]) == 1


def test_rollout_is_blocked_until_the_client_approves(blueprint, wireframe, store):
    machine = ApprovalMachine(client_id=blueprint["client_id"])
    machine.set_blueprint(blueprint)
    machine.propose("designer")
    with pytest.raises(StateError):
        rollout_child_pages(machine, [wireframe], store.get)


def test_cli_lock_compile_and_validate(tmp_path, capsys):
    tokens = tmp_path / "approved_design_tokens.json"
    assert main(["lock", str(EXAMPLES / "brand_blueprint.json"), "--approved-by", "Client", "-o", str(tokens)]) == 0
    out = tmp_path / "page.json"
    assert main(["compile", str(EXAMPLES / "homepage_manifest.json"), "--tokens", str(tokens), "--tenant", "brightside-dental", "-o", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "draft" and payload["elementor_data"]
    assert main(["validate", "manifest", str(EXAMPLES / "homepage_manifest.json")]) == 0
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps(payload["elementor_data"]), encoding="utf-8")
    assert main(["validate", "tree", str(tree)]) == 0
    assert capsys.readouterr().out.count("ok") == 2


def test_cli_reports_a_tampered_lock(tmp_path, capsys):
    tokens = tmp_path / "t.json"
    main(["lock", str(EXAMPLES / "brand_blueprint.json"), "--approved-by", "Client", "-o", str(tokens)])
    data = json.loads(tokens.read_text(encoding="utf-8"))
    data["tokens"]["colors"]["primary"] = "#000000"
    tokens.write_text(json.dumps(data), encoding="utf-8")
    code = main(["compile", str(EXAMPLES / "homepage_manifest.json"), "--tokens", str(tokens), "--tenant", "x"])
    assert code == 1 and "does not match its recorded hash" in capsys.readouterr().err
