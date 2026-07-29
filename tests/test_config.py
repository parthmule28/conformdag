from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from conformdag.config import load_project_config, semantic_api_key


def test_missing_project_config_uses_safe_defaults(tmp_path: Path) -> None:
    config = load_project_config(tmp_path / "missing.yaml")

    assert config.scan.policy_pack == Path("policies/pack.yaml")
    assert config.semantic.enabled is False
    assert config.runtime.enabled is False


def test_semantic_key_is_resolved_only_from_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    from conformdag.models import ProjectConfig

    config = ProjectConfig()
    monkeypatch.setenv(config.semantic.api_key_env, "test-key")

    assert semantic_api_key(config) == "test-key"
