"""Exception hierarchy. Every failure is explicit: nothing is silently coerced."""


class CompilerError(Exception):
    """Base class for all errors raised by this package."""


class SchemaError(CompilerError):
    """A manifest or blueprint does not satisfy its JSON Schema."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class TreeValidationError(CompilerError):
    """A compiled Elementor tree breaks a structural rule."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]) + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""))
        self.errors = errors


class TokenLockedError(CompilerError):
    """Someone tried to change design tokens after client approval."""


class TokenTamperError(CompilerError):
    """The locked tokens no longer match their recorded hash."""


class StateError(CompilerError):
    """An approval-state transition is not allowed."""
