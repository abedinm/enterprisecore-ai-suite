"""Schemas for study aids (AI-generated summary + flashcards + MCQs)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


SourceType = Literal["paste", "upload"]


class StudyNoteCreate(BaseModel):
    source_text: str = Field(min_length=1)
    source_type: SourceType = "paste"


class StudyNoteUpdate(BaseModel):
    summary: str | None = None
    flashcards: list[dict[str, Any]] | None = None
    mcqs: list[dict[str, Any]] | None = None


class StudyNoteOut(ORMModel):
    id: str
    student_id: str
    source_text: str
    summary: str
    flashcards: list[dict[str, Any]]
    mcqs: list[dict[str, Any]]
    source_type: str
    created_at: datetime
    updated_at: datetime


class StudyAidGenerateIn(BaseModel):
    """Payload for the AI-powered generation endpoint.

    The AI call produces summary + flashcards + MCQs from ``source_text`` and
    persists them on the resulting StudyNote so the student can review later.
    """

    source_text: str = Field(min_length=1, max_length=40_000)
    source_type: SourceType = "paste"
    provider: str | None = None  # forwarded to ai.smart_text/json


class StudyAidRegenerateIn(BaseModel):
    """Body for POST /study-aids/notes/{id}/regenerate.

    Optional ``hint`` lets the student steer the regeneration ("make it
    shorter", "more advanced", "add code examples"). Empty means the default
    "improve quality" hint.
    """

    hint: str = ""
    provider: str | None = None


class QuizQuestion(BaseModel):
    """An MCQ stripped of the answer for student-facing rendering."""

    index: int
    question: str
    options: list[str]


class QuizOut(BaseModel):
    """Quiz-ready shape: questions on one side, the answer key on the other.

    The frontend can render the questions list and only check the answer key
    after the student submits — splitting them keeps the answers out of the
    DOM while the quiz is in progress.
    """

    note_id: str
    questions: list[QuizQuestion]
    answer_key: dict[int, int]


class QuizAttemptIn(BaseModel):
    """Body for POST /study-aids/notes/{id}/quiz/attempts.

    Keys in ``answers`` are stringified ints (JSON object key constraint).
    """

    answers: dict[str, int]


class QuizAttemptOut(ORMModel):
    id: str
    note_id: str
    student_id: str
    score: int
    total: int
    taken_at: datetime
    created_at: datetime
