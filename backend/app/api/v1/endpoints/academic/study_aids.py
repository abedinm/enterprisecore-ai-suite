"""Study aids — student-owned AI-generated study notes (summary + cards + MCQs).

The ``generate`` endpoint is the AI-Brain-powered hook for this phase: it
shells out to ``app.services.ai.smart_json`` to summarise the input and
manufacture flashcards/MCQs in one round-trip, then persists the result on
the student's StudyNote row.

Workflow features layered on top of the CRUD scaffold:
- ``POST /study-aids/notes/{id}/regenerate`` — re-runs generation with an
  optional "make it better" hint and overwrites the existing summary/cards/
  MCQs in place.
- ``GET /study-aids/notes/{id}/quiz`` — returns the note's MCQs in a quiz
  shape, with the answer key separated so the UI can render questions
  without leaking answers in the DOM.
- ``POST /study-aids/notes/{id}/quiz/attempts`` — records a scored attempt.
- ``GET /study-aids/students/me/quiz-history`` — quiz attempts the student
  has logged, newest first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import _apply_update, _get_or_404
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.academic.study_aids import (
    AcademicStudyNote, AcademicStudyQuizAttempt,
)
from app.models.user import User
from app.schemas.academic.study_aids import (
    QuizAttemptIn, QuizAttemptOut, QuizOut, QuizQuestion, StudyAidGenerateIn,
    StudyAidRegenerateIn, StudyNoteCreate, StudyNoteOut, StudyNoteUpdate,
)
from app.services import ai as ai_svc

router = APIRouter()


@router.get("/notes", response_model=list[StudyNoteOut])
def list_notes(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return db.scalars(
        select(AcademicStudyNote)
        .where(AcademicStudyNote.student_id == current.id)
        .order_by(AcademicStudyNote.created_at.desc())
    ).all()


@router.post(
    "/notes",
    response_model=StudyNoteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    payload: StudyNoteCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = AcademicStudyNote(
        student_id=current.id,
        source_text=payload.source_text,
        source_type=payload.source_type,
        summary="",
        flashcards=[],
        mcqs=[],
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Quiz history (declared BEFORE /notes/{note_id} so it isn't captured).
# ---------------------------------------------------------------------------
@router.get(
    "/students/me/quiz-history",
    response_model=list[QuizAttemptOut],
)
def my_quiz_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return db.scalars(
        select(AcademicStudyQuizAttempt)
        .where(AcademicStudyQuizAttempt.student_id == current.id)
        .order_by(AcademicStudyQuizAttempt.taken_at.desc())
    ).all()


@router.get("/notes/{note_id}", response_model=StudyNoteOut)
def get_note(
    note_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    return obj


@router.patch("/notes/{note_id}", response_model=StudyNoteOut)
def update_note(
    note_id: str, payload: StudyNoteUpdate, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT,
)
def delete_note(
    note_id: str, db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# AI-powered generation
# ---------------------------------------------------------------------------
_GENERATE_PROMPT = (
    "You are a study assistant. Given the source text below, produce strict "
    "JSON with this shape:\n"
    '{\n'
    '  "summary": "<3-6 sentence summary>",\n'
    '  "flashcards": [{"front": "...", "back": "..."}, ...],\n'
    '  "mcqs": [{"question": "...", "options": ["a","b","c","d"], "answer_index": 0}, ...]\n'
    "}\n"
    "Aim for 5-8 flashcards and 3-5 MCQs. Reply with JSON only.\n\n"
    "SOURCE:\n{source}"
)

_REGENERATE_HINT_DEFAULT = (
    "Improve clarity and add an extra example where it helps."
)


def _coerce_list(value, key: str) -> list:
    if isinstance(value, list):
        return value
    return []


def _build_generate_prompt(source: str, *, hint: str | None = None) -> str:
    prompt = _GENERATE_PROMPT.replace("{source}", source)
    if hint:
        prompt = f"{prompt}\n\nADDITIONAL HINT:\n{hint}"
    return prompt


def _apply_generation(
    note: AcademicStudyNote, data: dict,
) -> None:
    """Mutate ``note`` with the AI gateway result (or its ``_raw`` fallback)."""
    if "_raw" in data:
        note.summary = str(data.get("_raw", ""))
        note.flashcards = []
        note.mcqs = []
    else:
        note.summary = str(data.get("summary", ""))
        note.flashcards = _coerce_list(data.get("flashcards"), "flashcards")
        note.mcqs = _coerce_list(data.get("mcqs"), "mcqs")


@router.post(
    "/notes/generate",
    response_model=StudyNoteOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_note(
    payload: StudyAidGenerateIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """One-shot: call the AI gateway, persist the produced summary + cards +
    MCQs onto a fresh StudyNote owned by the current student."""
    data = ai_svc.smart_json(
        _build_generate_prompt(payload.source_text),
        feature="study_aids",
        provider=payload.provider,
        db=db,
        user_id=current.id,
        max_tokens=1400,
        system="You build concise study aids in strict JSON.",
    )
    obj = AcademicStudyNote(
        student_id=current.id,
        source_text=payload.source_text,
        source_type=payload.source_type,
        summary="",
        flashcards=[],
        mcqs=[],
    )
    _apply_generation(obj, data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post(
    "/notes/{note_id}/regenerate",
    response_model=StudyNoteOut,
)
def regenerate_note(
    note_id: str,
    payload: StudyAidRegenerateIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Re-runs generation against the same source text and overwrites the
    existing summary/flashcards/MCQs. Useful when the first attempt was
    weak or the student wants a different angle (supplied via ``hint``).
    """
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    hint = payload.hint.strip() or _REGENERATE_HINT_DEFAULT
    data = ai_svc.smart_json(
        _build_generate_prompt(obj.source_text, hint=hint),
        feature="study_aids",
        provider=payload.provider,
        db=db,
        user_id=current.id,
        max_tokens=1400,
        system="You rebuild concise study aids in strict JSON.",
    )
    _apply_generation(obj, data)
    db.commit()
    db.refresh(obj)
    return obj


