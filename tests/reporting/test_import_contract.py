"""Import and compatibility contract for the future reporting package."""


def test_canonical_reporting_modules_and_gate_owner_are_importable() -> None:
    from conformdag.gates import has_blocking_failures
    from conformdag.reporting.html import render_html
    from conformdag.reporting.normalize import normalize_report
    from conformdag.reporting.sarif import render_sarif
    from conformdag.reporting.suppressions import apply_suppressions

    assert callable(normalize_report)
    assert callable(apply_suppressions)
    assert callable(render_sarif)
    assert callable(render_html)
    assert callable(has_blocking_failures)


def test_reporting_facade_reexports_canonical_objects_and_stable_exports() -> None:
    import conformdag.reporting as reporting
    from conformdag.gates import has_blocking_failures as gate_has_blocking_failures
    from conformdag.reporting.html import render_html as canonical_render_html
    from conformdag.reporting.normalize import normalize_report as canonical_normalize_report
    from conformdag.reporting.sarif import render_sarif as canonical_render_sarif
    from conformdag.reporting.suppressions import apply_suppressions as canonical_apply_suppressions

    assert reporting.apply_suppressions is canonical_apply_suppressions
    assert reporting.normalize_report is canonical_normalize_report
    assert reporting.render_sarif is canonical_render_sarif
    assert reporting.render_html is canonical_render_html
    assert reporting.has_blocking_failures is gate_has_blocking_failures
    assert reporting.__all__ == [
        "apply_suppressions",
        "normalize_report",
        "render_sarif",
        "render_html",
        "has_blocking_failures",
    ]
