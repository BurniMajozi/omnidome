"""Unit tests for Long-Horizon Agent and Voice Integration (Cookbook: 'Build a Long-Horizon Agent')."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
import pytest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.long_horizon import (
    check_ceilings,
    estimate_token_cost,
    run_long_horizon_agent,
    DONE_SENTINEL,
    LongHorizonJobResult,
)
from services.agent_orchestrator.voice import transcribe_audio, synthesize_speech


def test_check_ceilings_cost_and_steps():
    """Cookbook step 1: Stop conditions fire as soon as cost or step ceiling is reached."""
    # Under limits
    assert check_ceilings(step_count=5, cost_usd=0.50, tokens_used=1000, max_steps=10, max_cost_usd=2.0) is None

    # Cost ceiling breached
    cost_breach = check_ceilings(step_count=5, cost_usd=2.05, tokens_used=1000, max_steps=10, max_cost_usd=2.0)
    assert cost_breach is not None
    assert "max_cost_usd" in cost_breach

    # Step count ceiling breached
    step_breach = check_ceilings(step_count=15, cost_usd=0.50, tokens_used=1000, max_steps=10, max_cost_usd=2.0)
    assert step_breach is not None
    assert "max_steps" in step_breach


def test_estimate_token_cost():
    """Verify cost calculation scales linearly with token volume."""
    cost = estimate_token_cost(prompt_tokens=1000, completion_tokens=500)
    # 1000 * 0.000002 = 0.002, 500 * 0.000008 = 0.004 -> 0.006
    assert 0.0059 <= cost <= 0.0061


def test_long_horizon_run_terminates_on_done_sentinel():
    """Cookbook step 4: loop terminates when agent emits [DONE] sentinel."""
    async def _run():
        mock_turn = {
            "content": f"Research complete. All fiber nodes reconciled. {DONE_SENTINEL}",
            "tool_calls": [{"name": "mock_tool", "result": {"ok": True}}],
            "status": "completed",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        with patch("services.agent_orchestrator.long_horizon.Agent.run", AsyncMock(return_value=mock_turn)), \
             patch("services.agent_orchestrator.long_horizon.dispatch_completion_notification", AsyncMock()):
            result: LongHorizonJobResult = await run_long_horizon_agent(
                prompt="Audit all fiber ports in Sandton.",
                agent_type="assistant",
                max_cost_usd=5.00,
                max_iterations=5,
            )

            assert result.status == "completed"
            assert result.stopped_by == "done_sentinel"
            assert result.iterations == 1
            assert DONE_SENTINEL not in result.final_output
            assert "Research complete." in result.final_output

    asyncio.run(_run())


def test_long_horizon_resumable_checkpoint():
    """Cookbook step 2: resuming from saved checkpoint continues without restarting from scratch."""
    async def _run():
        saved_checkpoint = {
            "job_id": "lh_test_12345",
            "conversation_id": str(uuid.uuid4()),
            "iterations_completed": 2,
            "total_steps": 8,
            "total_tokens": 1200,
            "accumulated_cost_usd": 0.05,
            "history": [
                {"role": "user", "content": "Initial prompt"},
                {"role": "assistant", "content": "Partial progress report"},
            ],
            "last_output": "Partial progress report",
        }

        mock_turn = {
            "content": f"Final verification passed. {DONE_SENTINEL}",
            "tool_calls": [],
            "status": "completed",
            "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
        }

        with patch("services.agent_orchestrator.long_horizon.Agent.run", AsyncMock(return_value=mock_turn)), \
             patch("services.agent_orchestrator.long_horizon.dispatch_completion_notification", AsyncMock()):
            result = await run_long_horizon_agent(
                prompt="Initial prompt",
                max_cost_usd=5.00,
                max_iterations=5,
                resume_from_checkpoint=saved_checkpoint,
            )

            # Iterations should increment from saved 2 -> 3
            assert result.iterations == 1  # 1 iteration in this resumption run
            assert result.checkpoint["iterations_completed"] == 3
            assert result.total_tokens == 1500  # 1200 + 300
            assert result.status == "completed"

    asyncio.run(_run())


def test_no_evidence_progress_stops_after_one_turn_and_preserves_cost_metadata():
    async def _run():
        turn = {"content": "I cannot inspect this component with my current tools.",
                "tool_calls": [], "status": "completed",
                "model_calls": [{"model": "free/example", "provider": "OpenRouter", "cost_usd": 0,
                                 "prompt_tokens": 1200, "completion_tokens": 200}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 200,
                          "total_tokens": 1400, "cost": 0.0}}
        agent_run = AsyncMock(return_value=turn)
        with patch("services.agent_orchestrator.long_horizon.Agent.run", agent_run), \
             patch("services.agent_orchestrator.long_horizon.evaluate_adversarial_jev",
                   AsyncMock(return_value=(False, "Missing source evidence", {
                       "provider": "typesafe", "model": "jev-latest", "total_tokens": 80,
                       "cost_usd": None}))), \
             patch("services.agent_orchestrator.long_horizon.dispatch_completion_notification", AsyncMock()):
            result = await run_long_horizon_agent("Inspect the Sales AI Lead Warmers component.", max_iterations=10)
        assert agent_run.await_count == 1
        assert result.status == "awaiting_review"
        assert result.stopped_by == "no_evidence_progress"
        assert result.total_tokens == 1480
        assert result.to_dict()["model_calls"][0]["model"] == "free/example"
        assert result.to_dict()["jev_usage"]["cost_reported"] is False
    asyncio.run(_run())


def test_voice_stt_transcription_mock():
    """Cookbook step 5: Voice audio translates to transcribed text."""
    async def _run():
        import httpx
        mock_resp = httpx.Response(200, json={"text": "My router has a red light and needs a reboot"})
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            text = await transcribe_audio(b"fake_audio_bytes", model="openai/whisper-1")
            assert text == "My router has a red light and needs a reboot"

    asyncio.run(_run())


def test_voice_tts_synthesis_mock():
    """Cookbook step 6: Text response synthesizes to audio bytes."""
    async def _run():
        import httpx
        fake_audio_bytes = b"ID3\x03\x00\x00\x00fake_mp3_payload"
        mock_resp = httpx.Response(200, content=fake_audio_bytes)
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            audio = await synthesize_speech("Your line has been successfully reset.", voice="alloy")
            assert audio == fake_audio_bytes

    asyncio.run(_run())