# ---------------------------------------------------------------------------
# Quiz mode
# ---------------------------------------------------------------------------
@router.get(
    "/notes/{note_id}/quiz",
    response_model=QuizOut,
)
def note_quiz(
    note_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Return the note's MCQs in a quiz-friendly shape.

    Questions go on one side (no answer index leaks), the answer key on the
    other so the UI can keep the correct answers out of the rendered DOM
    until the student submits.
    """
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    questions: list[QuizQuestion] = []
    answer_key: dict[int, int] = {}
    for idx, raw in enumerate(obj.mcqs or []):
        if not isinstance(raw, dict):
            continue
        opts = raw.get("options") or []
        if not isinstance(opts, list):
            opts = []
        questions.append(
            QuizQuestion(
                index=idx,
                question=str(raw.get("question", "")),
                options=[str(o) for o in opts],
            )
        )
        try:
            answer_key[idx] = int(raw.get("answer_index", 0))
        except (TypeError, ValueError):
            answer_key[idx] = 0
    return QuizOut(
        note_id=obj.id, questions=questions, answer_key=answer_key,
    )


@router.post(
    "/notes/{note_id}/quiz/attempts",
    response_model=QuizAttemptOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_quiz_attempt(
    note_id: str,
    payload: QuizAttemptIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Score the answers against the note's MCQ key and persist the result."""
    obj = _get_or_404(db, AcademicStudyNote, note_id, "Study note")
    if obj.student_id != current.id:
        raise NotFoundError("Study note not found")
    mcqs = obj.mcqs or []
    total = len(mcqs)
    score = 0
    for idx_str, chosen in payload.answers.items():
        try:
            idx = int(idx_str)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < total and isinstance(mcqs[idx], dict):
            try:
                correct = int(mcqs[idx].get("answer_index", -1))
            except (TypeError, ValueError):
                continue
            if correct == int(chosen):
                score += 1
    attempt = AcademicStudyQuizAttempt(
        note_id=obj.id,
        student_id=current.id,
        score=score,
        total=total,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt
