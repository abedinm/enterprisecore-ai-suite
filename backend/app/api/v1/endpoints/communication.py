"""Communication & collaboration endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.communication import (
    Announcement, CalendarEvent, Feedback, Message, MessageThread, Poll,
    PollOption, PollVote, SharedNote, WikiPage,
)
from app.models.user import User, UserRole
from app.schemas.communication import (
    AnnouncementIn, AnnouncementOut, CalendarEventIn, CalendarEventOut,
    FeedbackIn, FeedbackOut, MessageIn, MessageOut, MessageThreadIn,
    MessageThreadOut, PollIn, PollOut, PollVoteIn, SharedNoteIn, SharedNoteOut,
    WikiPageIn, WikiPageOut,
)

router = APIRouter()


# ---- Messaging ----------------------------------------------------------
@router.get("/threads", response_model=list[MessageThreadOut])
def list_threads(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(MessageThread).order_by(MessageThread.created_at.desc()).limit(200)).all()


@router.post("/threads", response_model=MessageThreadOut)
def create_thread(payload: MessageThreadIn, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    obj = MessageThread(title=payload.title)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/threads/{tid}/messages", response_model=list[MessageOut])
def list_messages(tid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(
        select(Message).where(Message.thread_id == tid).order_by(Message.created_at)
    ).all()


@router.post("/threads/{tid}/messages", response_model=MessageOut)
def send_message(tid: str, payload: MessageIn, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    msg = Message(thread_id=tid, sender_id=current.id, body=payload.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ---- Announcements ------------------------------------------------------
@router.get("/announcements", response_model=list[AnnouncementOut])
def list_announcements(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Announcement).order_by(Announcement.created_at.desc()).limit(100)).all()


@router.post("/announcements", response_model=AnnouncementOut)
def create_announcement(payload: AnnouncementIn, db: Session = Depends(get_db),
                        _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = Announcement(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Calendar / Meetings ------------------------------------------------
@router.get("/calendar", response_model=list[CalendarEventOut])
def list_calendar(start: datetime | None = None, end: datetime | None = None,
                  db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(CalendarEvent).order_by(CalendarEvent.starts_at)
    if start:
        stmt = stmt.where(CalendarEvent.starts_at >= start)
    if end:
        stmt = stmt.where(CalendarEvent.starts_at <= end)
    return db.scalars(stmt.limit(500)).all()


@router.post("/calendar", response_model=CalendarEventOut)
def create_event(payload: CalendarEventIn, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    data = payload.model_dump()
    # `attendees` is JSON-stored as string for portability
    data["attendees"] = "[" + ",".join(f'"{a}"' for a in data.get("attendees", [])) + "]" if "attendees" in data else "[]"
    # Drop attendees if model doesn't have it directly
    data.pop("attendees", None)
    obj = CalendarEvent(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Notes --------------------------------------------------------------
@router.get("/notes", response_model=list[SharedNoteOut])
def list_notes(q: str | None = None, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    stmt = select(SharedNote).order_by(SharedNote.updated_at.desc())
    if q:
        stmt = stmt.where(or_(SharedNote.title.ilike(f"%{q}%"), SharedNote.body.ilike(f"%{q}%")))
    return db.scalars(stmt.limit(500)).all()


@router.post("/notes", response_model=SharedNoteOut)
def create_note(payload: SharedNoteIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    obj = SharedNote(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/notes/{nid}", response_model=SharedNoteOut)
def update_note(nid: str, payload: SharedNoteIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    obj = db.get(SharedNote, nid)
    if not obj:
        raise NotFoundError("Note not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Polls --------------------------------------------------------------
@router.get("/polls", response_model=list[PollOut])
def list_polls(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    polls = db.scalars(select(Poll).order_by(Poll.created_at.desc()).limit(100)).all()
    out = []
    for p in polls:
        options = db.scalars(select(PollOption).where(PollOption.poll_id == p.id)).all()
        option_blobs = []
        total = 0
        for opt in options:
            votes = db.scalar(select(__import__("sqlalchemy").func.count(PollVote.id)).where(PollVote.option_id == opt.id)) or 0
            option_blobs.append({"id": opt.id, "label": opt.label, "votes": int(votes)})
            total += int(votes)
        out.append(PollOut(id=p.id, question=p.question, multi_choice=getattr(p, "multi_choice", False),
                           closes_at=getattr(p, "closes_at", None), options=option_blobs, total_votes=total))
    return out


@router.post("/polls", response_model=PollOut)
def create_poll(payload: PollIn, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    poll = Poll(question=payload.question)
    if hasattr(poll, "multi_choice"):
        poll.multi_choice = payload.multi_choice
    if hasattr(poll, "closes_at"):
        poll.closes_at = payload.closes_at
    db.add(poll)
    db.flush()
    options = []
    for label in payload.options:
        opt = PollOption(poll_id=poll.id, label=label)
        db.add(opt)
        options.append(opt)
    db.commit()
    db.refresh(poll)
    return PollOut(id=poll.id, question=poll.question, multi_choice=payload.multi_choice,
                   closes_at=payload.closes_at,
                   options=[{"id": o.id, "label": o.label, "votes": 0} for o in options],
                   total_votes=0)


@router.post("/polls/vote", status_code=204)
def vote(payload: PollVoteIn, db: Session = Depends(get_db),
         current: User = Depends(get_current_user)):
    for opt_id in payload.option_ids:
        db.add(PollVote(option_id=opt_id, voter_id=current.id))
    db.commit()
    return None


# ---- Feedback -----------------------------------------------------------
@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()


@router.post("/feedback", response_model=FeedbackOut)
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    obj = Feedback(**payload.model_dump())
    if hasattr(obj, "submitter_id"):
        obj.submitter_id = current.id
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Wiki ---------------------------------------------------------------
@router.get("/wiki", response_model=list[WikiPageOut])
def list_wiki(q: str | None = None, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    stmt = select(WikiPage).order_by(WikiPage.title)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WikiPage.title.ilike(like), WikiPage.body.ilike(like)))
    return db.scalars(stmt.limit(500)).all()


@router.post("/wiki", response_model=WikiPageOut)
def create_wiki_page(payload: WikiPageIn, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    obj = WikiPage(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/wiki/{wid}", response_model=WikiPageOut)
def update_wiki_page(wid: str, payload: WikiPageIn, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    obj = db.get(WikiPage, wid)
    if not obj:
        raise NotFoundError("Page not found")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj
