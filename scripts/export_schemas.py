"""Export JSON Schemas for ConformDAG's public Pydantic models."""

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


def main() -> None:
    output_dir = Path("schemas")
    output_dir.mkdir(exist_ok=True)
    models = {
        "policy-pack": PolicyPack,
        "project-config": ProjectConfig,
        "runtime-manifest": RuntimeManifest,
        "scan-report": ScanReport,
        "semantic-request": SemanticRequest,
        "semantic-response": SemanticResponse,
        "suppression": Suppression,
    }
    for name, model in models.items():
        target = output_dir / f"{name}.json"
        target.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
