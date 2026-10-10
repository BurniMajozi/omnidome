"""Public summaries and durable clarification stay separate from approval."""
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from services.common.auth import AuthContext
from services.agent_orchestrator import ask_user, steps


@compiles(JSONB, "sqlite")
def compile_jsonb(type_, compiler, **kw):
    return "JSON"


QUESTIONS = {"questions": [{"header": "Period", "question": "Which period?", "options": [{"label": "Month", "description": "Current month"}, {"label": "Year", "description": "Current year"}]}]}


def test_public_steps_redact_and_report_failed_tool():
    async def scenario():
        progress = steps.Steps(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
        token = steps.current.set(progress)
        async def failing():
            return "data.query", {}, {"success": False, "error": "secret"}
        try:
            await steps.track("data", "Query data", failing())
            progress.emit("test", {"text": "someone@example.com Bearer SECRET +27821234567"})
            events = [await progress.queue.get() for _ in range(4)]
            assert events[2]["value"]["status"] == "error"
            assert "SECRET" not in str(events) and "example.com" not in str(events) and "27821234567" not in str(events)
        finally:
            steps.current.reset(token)
    asyncio.run(scenario())


def test_clarification_validation_never_implies_approval():
    questions = ask_user.Questions.model_validate(QUESTIONS).model_dump()["questions"]
    ask_user.validate_answers(questions, [ask_user.Answer(question="Which period?", other="Last quarter")])
    for answer in [ask_user.Answer(question="Which period?", selected=["Approve"]), ask_user.Answer(question="Which period?", selected=["Month", "Year"]), ask_user.Answer(question="Which period?")]:
        with pytest.raises(HTTPException):
            ask_user.validate_answers(questions, [answer])


def test_durable_question_owner_tenant_resume_and_cancel(tmp_path, monkeypatch):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'questions.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: ask_user.PendingQuestion.__table__.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        @asynccontextmanager
        async def scope(*args):
            async with factory() as db:
                async with db.begin():
                    yield db
        monkeypatch.setattr(ask_user, "session_scope", scope)
        tenant, owner, run = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        progress = steps.Steps(run, tenant, owner)
        token = steps.current.set(progress)
        try:
            pending = asyncio.create_task(ask_user.ask(QUESTIONS))
            event = await asyncio.wait_for(progress.queue.get(), 3)
            qid = uuid.UUID(event["value"]["question_id"])
            body = ask_user.Answers(question_id=qid, answers=[ask_user.Answer(question="Which period?", selected=["Month"])])
            for ctx, expected in [(AuthContext(uuid.uuid4(), tenant), 403), (AuthContext(owner, uuid.uuid4()), 404)]:
                with pytest.raises(HTTPException) as exc:
                    await ask_user.answer_question(run, body, ctx)
                assert exc.value.status_code == expected
            await ask_user.answer_question(run, body, AuthContext(owner, tenant))
            result = await asyncio.wait_for(pending, 3)
            assert result == {"success": True, "answers": [{"question": "Which period?", "selected": ["Month"], "other": None}]}
            with pytest.raises(HTTPException) as exc:
                await ask_user.answer_question(run, body, AuthContext(owner, tenant))
            assert exc.value.status_code == 409
            await progress.queue.get()  # answered event
            pending = asyncio.create_task(ask_user.ask(QUESTIONS))
            event = await asyncio.wait_for(progress.queue.get(), 3)
            qid = uuid.UUID(event["value"]["question_id"])
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            async with factory() as db:
                assert (await db.get(ask_user.PendingQuestion, qid)).status == "cancelled"
        finally:
            steps.current.reset(token)
            await engine.dispose()
    asyncio.run(scenario())


def test_live_stream_reports_progress_before_answer_and_cancels(monkeypatch):
    from services.agent_orchestrator.routes import protocols
    from services.agent_orchestrator.protocols import AGUIRunRequest
    stored = []
    class Session:
        def add(self, value): stored.append(value)
    @asynccontextmanager
    async def scope(*args): yield Session()
    monkeypatch.setattr(protocols, "get_session", scope)
    monkeypatch.setattr(protocols.settings, "chat_backend", "native")
    cancelled = []
    class Agent:
        def __init__(self, *args, **kw): pass
        async def run(self, *args, **kw):
            progress = steps.current.get()
            progress.begin("knowledge", "Searching company memory (RAG)")
            try: await asyncio.Event().wait()
            finally: cancelled.append(True)
    monkeypatch.setattr(protocols, "Agent", Agent)
    async def scenario():
        response = await protocols.ag_ui_run(AGUIRunRequest(agent_type="assistant", message="Check memory", context={"user_id": "forged"}), AuthContext(uuid.uuid4(), uuid.uuid4()))
        iterator = response.body_iterator
        assert "RUN_STARTED" in await asyncio.wait_for(anext(iterator), 2)
        event = await asyncio.wait_for(anext(iterator), 2)
        assert '"CUSTOM"' in event and "Searching company memory" in event
        await iterator.aclose()
        assert cancelled == [True]
        assert stored[0].context["user_id"] != "forged"
        assert stored[0].context["owner_user_id"] == stored[0].context["user_id"]
    asyncio.run(scenario())


def test_capability_cards_are_registered_and_have_no_sql_or_customer_rows():
    from services.tenant_memory.knowledge.cards.builders_capabilities import capability_cards
    from services.tenant_memory.knowledge.cards.sources import SOURCES
    cards = capability_cards()
    assert "capabilities" in SOURCES and SOURCES["capabilities"].snapshot
    assert any(c.source_id == "dataset:sales_pipeline" and c.module == "sales" and "age_days" in c.markdown for c in cards)
    assert not any(c.source_id.startswith("tool:analytics.query") for c in cards)
