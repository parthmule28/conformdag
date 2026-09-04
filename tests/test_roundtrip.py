"""Round-trip release gate: fix benchmark violations and assert clean re-scans."""

from pathlib import Path

import pytest

from conformdag.roundtrip import run_fix_roundtrip

CORPUS_ROOT = Path("benchmarks/synthetic")
MANIFEST = CORPUS_ROOT / "manifest.yaml"
PACK = Path("policies/pack.yaml")


@pytest.mark.skipif(
    not (CORPUS_ROOT / "manifest.yaml").is_file() or not PACK.is_file(),
    reason="benchmark corpus and organizational pack are not present",
)
def test_roundtrip_gate_fixes_every_autofix_violation_case() -> None:
    result = run_fix_roundtrip(MANIFEST, PACK, CORPUS_ROOT)

    failures = [case for case in result.cases if not case.passed]
    assert result.total_cases == 80, "expected the autofix violation population"
    assert failures == [], "; ".join(f"{case.case_id}: {case.error}" for case in failures)
    assert result.passed
