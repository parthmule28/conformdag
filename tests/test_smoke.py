from conformdag import __version__


def test_package_version_is_defined() -> None:
    assert __version__ == "1.0.0b1"
