from services.agent_orchestrator.llm import canonical_requested_model


def test_existing_hr_model_label_uses_executable_route_id():
    assert canonical_requested_model("Qwen 2.5 7B") == "qwen2.5:7b"
    assert canonical_requested_model("qwen2.5:7b") == "qwen2.5:7b"
