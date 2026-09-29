"""Application-level scan workflows and their transport-neutral contracts."""

from conformdag.application.configuration import (
    EffectiveScanConfiguration,
    ScanOverrides,
    coerce_platform_airflow_profile,
    resolve_effective_configuration,
)
from conformdag.application.errors import RuntimeExecutionError, ScanInputError
from conformdag.application.outcomes import ExecutionOutcome, classify_report
from conformdag.application.scan import (
    BaselineInput,
    RuntimeExecutor,
    ScanExecutionResult,
    ScanOptions,
    execute_scan,
)

__all__ = [
    "BaselineInput",
    "EffectiveScanConfiguration",
    "ExecutionOutcome",
    "RuntimeExecutionError",
    "RuntimeExecutor",
    "ScanExecutionResult",
    "ScanInputError",
    "ScanOptions",
    "ScanOverrides",
    "coerce_platform_airflow_profile",
    "classify_report",
    "execute_scan",
    "resolve_effective_configuration",
]
