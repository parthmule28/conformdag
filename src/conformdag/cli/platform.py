"""Platform command adapters with deferred optional imports."""

import typer

from .common import fail as _fail


def _platform_session_factory():
    from conformdag.platform.app import load_settings
    from conformdag.platform.db import initialize_session_factory

    settings = load_settings()
    return settings, initialize_session_factory(settings.dsn)


def baseline_set(scan_id: str) -> None:
    """Mark one platform scan as its repository's baseline."""
    try:
        from sqlalchemy.exc import SQLAlchemyError

        from conformdag.platform.db import RepositoryRow, ScanRow, eligible_baseline
    except ImportError as exc:  # pragma: no cover - guarded by the platform extra
        _fail(ValueError(f"platform extra is not installed: {exc}"))
    try:
        settings, session_factory = _platform_session_factory()
    except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
        _fail(exc)
    if not settings.admin_token:
        _fail(ValueError("platform admin token is not configured; mutations are disabled"))
    try:
        with session_factory() as session:
            scan = session.get(ScanRow, scan_id)
            if scan is None:
                _fail(ValueError(f"scan not found: {scan_id}"))
            repository = session.get(RepositoryRow, scan.repository_id)
            if repository is None:
                _fail(ValueError(f"repository not found for scan: {scan_id}"))
            if eligible_baseline(session, scan.repository_id, scan_id) is None:
                _fail(
                    ValueError(f"scan {scan_id} is not eligible as a baseline: it must be a succeeded, complete scan")
                )
            repository.baseline_scan_id = scan_id
            session.commit()
            repository_id = repository.id
    except typer.Exit:
        # typer.Exit derives from RuntimeError; intentional CLI exits must not be
        # re-caught and reported as a second (empty) error line.
        raise
    except (OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"baseline set: {scan_id} (repository {repository_id})")


def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address for the dashboard API."),
    port: int = typer.Option(8642, "--port", help="Bind port for the dashboard API."),
) -> None:
    """Serve the platform dashboard API on /api/v1."""
    try:
        import uvicorn

        from conformdag.platform.app import create_app
    except ImportError as exc:  # pragma: no cover - guarded by the platform extra
        _fail(ValueError(f"platform extra is not installed: {exc}"))
    settings, session_factory = _platform_session_factory()
    platform_app = create_app(session_factory, settings)
    uvicorn.run(platform_app, host=host, port=port, log_level="info")


def worker_command() -> None:
    """Run the durable platform worker that executes queued scans."""
    try:
        from conformdag.platform.worker import WorkerSettings, run_worker
    except ImportError as exc:  # pragma: no cover - guarded by the platform extra
        _fail(ValueError(f"platform extra is not installed: {exc}"))
    settings, session_factory = _platform_session_factory()
    typer.echo("platform worker started", err=True)
    run_worker(session_factory, settings.dsn, WorkerSettings.from_environment())
