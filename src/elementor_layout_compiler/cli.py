"""Command line interface: ``elc lock | compile | validate``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import compile_manifest
from .errors import CompilerError
from .payload import build_payload
from .schema import validate_blueprint, validate_manifest
from .tokens import lock_tokens, verify_locked
from .validator import validate_tree


def _read(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | None, value) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elc", description="Compile layout manifests into Elementor container JSON.")
    sub = parser.add_subparsers(dest="command", required=True)

    lock = sub.add_parser("lock", help="validate a brand blueprint and write approved_design_tokens.json")
    lock.add_argument("blueprint")
    lock.add_argument("--approved-by", required=True)
    lock.add_argument("-o", "--output")

    comp = sub.add_parser("compile", help="compile a layout manifest against locked tokens")
    comp.add_argument("manifest")
    comp.add_argument("--tokens", required=True, help="approved_design_tokens.json")
    comp.add_argument("--tenant", required=True, help="client_id for the payload")
    comp.add_argument("--tree-only", action="store_true", help="print just the _elementor_data array")
    comp.add_argument("-o", "--output")

    val = sub.add_parser("validate", help="validate a manifest, a blueprint or an _elementor_data tree")
    val.add_argument("kind", choices=["manifest", "blueprint", "tree"])
    val.add_argument("path")

    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            _write(args.output, lock_tokens(_read(args.blueprint), approved_by=args.approved_by))
        elif args.command == "compile":
            manifest, locked = _read(args.manifest), _read(args.tokens)
            verify_locked(locked)
            tree = compile_manifest(manifest, locked)
            if args.tree_only:
                _write(args.output, tree)
            else:
                _write(args.output, build_payload(title=manifest["page"]["title"], slug=manifest["page"]["slug"], tree=tree,
                                                  tenant_id=args.tenant, locked_tokens=locked))
        else:
            document = _read(args.path)
            if args.kind == "manifest":
                validate_manifest(document)
            elif args.kind == "blueprint":
                validate_blueprint(document)
            else:
                problems = validate_tree(document)
                if problems:
                    for line in problems:
                        print(f"error: {line}", file=sys.stderr)
                    return 1
            print("ok")
    except CompilerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for line in getattr(exc, "errors", []):
            print(f"  - {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
