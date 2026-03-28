"""Unit tests for PII masker — each pattern masks and unmasks correctly."""

import pytest
from a1.security.pii_masker import PIIMasker


def masker(*patterns) -> PIIMasker:
    return PIIMasker(list(patterns) if patterns else None)


def roundtrip(text: str, pattern: str) -> str:
    """Mask then unmask — should return original text."""
    m = masker(pattern)
    result = m.mask(text)
    return m.unmask(result.masked_text, result.mask_map)


# --- Email ---
def test_email_masked():
    result = masker("email").mask("Contact john@example.com for help")
    assert "john@example.com" not in result.masked_text
    assert "[EMAIL_1]" in result.masked_text


def test_email_unmasked():
    assert roundtrip("Contact john@example.com for help", "email") == "Contact john@example.com for help"


def test_email_multiple():
    result = masker("email").mask("From a@b.com to c@d.org")
    assert result.detection_count == 2


# --- Phone ---
def test_phone_masked():
    result = masker("phone").mask("Call me at 555-867-5309")
    assert "555-867-5309" not in result.masked_text


def test_phone_unmasked():
    text = "My number is 555-867-5309 please call"
    assert roundtrip(text, "phone") == text


# --- SSN ---
def test_ssn_masked():
    result = masker("ssn").mask("SSN: 123-45-6789")
    assert "123-45-6789" not in result.masked_text
    assert "[SSN_1]" in result.masked_text


def test_ssn_unmasked():
    text = "SSN: 123-45-6789 is confidential"
    assert roundtrip(text, "ssn") == text


# --- Credit card ---
def test_credit_card_masked():
    result = masker("credit_card").mask("Card: 4111 1111 1111 1111")
    assert "4111 1111 1111 1111" not in result.masked_text


def test_credit_card_unmasked():
    text = "Pay with 4111-1111-1111-1111"
    assert roundtrip(text, "credit_card") == text


# --- API key ---
def test_api_key_masked():
    result = masker("api_key").mask("Use key sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result.masked_text


def test_api_key_unmasked():
    text = "Token: sk-abc123defgh456ijklmnop789"
    assert roundtrip(text, "api_key") == text


# --- IP address ---
def test_ip_masked():
    result = masker("ip_address").mask("Server at 192.168.1.100")
    assert "192.168.1.100" not in result.masked_text


def test_ip_unmasked():
    text = "Connect to 10.0.0.1 port 22"
    assert roundtrip(text, "ip_address") == text


# --- AWS key ---
def test_aws_key_masked():
    result = masker("aws_key").mask("Key: AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in result.masked_text


# --- Password ---
def test_password_masked():
    result = masker("password").mask("password: SuperSecret123")
    assert "SuperSecret123" not in result.masked_text


def test_password_unmasked():
    text = "password: MyP@ssw0rd"
    assert roundtrip(text, "password") == text


# --- Private key ---
def test_private_key_masked():
    result = masker("private_key").mask("-----BEGIN RSA PRIVATE KEY-----")
    assert "BEGIN RSA PRIVATE KEY" not in result.masked_text


# --- Empty/edge cases ---
def test_empty_text():
    result = masker("email").mask("")
    assert result.masked_text == ""
    assert result.detection_count == 0


def test_no_pii_unchanged():
    text = "Hello, this is a normal message with no PII."
    result = masker("email").mask(text)
    assert result.masked_text == text
    assert result.detection_count == 0


# --- mask_messages ---
def test_mask_messages_roundtrip():
    m = masker("email")
    msgs = [
        {"role": "user", "content": "email me at test@example.com"},
        {"role": "assistant", "content": "Sure, I will email test@example.com"},
    ]
    masked_msgs, mask_map = m.mask_messages(msgs)
    assert "test@example.com" not in masked_msgs[0]["content"]
    assert "test@example.com" not in masked_msgs[1]["content"]
    for msg in masked_msgs:
        restored = m.unmask(msg["content"], mask_map)
        assert "test@example.com" in restored
