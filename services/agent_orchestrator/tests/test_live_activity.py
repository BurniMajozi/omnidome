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

@pytest.mark.parametrize("count", [2,4])
def test_retry_workflow_question_matches_advertised_schema(count):
    body={"questions":[{"header":"Retry Workflow","multi_select":False,"question":"Which workflow would you like to retry?",
        "options":[{"label":f"Workflow {i}","description":"Currently active workflow"} for i in range(count)]}]}
    assert ask_user.Questions.model_validate(body).questions[0].header=="Retry Workflow"
    schema=ask_user.tool_schema()
    assert schema["properties"]["questions"]["items"]["properties"]["header"]["maxLength"]==24
    assert "$ref" not in str(schema)

def test_question_validation_names_the_actual_bad_field():
    from pydantic import ValidationError
    body={"questions":[{**QUESTIONS["questions"][0],"header":"x"*25}]}
    with pytest.raises(ValidationError) as error:ask_user.Questions.model_validate(body)
    message=ask_user.validation_error(error.value)
    assert "questions.0.header" in message and "24" in message


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


def test_live_stream_reports_progress_before_answer_and_survives_disconnect_until_cancelled(monkeypatch):
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
        response_ctx_tenant, response_ctx_user = uuid.uuid4(), uuid.uuid4()
        monkeypatch.setattr(protocols.run_registry, "_notify_done", lambda rec: asyncio.sleep(0))
        response = await protocols.ag_ui_run(AGUIRunRequest(agent_type="assistant", message="Check memory", context={"user_id": "forged"}), AuthContext(response_ctx_user, response_ctx_tenant))
        iterator = response.body_iterator
        assert "RUN_STARTED" in await asyncio.wait_for(anext(iterator), 2)
        event = await asyncio.wait_for(anext(iterator), 2)
        assert '"CUSTOM"' in event and "Searching company memory" in event
        await iterator.aclose()  # the browser navigated away: the run belongs to the backend and keeps going
        await asyncio.sleep(0.05)
        assert cancelled == []
        ctx = AuthContext(response_ctx_user, response_ctx_tenant)
        run = protocols.run_registry.list_for(ctx.tenant_id, ctx.user_id)[0]
        await protocols.ag_ui_run_cancel(run.run_id, ctx)  # an explicit Stop does cancel it
        await asyncio.gather(run.task, return_exceptions=True)
        assert cancelled == [True] and run.status == "cancelled"
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


def test_no_raw_sql_tool_is_registered_for_any_agent():
    from services.agent_orchestrator.tools import tool_registry
    names = {t.name for t in tool_registry.list_tools()}
    assert not {n for n in names if "sql" in n.lower() or n in {"analytics.query", "analytics_query"}}
    for agent in ("auto", "orchestrator", "executive", "analytics", "assistant"):
        assert not {"analytics.query", "analytics_query"} & {t.name for t in tool_registry.filter_for_agent(agent)}
    assert {"data.query", "data.datasets"} <= {t.name for t in tool_registry.filter_for_agent("analytics")}
