"""Application scan input and runtime execution errors."""


class ScanInputError(ValueError):
    """Raised when an application scan input or preflight is invalid."""


class RuntimeExecutionError(RuntimeError):
    """Raised by a runtime adapter when runtime execution cannot complete."""
