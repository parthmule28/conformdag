"""Verify the reviewed runtime profile identity covers the release being published."""

from __future__ import annotations

import sys

from conformdag.runtime import RuntimeReleaseError, validate_runtime_release


def main() -> int:
    """Run the runtime release identity check for the tagged release ref."""
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: verify_runtime_release.py <release-ref>", file=sys.stderr)
        return 2
    release_ref = sys.argv[1]
    try:
        validate_runtime_release(release_ref)
    except RuntimeReleaseError as exc:
        print(f"runtime release check failed: {exc}", file=sys.stderr)
        return 1
    print(f"runtime profiles reviewed for release {release_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
