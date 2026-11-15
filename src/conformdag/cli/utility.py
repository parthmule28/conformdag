"""Workspace initialization, diagnostics, and version commands."""

import os
import shutil
from pathlib import Path

import typer

from conformdag import __version__
from conformdag.config import load_project_config
from conformdag.models import PolicyPack, ProjectConfig
from conformdag.policy import (
    PolicyValidationError,
    resolve_configured_policy_pack,
    select_policy_pack,
    validate_policy_provenance,
)

from .common import console


def init(path: Path = Path("."), force: bool = False) -> None:
    """Create a safe starter configuration and policy-pack scaffold."""
    root = path.resolve()
    files = {
        root / "conformdag.yaml": (
            'config_version: "1"\n'
            "scan:\n"
            "  policy_pack: policies/pack.yaml\n"
            "  include:\n"
            '    - "dags/**/*.py"\n'
            "  exclude:\n"
            '    - "**/.venv/**"\n'
            '    - "**/.git/**"\n'
            '    - "**/vendor/**"\n'
            '    - "**/generated/**"\n'
            "semantic:\n"
            "  enabled: false\n"
            "runtime:\n"
            "  enabled: false\n"
        ),
        root / "conformdag-workspace.yaml": (
            "# ConformDAG platform workspace (optional - only the platform reads this).\n"
            'schema_version: "1"\n'
            "# repositories:\n"
            "#   - name: core-dags\n"
            "#     path: ./dags-repo\n"
            "#     policy_pack: ./policies/pack.yaml\n"
            "# policy_packs:\n"
            "#   - name: org\n"
            "#     path: ./policies/pack.yaml\n"
        ),
        root / "policies" / "pack.yaml": ('schema_version: "1"\nid: default\nversion: 0.1.0\npolicies: []\n'),
        root / "standards" / "dag-authoring.md": "# DAG Authoring Standards\n",
        root / ".conformdag" / "suppressions.yaml": "suppressions: []\n",
    }
    for target, content in files.items():
        if target.exists() and not force:
            typer.echo(f"skipped {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        typer.echo(f"created {target}")


def doctor() -> None:
    """Diagnose the local workspace: config, pack, registry, provenance, runtime."""
    root = Path.cwd()
    rows: list[tuple[str, str, str]] = []

    config: ProjectConfig | None = None
    config_path = root / "conformdag.yaml"
    try:
        if not config_path.is_file():
            raise OSError(f"config file not found: {config_path}")
        config = load_project_config(config_path)
        rows.append(("config", "PASS", "conformdag.yaml parses"))
    except (OSError, ValueError) as exc:
        rows.append(("config", "FAIL", str(exc)))

    selected_pack = (
        resolve_configured_policy_pack(config.scan.policy_pack, scan_root=root, from_cli=False)
        if config is not None
        else None
    )
    pack: PolicyPack | None = None
    try:
        pack = select_policy_pack(selected_pack, root)
        rows.append(("pack", "PASS", f"{pack.id} {pack.version} ({len(pack.policies)} policies)"))
    except PolicyValidationError as exc:
        rows.append(("pack", "FAIL", str(exc)))

    if pack is not None and config is not None:
        try:
            pack_path = resolve_configured_policy_pack(config.scan.policy_pack, scan_root=root, from_cli=False)
            provenance = validate_policy_provenance(pack, pack_path=pack_path, repository_root=root)
            rows.append(
                (
                    "provenance",
                    "PASS" if not provenance else "FAIL",
                    "; ".join(provenance) if provenance else "all policy provenance resolves",
                )
            )
        except (OSError, ValueError) as exc:
            rows.append(("provenance", "FAIL", str(exc)))

    docker = shutil.which("docker")
    rows.append(
        (
            "docker",
            "PASS" if docker else "WARN",
            "docker binary found" if docker else "docker not found; runtime checks unavailable",
        )
    )

    dsn = os.environ.get("CONFORMDAG_PLATFORM_DSN")
    if not dsn:
        rows.append(("platform-dsn", "WARN", "CONFORMDAG_PLATFORM_DSN is not set; platform reachability not checked"))
    else:
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.engine import Engine
            from sqlalchemy.exc import SQLAlchemyError
        except ImportError as exc:  # pragma: no cover - exercised without the platform extra
            rows.append(("platform-dsn", "FAIL", f"platform extra is not installed: {exc}"))
        else:
            engine: Engine | None = None
            try:
                engine = create_engine(dsn)
                with engine.connect():
                    pass
            except (ImportError, OSError, SQLAlchemyError, ValueError) as exc:
                rows.append(("platform-dsn", "FAIL", f"cannot reach configured DSN: {exc}"))
            else:
                rows.append(("platform-dsn", "PASS", "configured platform DSN is reachable"))
            finally:
                if engine is not None:
                    engine.dispose()

    for label, status, detail in rows:
        style = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[status]
        console.print(f"[{style}]{status}[/] {label}: {detail}")
    if any(status == "FAIL" for _, status, _ in rows):
        raise typer.Exit(code=1)


def version() -> None:
    """Show the installed ConformDAG version."""
    typer.echo(__version__)
