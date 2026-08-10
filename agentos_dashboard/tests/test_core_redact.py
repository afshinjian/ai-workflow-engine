"""`core.redact.redact_secrets` — SC-09 secret-shaped substring redaction."""

from __future__ import annotations

import pytest

from agentos_dashboard.core.redact import REDACTED_PLACEHOLDER, redact_mapping, redact_secrets


@pytest.mark.parametrize(
    "secret",
    [
        "api_key=sk-THISISAFAKESECRETVALUE1234567890",
        'api_key: "sk-THISISAFAKESECRETVALUE1234567890"',
        "SECRET=hunter2-not-a-real-password-value",
        "token = 'abcdef0123456789abcdefTOKEN'",
        "password: correct-horse-battery-staple",
        "private_key=-----BEGINFAKEKEY-----",
        "client_secret=abcdefghijklmnop0123",
        '"api_key": "a quoted value with spaces"',
        "'PASSWORD' : 'mixed CASE value'",
        "api_key\n=\nsecret-on-another-line",
        "api_key%3Durl-encoded-secret",
        "&quot;token&quot;: &quot;html-escaped-secret&quot;",
    ],
)
def test_key_value_assignments_are_redacted(secret: str) -> None:
    text = f"before {secret} after"
    result = redact_secrets(text)
    assert REDACTED_PLACEHOLDER in result
    # The literal secret value never survives, only the key name + placeholder.
    assert "sk-THISISAFAKESECRETVALUE1234567890" not in result
    assert "hunter2-not-a-real-password-value" not in result
    assert "correct-horse-battery-staple" not in result
    assert "before" in result and "after" in result


def test_bearer_token_is_redacted() -> None:
    text = "Authorization: Bearer abcDEF012345.ghiJKL678901-secretpart"
    result = redact_secrets(text)
    assert "abcDEF012345" not in result
    assert result.count("Bearer") == 1
    assert REDACTED_PLACEHOLDER in result


@pytest.mark.parametrize(
    "text, leaked",
    [
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ('Authorization: "opaque value with spaces"', "opaque value with spaces"),
        ("Proxy-Authorization=Token abcdef012345", "abcdef012345"),
        ("authorization%3Dbearer%20abcdef012345", "abcdef012345"),
    ],
)
def test_authorization_style_values_are_redacted(text: str, leaked: str) -> None:
    result = redact_secrets(text)
    assert leaked not in result
    assert REDACTED_PLACEHOLDER in result


@pytest.mark.parametrize(
    "token",
    [
        "AKIAABCDEFGHIJKLMNOP",
        "ghp_" + "a" * 36,
        "github_pat_" + "a" * 22,
        "xoxb-" + "1234567890",
        "sk-" + "a" * 24,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_signaturepart",
    ],
)
def test_vendor_token_shapes_are_redacted(token: str) -> None:
    text = f"pasted credential: {token} (end)"
    result = redact_secrets(text)
    assert token not in result
    assert REDACTED_PLACEHOLDER in result
    assert "(end)" in result


def test_ordinary_text_is_left_untouched() -> None:
    text = "The build passed with 12 tests; see docs/CONTEXT.md for details."
    assert redact_secrets(text) == text


def test_a_commit_sha_is_not_mistaken_for_a_secret() -> None:
    """Regression guard: 40/64-hex-char content (SHAs, digests) must survive untouched — the
    whole point of a shape-based denylist over a generic entropy detector."""
    text = "HEAD is ca5bf64f905d435b4b56f9a125c8c7c78eaba145, digest " + "a" * 64
    assert redact_secrets(text) == text


def test_multiple_secrets_in_one_text_are_all_redacted() -> None:
    text = "api_key=abcd1234efgh5678 and also token=zzzz9999yyyy8888 in one message"
    result = redact_secrets(text)
    assert "abcd1234efgh5678" not in result
    assert "zzzz9999yyyy8888" not in result
    assert result.count(REDACTED_PLACEHOLDER) == 2


def test_url_query_redaction_does_not_consume_the_next_parameter() -> None:
    result = redact_secrets("https://local.test/?api_key=secret-value&next=ordinary")
    assert "secret-value" not in result
    assert "&next=ordinary" in result


def test_markdown_and_punctuation_do_not_bypass_redaction() -> None:
    result = redact_secrets("`token=adjacent-secret`, [next](./ordinary); password=pw!")
    assert "adjacent-secret" not in result
    assert "password=pw" not in result
    assert result.count(REDACTED_PLACEHOLDER) == 2


def test_long_secret_value_is_not_partially_retained() -> None:
    secret = "z" * 5000
    result = redact_secrets(f"api_key={secret}")
    assert secret not in result
    assert result == f"api_key={REDACTED_PLACEHOLDER}"


def test_redaction_is_idempotent() -> None:
    once = redact_secrets("token=one Authorization: Bearer two-two")
    assert redact_secrets(once) == once


def test_recursive_mapping_redacts_values_without_changing_schema_keys() -> None:
    result = redact_mapping(
        {"event": "note", "nested": {"body": "password=hidden"}, "items": ["token=gone", 2]}
    )
    assert result == {
        "event": "note",
        "nested": {"body": f"password={REDACTED_PLACEHOLDER}"},
        "items": [f"token={REDACTED_PLACEHOLDER}", 2],
    }


@pytest.mark.parametrize(
    "ordinary",
    [
        "550e8400-e29b-41d4-a716-446655440000",
        "/tmp/token=ordinary/path",
        "src/tokenizer.py monkey auth_tokenizer APIKeyFactory",
        "sha256:" + "f" * 64,
    ],
)
def test_ordinary_identifiers_paths_hashes_and_uuids_are_not_redacted(ordinary: str) -> None:
    assert redact_secrets(ordinary) == ordinary


def test_empty_string_is_returned_unchanged() -> None:
    assert redact_secrets("") == ""
