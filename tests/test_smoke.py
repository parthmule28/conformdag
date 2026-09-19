"""Documentation contract tests for the disposable local demo.

These protect the documented demo entry points (`mise run setup` + `mise run demo`)
without testing prose layout.
"""

from pathlib import Path

from conformdag import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_package_version_is_defined() -> None:
    assert __version__ == "1.0.0b1"


def test_mise_toml_defines_the_demo_task() -> None:
    assert "[tasks.demo]" in _read("mise.toml")


def test_readme_leads_with_the_demo() -> None:
    readme = _read("README.md")
    assert "## Run the demo" in readme
    assert "mise run setup" in readme
    assert "mise run demo" in readme
    assert readme.index("## Run the demo") < readme.index("### The governance platform")


def test_user_guide_documents_demo_controls_and_compose_distinction() -> None:
    guide = _read("docs/user-guide.md")
    assert "## Local product demo" in guide
    demo_section = guide[guide.index("## Local product demo") :]
    assert "mise run demo" in demo_section
    assert "mise run demo -- --no-open --port 8765" in demo_section
    assert "127.0.0.1" in demo_section
    assert "Ctrl-C" in demo_section
    assert "docker compose" in demo_section.lower()
