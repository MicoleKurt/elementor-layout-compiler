"""elementor-layout-compiler: turn a validated layout manifest into Elementor container JSON."""

from .compiler import LayoutCompiler, compile_manifest, contrast_ratio
from .errors import CompilerError, SchemaError, StateError, TokenLockedError, TokenTamperError, TreeValidationError
from .payload import build_payload
from .rollout import RolloutResult, build_manifest, rollout_child_pages
from .schema import validate_blueprint, validate_manifest
from .state import ApprovalMachine
from .tokens import assert_unchanged, lock_tokens, sha256_hex, verify_locked
from .validator import ALLOWED_WIDGETS, assert_valid, validate_tree

__version__ = "0.1.0"
__author__ = "Micole Kurt T. Gonda"

__all__ = [
    "ALLOWED_WIDGETS", "ApprovalMachine", "CompilerError", "LayoutCompiler", "RolloutResult", "SchemaError", "StateError",
    "TokenLockedError", "TokenTamperError", "TreeValidationError", "assert_unchanged", "assert_valid", "build_manifest",
    "build_payload", "compile_manifest", "contrast_ratio", "lock_tokens", "rollout_child_pages", "sha256_hex",
    "validate_blueprint", "validate_manifest", "validate_tree", "verify_locked",
]
