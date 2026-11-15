"""Deterministic benchmark command adapter."""

import json
from pathlib import Path

import typer

from conformdag.benchmark import (
    BenchmarkValidationError,
    render_benchmark_report,
    run_deterministic_benchmark,
)
from conformdag.policy import resolve_policy_pack_path

from .common import (
    BENCHMARK_MARKDOWN_OPTION,
    BENCHMARK_OUTPUT_OPTION,
    BENCHMARK_PATH_ARGUMENT,
    BENCHMARK_POLICY_PACK_OPTION,
)
from .common import fail as _fail


def benchmark(
    path: Path = BENCHMARK_PATH_ARGUMENT,
    policy_pack: Path = BENCHMARK_POLICY_PACK_OPTION,
    output: Path | None = BENCHMARK_OUTPUT_OPTION,
    technical_report: Path | None = BENCHMARK_MARKDOWN_OPTION,
) -> None:
    """Verify and run the local deterministic benchmark without provider or network access."""
    root = Path.cwd().resolve()
    manifest_path = path / "manifest.yaml" if path.is_dir() else path
    selected_pack = resolve_policy_pack_path(policy_pack)
    try:
        result = run_deterministic_benchmark(manifest_path, selected_pack, root)
    except (BenchmarkValidationError, ValueError, OSError) as exc:
        _fail(exc)
    payload = json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(payload, encoding="utf-8")
    else:
        typer.echo(payload, nl=False)
    if technical_report is not None:
        technical_report.write_text(render_benchmark_report(result), encoding="utf-8")
    if not result.passed:
        raise typer.Exit(code=1)
