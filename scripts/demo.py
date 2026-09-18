"""Disposable local ConformDAG demo launcher.

``mise run demo`` seeds a realistic governance scenario through the production
platform stack (Alembic migrations, the durable worker, and the normal scan
path) inside a temporary directory, serves the real dashboard on the loopback
interface, and removes every seeded row when the process exits. Nothing here
requires Docker, network access, or secrets, and the demo token never leaves
the local machine.
"""

from __future__ import annotations

import argparse
import signal
import socket
import sys
import tempfile
import webbrowser
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from uvicorn import Server

SignalHandler = Callable[[int, FrameType | None], object]

DEFAULT_DEMO_HOST = "127.0.0.1"
DEFAULT_DEMO_PORT = 8642
DEFAULT_DEMO_TOKEN = "demo-local-disposable-token"
WORKER_JOIN_TIMEOUT_SECONDS = 10.0


def demo_url(host: str, port: int) -> str:
    """Return the dashboard URL that enables the guided client demo tour."""
    return f"http://{host}:{port}/?demo=1"


def ensure_port_available(host: str, port: int) -> None:
    """Bind-test the requested endpoint so an occupied port fails before seeding.

    The probe socket is closed immediately; this check only reports a conflict
    early with an actionable message instead of after the seed completes.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as error:
        message = f"{host}:{port} is already in use; stop that process or pass a different --port"
        raise RuntimeError(message) from error
    finally:
        probe.close()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a disposable local ConformDAG demo (Ctrl-C removes its seeded state)",
    )
    parser.add_argument("--host", default=DEFAULT_DEMO_HOST, help="Loopback bind address for the dashboard.")
    parser.add_argument("--port", type=int, default=DEFAULT_DEMO_PORT, help="Bind port for the dashboard.")
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        dest="open_browser",
        default=True,
        help="Open the demo URL in the browser once seeding succeeds.",
    )
    parser.add_argument("--token", default=DEFAULT_DEMO_TOKEN, help="Admin token for this local demo instance only.")
    return parser.parse_args(argv)


def _make_server(app: FastAPI, host: str, port: int) -> Server:
    """Build the real Uvicorn server for the demo app (unit-test seam)."""
    import uvicorn

    return uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))


def _signal_exit_forwarder(server: Server) -> SignalHandler:
    """Build a handler that routes SIGINT/SIGTERM into Uvicorn's cooperative exit.

    Installing this before ``server.run()`` matters: after its graceful
    shutdown Uvicorn restores the previous handlers and re-raises the captured
    signal. With this handler installed the re-raise is absorbed cooperatively
    instead of killing the process with the default terminating disposition,
    so the ``finally`` block always gets to clean the temporary state up.
    """

    def handler(signum: int, frame: FrameType | None) -> object:
        server.should_exit = True
        return None

    return handler


def main(argv: list[str] | None = None) -> int:
    """Seed, serve, and clean up one disposable local demo instance."""
    args = _parse_args(argv)

    try:
        ensure_port_available(args.host, args.port)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    from conformdag.platform.app import PlatformSettings, create_app
    from conformdag.platform.db import initialize_session_factory
    from conformdag.platform.demo import build_demo_workspace, seed_demo_scenario, start_demo_worker
    from conformdag.platform.worker import request_shutdown

    url = demo_url(args.host, args.port)
    try:
        with tempfile.TemporaryDirectory(prefix="conformdag-demo-") as tmp:
            print("Seeding the disposable demo scenario through the real worker (this takes a moment)...")
            workspace = build_demo_workspace(Path(tmp))
            seed_demo_scenario(workspace)
            worker = start_demo_worker(workspace)
            settings = PlatformSettings(
                dsn=workspace.dsn,
                admin_token=args.token,
                workspace=workspace.workspace_path,
            )
            app = create_app(
                initialize_session_factory(workspace.dsn),
                settings,
                workspace_path=workspace.workspace_path,
            )
            server = _make_server(app, args.host, args.port)
            print(f"ConformDAG demo dashboard: {url}")
            print("This instance is loopback-only and disposable: every seeded row lives in a temporary directory.")
            print(f"The admin token is for this local demo only: {args.token}")
            print("Press Ctrl-C to stop; the seeded temporary state is removed automatically on exit.")
            exit_forwarder = _signal_exit_forwarder(server)
            installed: list[tuple[int, SignalHandler]] = []
            try:
                for signum in (signal.SIGINT, signal.SIGTERM):
                    installed.append((signum, signal.signal(signum, exit_forwarder)))
                if args.open_browser:
                    webbrowser.open(url)
                server.run()
            except KeyboardInterrupt:  # pragma: no cover - defensive; the forwarder absorbs Ctrl-C
                pass
            finally:
                server.should_exit = True
                request_shutdown()
                worker.join(timeout=WORKER_JOIN_TIMEOUT_SECONDS)
                for signum, previous_handler in reversed(installed):
                    signal.signal(signum, previous_handler)
    except OSError as error:
        print(f"error: the demo could not start or serve: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; disposing the temporary demo state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
