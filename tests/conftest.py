import copy
import json
from pathlib import Path

import pytest

from elementor_layout_compiler import lock_tokens

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def blueprint():
    return load("brand_blueprint.json")


@pytest.fixture
def manifest():
    return load("homepage_manifest.json")


@pytest.fixture
def locked(blueprint):
    return lock_tokens(blueprint, approved_by="Dr. L. Cruz (client)")


@pytest.fixture
def clone():
    return copy.deepcopy
