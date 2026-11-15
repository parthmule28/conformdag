"""Shared declarations for the ConformDAG CLI adapters."""

from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console

console = Console()
RUNTIME_OPTION = typer.Option(
    None,
    "--runtime",
    help="Enable the maintained published runtime profile (3.3.0).",
)
RUNTIME_IMAGE_OPTION = typer.Option(
    None,
    "--runtime-image",
    help="Enable an explicitly pinned custom runtime image.",
)
NO_EVIDENCE_OPTION = typer.Option(
    False,
    "--no-evidence",
    help="Remove source evidence from rendered findings.",
)
PREVIEW_MODEL_CONTEXT_OPTION = typer.Option(
    False,
    "--preview-model-context",
    help="Print the redacted semantic context without calling a provider.",
)
SEMANTIC_OPTION = typer.Option(
    None,
    "--semantic/--no-semantic",
    help="Enable or disable BYOK semantic evaluation (defaults to project configuration).",
)
SEMANTIC_BASE_URL_OPTION = typer.Option(
    None,
    "--semantic-base-url",
    help="Override the configured OpenAI-compatible API base URL.",
)
SEMANTIC_MODEL_OPTION = typer.Option(
    None,
    "--semantic-model",
    help="Override the exact configured semantic model ID.",
)
SEMANTIC_STRUCTURED_OUTPUT_OPTION = typer.Option(
    None,
    "--semantic-structured-output/--no-semantic-structured-output",
    help="Enable or disable provider-native strict JSON Schema output.",
)
BASELINE_OPTION = typer.Option(
    None,
    "--baseline",
    help="Path to a baseline scan report JSON used by quality-gate rules.",
)
BENCHMARK_PATH_ARGUMENT = typer.Argument(Path("benchmarks/synthetic"))
BENCHMARK_POLICY_PACK_OPTION = typer.Option(Path("policies/pack.yaml"), "--policy-pack")
BENCHMARK_OUTPUT_OPTION = typer.Option(None, "--output", help="Write the JSON report to this path.")
BENCHMARK_MARKDOWN_OPTION = typer.Option(
    None, "--technical-report", help="Write the human-readable Markdown report to this path."
)
AGENT_REPORTS_ARGUMENT = typer.Argument(help="Canonical report JSON paths to aggregate.")
AGENT_PACK_ID_OPTION = typer.Option("org-pack", "--pack-id", help="Pack label for the proposal.")
AGENT_FORMAT_OPTION = typer.Option("markdown", "--format", help="Proposal format: markdown or json.")
PACK_NAME_OPTION = typer.Option(None, "--name", help="Local cache name for the pulled pack.")
PACK_CACHE_ROOT_OPTION = typer.Option(None, "--cache-root", help="Cache root; defaults to .conformdag/packs.")


def _fail(error: Exception) -> NoReturn:
    typer.echo(f"error: {error}", err=True)
    raise typer.Exit(code=2)


fail = _fail
