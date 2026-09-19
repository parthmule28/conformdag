"""Disposable ConformDAG platform for the Playwright browser journeys."""

from __future__ import annotations

import argparse
import signal
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

import uvicorn

from conformdag.platform.demo import build_demo_workspace, seed_demo_scenario, start_demo_worker

if TYPE_CHECKING:
    from uvicorn import Server

SignalHandler = Callable[[int, FrameType | None], object]


def _stop_bridge(server_holder: list[Server | None]) -> SignalHandler:
    """Build a cleanup-safe SIGINT/SIGTERM bridge covering the whole launcher lifetime.

    Mirrors ``scripts/demo.py``: while the holder is empty (workspace seeding,
    app construction) a signal raises ``KeyboardInterrupt`` so the exception
    unwinds through the ``TemporaryDirectory`` context and removes the seeded
    state, instead of the default terminating disposition killing the process
    mid-seed. Once the Uvicorn server exists the bridge is cooperative
    (``should_exit``) and absorbs Uvicorn's post-shutdown signal re-raise;
    while Uvicorn is serving, its own handlers remain in charge and this
    bridge is only restored as the previous handler at that point.
    """

    def handler(signum: int, frame: FrameType | None) -> object:
        server = server_holder[0]
        if server is None:
            raise KeyboardInterrupt from None
        server.should_exit = True
        return None

    return handler


def main(argv: list[str] | None = None) -> int:
    """Run the disposable platform until interrupted, then remove its state."""
    parser = argparse.ArgumentParser(description="Disposable platform for browser e2e journeys")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    parser.add_argument("--token", default="secret-token")
    args = parser.parse_args(argv)

    from conformdag.platform.app import PlatformSettings, create_app
    from conformdag.platform.db import create_session_factory
    from conformdag.platform.worker import request_shutdown

    server_holder: list[Server | None] = [None]
    stop_bridge = _stop_bridge(server_holder)
    installed: list[tuple[int, SignalHandler]] = []
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            installed.append((signum, signal.signal(signum, stop_bridge)))
        try:
            with tempfile.TemporaryDirectory(prefix="conformdag-e2e-") as tmp:
                workspace = build_demo_workspace(Path(tmp))
                seed_demo_scenario(workspace)
                worker = start_demo_worker(workspace)
                try:
                    settings = PlatformSettings(
                        dsn=workspace.dsn,
                        admin_token=args.token,
                        workspace=workspace.workspace_path,
                    )
                    app = create_app(
                        create_session_factory(workspace.dsn),
                        settings,
                        workspace_path=workspace.workspace_path,
                    )
                    uvicorn_config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
                    uvicorn_server = uvicorn.Server(uvicorn_config)
                    server_holder[0] = uvicorn_server
                    uvicorn_server.run()
                finally:
                    server = server_holder[0]
                    if server is not None:
                        server.should_exit = True
                    request_shutdown()
                    worker.join(timeout=10.0)
        except KeyboardInterrupt:
            pass
    finally:
        for signum, previous_handler in reversed(installed):
            signal.signal(signum, previous_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
