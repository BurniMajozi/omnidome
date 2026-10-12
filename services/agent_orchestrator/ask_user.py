"""Durable, owner-scoped clarification: answers may arrive at another worker."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import DateTime, String, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from services.agent_orchestrator.models import Base
from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.agent_orchestrator.steps import current


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: str = Field(min_length=1, max_length=24)
    question: str = Field(min_length=1, max_length=500)
    options: list[Option] = Field(min_length=2, max_length=4)
    multi_select: bool = False
    @model_validator(mode="after")
    def unique_options(self):
        if len({o.label for o in self.options}) != len(self.options): raise ValueError("Option labels must be unique")
        return self


class Questions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[Question] = Field(min_length=1, max_length=3)

def tool_schema():
    """Inline references for provider compatibility, from the actual validator."""
    schema = Questions.model_json_schema()
    definitions = schema.pop("$defs", {})
    def inline(value):
        if isinstance(value, list): return [inline(item) for item in value]
        if not isinstance(value, dict): return value
        if "$ref" in value: return inline(definitions[value["$ref"].rsplit("/", 1)[-1]])
        return {key: inline(item) for key,item in value.items()}
    return inline(schema)

def validation_error(error):
    return "Invalid ask_user arguments: " + "; ".join(".".join(map(str,item["loc"])) + ": " + item["msg"] for item in error.errors(include_input=False)[:3])


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=500)
    selected: list[str] = Field(default_factory=list, max_length=4)
    other: str | None = Field(default=None, max_length=500)


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: uuid.UUID
    answers: list[Answer] = Field(min_length=1, max_length=3)


class PendingQuestion(Base):
    __tablename__ = "agent_pending_questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    questions: Mapped[dict] = mapped_column(JSONB)
    answer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def validate_answers(questions, answers):
    if len(questions) != len(answers): raise HTTPException(422, "Answer every question")
    for q, a in zip(questions, answers):
        options = {o["label"] for o in q["options"]}
        if a.question != q["question"] or not set(a.selected) <= options or len(a.selected) != len(set(a.selected)):
            raise HTTPException(422, "Invalid question or option")
        if (not q.get("multi_select") and len(a.selected) > 1) or not (a.selected or (a.other or "").strip()):
            raise HTTPException(422, "Choose an option or enter an answer")


async def answer_question(run_id: uuid.UUID, body: Answers, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as db:
        row = (await db.execute(select(PendingQuestion).where(PendingQuestion.id == body.question_id, PendingQuestion.run_id == run_id, PendingQuestion.tenant_id == ctx.tenant_id).with_for_update())).scalar_one_or_none()
        if not row: raise HTTPException(404, "Question not found")
        if row.user_id != ctx.user_id: raise HTTPException(403, "Only the run owner can answer")
        if row.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc) or row.status in {"expired", "cancelled"}: raise HTTPException(404, "Question expired or cancelled")
        if row.status != "pending": raise HTTPException(409, "Question already answered")
        validate_answers(row.questions["questions"], body.answers)
        row.answer = body.model_dump(mode="json")
        row.status = "answered"
        return {"ok": True}


async def ask(tool_input):
    body = Questions.model_validate(tool_input)
    steps = current.get()
    if not steps or not steps.user_id: return {"success": False, "error": "Interactive questions require a live chat. Ask the user in your response."}
    # Persist exactly what the public event displays, so redacted option labels
    # and question text can still be validated when another worker answers.
    body = Questions.model_validate(steps.sanitize(body.model_dump()))
    qid, expires = uuid.uuid4(), datetime.now(timezone.utc) + timedelta(minutes=30)
    async with session_scope() as db:
        db.add(PendingQuestion(id=qid, run_id=steps.run_id, tenant_id=steps.tenant_id, user_id=steps.user_id, questions=body.model_dump(), expires_at=expires, status="pending"))
    steps.emit("omnidome.question", {"run_id": str(steps.run_id), "question_id": str(qid), **body.model_dump(), "expires_at": expires.isoformat(), "ttl_seconds": 1800})
    status = "cancelled"
    try:
        while datetime.now(timezone.utc) < expires:
            async with session_scope() as db:
                row = (await db.execute(select(PendingQuestion).where(PendingQuestion.id == qid))).scalar_one()
                if row.status == "answered":
                    status = "answered"
                    return {"success": True, "answers": row.answer["answers"]}
            await asyncio.sleep(1)
        status = "expired"
        return {"success": False, "error": "The question expired without an answer. Do not assume an answer or approval."}
    finally:
        async with session_scope() as db:
            row = (await db.execute(select(PendingQuestion).where(PendingQuestion.id == qid))).scalar_one_or_none()
            if row and row.status == "pending": row.status = status
        steps.emit("omnidome.question_resolved", {"run_id": str(steps.run_id), "question_id": str(qid), "status": status})
