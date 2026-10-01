from __future__ import annotations

import pytest

from conformdag.security.redaction import credential_name_like, redact_credentials, redact_evidence


@pytest.mark.parametrize(
    "name",
    [
        "password",
        "passwd",
        "token",
        "secret",
        "api_key",
        "api-key",
        "apikey",
        "credential",
        "PASSWORD",
        "db_password",
        "db-password",
        "auth_token",
        "clientSecret",
        "apiKey",
        "githubCredential",
    ],
)
def test_credential_name_like_detects_credential_identifier_components(name: str) -> None:
    assert credential_name_like(name)


@pytest.mark.parametrize(
    "name",
    ["secretary", "tokenizer", "passwordless", "credentials_counted"],
)
def test_credential_name_like_does_not_match_benign_words(name: str) -> None:
    assert not credential_name_like(name)


@pytest.mark.parametrize(
    "text,secret",
    [
        ("password=c15-test-password-value", "c15-test-password-value"),
        ("password = c15-test-password-value", "c15-test-password-value"),
        ("password: c15-test-password-value", "c15-test-password-value"),
        ("password='c15-test-password-value'", "c15-test-password-value"),
        ('password = "c15-test-password-value"', "c15-test-password-value"),
        ('"password": "c15-test-password-value"', "c15-test-password-value"),
        ("'token': 'c15-test-token-value'", "c15-test-token-value"),
        ("api_key=c15-test-api-key-value", "c15-test-api-key-value"),
        ("api-key: c15-test-api-key-value", "c15-test-api-key-value"),
        ("apikey = c15-test-api-key-value", "c15-test-api-key-value"),
        ("credential=c15-test-credential-value", "c15-test-credential-value"),
        ("clientSecret=c15-test-client-secret-value", "c15-test-client-secret-value"),
        ("auth_token=c15-test-auth-token-value", "c15-test-auth-token-value"),
        (
            "Authorization: Bearer c15-test-bearer-value",
            "c15-test-bearer-value",
        ),
        ("Bearer c15-test-bearer-value", "c15-test-bearer-value"),
        (
            "postgresql://user:c15-test-dsn-password@database/db",
            "c15-test-dsn-password",
        ),
        (
            "https://user:c15-test-url-password@example.test/path",
            "c15-test-url-password",
        ),
    ],
)
def test_redact_credentials_removes_supported_credential_values(text: str, secret: str) -> None:
    redacted = redact_credentials(text)

    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_redact_credentials_handles_multiple_values_and_is_idempotent() -> None:
    text = (
        "password=c15-test-password-value; token='c15-test-token-value'; "
        "https://user:c15-test-url-password@example.test/path"
    )

    redacted = redact_credentials(text)

    assert "c15-test-password-value" not in redacted
    assert "c15-test-token-value" not in redacted
    assert "c15-test-url-password" not in redacted
    assert redact_credentials(redacted) == redacted


def test_redact_credentials_preserves_already_redacted_content() -> None:
    text = 'password="[REDACTED]" and token=[REDACTED]'

    assert redact_credentials(text) == text


@pytest.mark.parametrize(
    "text,secret",
    [
        ("password=[REDACTED]c15-test-unquoted-suffix", "c15-test-unquoted-suffix"),
        ('password="[REDACTED]c15-test-quoted-suffix"', "c15-test-quoted-suffix"),
    ],
)
def test_redact_credentials_does_not_trust_a_redaction_marker_prefix(text: str, secret: str) -> None:
    redacted = redact_credentials(text)

    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_redact_credentials_finds_nested_assignment_in_noncredential_value() -> None:
    text = "owner='password=c15-test-password-value'"

    redacted = redact_credentials(text)

    assert redacted == "owner='password=[REDACTED]'"
    assert "c15-test-password-value" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_evidence_redacts_quoted_value_before_truncating() -> None:
    text = 'password="c15-test-password-value"'
    max_chars = 19

    redacted = redact_evidence(text, max_chars=max_chars)

    assert redacted == redact_credentials(text)[:max_chars]
    assert "c15-test-password-value" not in redacted
    assert "c15-test-" not in redacted
