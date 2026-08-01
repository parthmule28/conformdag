"""Export JSON Schemas for ConformDAG's public Pydantic models."""

import argparse
import json
from pathlib import Path

from conformdag.models import (
    PolicyPack,
    ProjectConfig,
    RuntimeManifest,
    ScanReport,
    SemanticRequest,
    SemanticResponse,
    Suppression,
)


def _rendered_schemas() -> dict[str, str]:
    models = {
        "policy-pack": PolicyPack,
        "project-config": ProjectConfig,
        "runtime-manifest": RuntimeManifest,
        "scan-report": ScanReport,
        "semantic-request": SemanticRequest,
        "semantic-response": SemanticResponse,
        "suppression": Suppression,
    }
    return {
        name: json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for name, model in models.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a checked-in schema differs from the current public model",
    )
    arguments = parser.parse_args()
    output_dir = Path("schemas")
    output_dir.mkdir(exist_ok=True)
    stale: list[Path] = []
    for name, rendered in _rendered_schemas().items():
        target = output_dir / f"{name}.json"
        if arguments.check:
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                stale.append(target)
        else:
            target.write_text(rendered, encoding="utf-8")
    if stale:
        parser.error("stale schemas: " + ", ".join(str(path) for path in stale))


if __name__ == "__main__":
    main()
