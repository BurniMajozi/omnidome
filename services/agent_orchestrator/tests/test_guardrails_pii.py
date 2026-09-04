"""PII scan + mask tests (TDD — written before implementation)."""

from guardrails.pii import PATTERNS, mask_text, scan_pii


def test_sa_id_detected_and_masked():
    text = "My ID is 8001015009087 thanks"
    hits = scan_pii(text)
    assert any(h["type"] == "sa_id" and h["value"] == "8001015009087" for h in hits)
    hit = next(h for h in hits if h["type"] == "sa_id")
    assert hit["span"] == (text.index("8001015009087"), text.index("8001015009087") + 13)
    masked = mask_text(text, hits)
    assert "8001015009087" not in masked
    assert "[SA_ID_MASKED]" in masked


def test_sa_phone_detected_and_masked():
    for phone in ("+27821234567", "0821234567"):
        text = f"Call me on {phone} please"
        hits = scan_pii(text)
        assert any(h["type"] == "sa_phone" and h["value"] == phone for h in hits), phone
        masked = mask_text(text)
        assert phone not in masked
        assert "[SA_PHONE_MASKED]" in masked


def test_email_detected_and_masked():
    text = "Email me at johan.vanwyk@example.co.za please"
    hits = scan_pii(text)
    assert any(
        h["type"] == "email" and h["value"] == "johan.vanwyk@example.co.za" for h in hits
    )
    masked = mask_text(text, hits)
    assert "johan.vanwyk@example.co.za" not in masked
    assert "[EMAIL_MASKED]" in masked


def test_clean_text_returns_no_hits():
    text = "Hello, I need help with my fibre line in Cape Town."
    hits = scan_pii(text)
    assert hits == []
    assert mask_text(text) == text


def test_none_and_empty_input_no_hits_no_raise():
    assert scan_pii(None) == []
    assert scan_pii("") == []
    assert mask_text(None) == ""
    assert mask_text("") == ""


def test_patterns_dict_has_required_keys():
    assert set(PATTERNS) >= {"sa_id", "sa_phone", "email"}
