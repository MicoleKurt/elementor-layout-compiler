"""JSON Schema loading and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from .errors import SchemaError


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    text = resources.files("elementor_layout_compiler").joinpath("schemas", f"{name}.schema.json").read_text("utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_document(name: str, document: Any) -> None:
    """Raise :class:`SchemaError` listing every violation, or return None."""
    errors = sorted(_validator(name).iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
        raise SchemaError(f"{name} failed validation ({len(lines)} problem(s))", lines)


def validate_blueprint(document: Any) -> None:
    validate_document("brand_blueprint", document)


def validate_manifest(document: Any) -> None:
    validate_document("layout_manifest", document)
