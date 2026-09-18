"""Disposable ConformDAG platform for the Playwright browser journeys."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn

from conformdag.platform.demo import build_demo_workspace, seed_demo_scenario, start_demo_worker


def main() -> int:
    """Run the disposable platform until interrupted, then remove its state."""
    parser = argparse.ArgumentParser(description="Disposable platform for browser e2e journeys")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    parser.add_argument("--token", default="secret-token")
    args = parser.parse_args()

    from conformdag.platform.app import PlatformSettings, create_app
    from conformdag.platform.db import create_session_factory
    from conformdag.platform.worker import request_shutdown

    with tempfile.TemporaryDirectory(prefix="conformdag-e2e-") as tmp:
        workspace = build_demo_workspace(Path(tmp))
        seed_demo_scenario(workspace)
        worker = start_demo_worker(workspace)
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
        try:
            uvicorn_server.run()
        except KeyboardInterrupt:
            pass
        finally:
            request_shutdown()
            worker.join(timeout=10.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
