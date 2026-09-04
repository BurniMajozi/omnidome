"""TDD tests for Task 7: per-agent deployable chat API (pure helpers, no DB)."""

import pytest
from pydantic import ValidationError


def test_validate_identifier_accepts_and_rejects():
    from routes.chat_deployments import validate_identifier

    assert validate_identifier("domebot-help") is True
    assert validate_identifier("AB") is False
    assert validate_identifier("a") is False
    assert validate_identifier("x" * 65) is False
    assert validate_identifier("has space") is False


def test_hash_verify_key_roundtrip():
    from routes.chat_deployments import hash_key, verify_key

    h = hash_key("supersecret123")
    assert h != "supersecret123"
    assert verify_key("supersecret123", h) is True
    assert verify_key("wrongkey!!", h) is False


def test_chat_deployment_create_schema_validation():
    from schemas import ChatDeploymentCreate

    with pytest.raises(ValidationError):
        ChatDeploymentCreate(agent_type="bogus", identifier="domebot-help")
    with pytest.raises(ValidationError):
        ChatDeploymentCreate(agent_type="support", identifier="domebot-help", access_key="short")


def test_chat_deployed_constant_importable():
    import audit_actions as aa

    assert aa.CHAT_DEPLOYED == "chat.deployed"
