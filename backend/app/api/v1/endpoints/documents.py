"""Document management endpoints — editor, versions, PDF, e-sign, templates, sharing."""
from __future__ import annotations

import hashlib
import io
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.documents import (
    Document, DocumentShare, DocumentTag, DocumentTemplate, DocumentVersion, ESignature,
)
from app.models.user import User, UserRole
from app.schemas.documents import (
    BulkRenameIn, BulkRenameOut, DocumentIn, DocumentOut, DocumentShareIn,
    DocumentShareOut, DocumentTagIn, DocumentTagOut, DocumentTemplateIn,
    DocumentTemplateOut, DocumentVersionOut, ESignatureIn, ESignatureOut,
)

router = APIRouter()


# ---- Documents (editor) -------------------------------------------------
@router.get("", response_model=list[DocumentOut])
def list_documents(q: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Document).order_by(Document.updated_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Document.title.ilike(like), Document.content.ilike(like)))
    return db.scalars(stmt.limit(500)).all()


@router.post("", response_model=DocumentOut)
def create_document(payload: DocumentIn, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    doc = Document(**payload.model_dump(), owner_id=current.id)
    db.add(doc)
    db.flush()
    db.add(DocumentVersion(document_id=doc.id, version_number=1, content=doc.content, author_id=current.id))
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{did}", response_model=DocumentOut)
def get_document(did: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(Document, did)
    if not doc:
        raise NotFoundError("Document not found")
    return doc


@router.patch("/{did}", response_model=DocumentOut)
def update_document(did: str, payload: DocumentIn, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    doc = db.get(Document, did)
    if not doc:
        raise NotFoundError("Document not found")
    # Snapshot prior version if content changed
    if doc.content != payload.content:
        next_v = (db.scalar(
            select(DocumentVersion.version_number).where(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc()).limit(1)
        ) or 0) + 1
        db.add(DocumentVersion(document_id=doc.id, version_number=next_v,
                               content=doc.content, author_id=current.id))
    for k, v in payload.model_dump().items():
        setattr(doc, k, v)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{did}", status_code=204)
def delete_document(did: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    doc = db.get(Document, did)
    if doc:
        db.delete(doc)
        db.commit()


# ---- Versioning ---------------------------------------------------------
@router.get("/{did}/versions", response_model=list[DocumentVersionOut])
def list_versions(did: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == did)
        .order_by(DocumentVersion.version_number.desc())
    ).all()


@router.post("/{did}/versions/{version_number}/restore", response_model=DocumentOut)
def restore_version(did: str, version_number: int, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    doc = db.get(Document, did)
    if not doc:
        raise NotFoundError("Document not found")
    ver = db.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == did,
                                       DocumentVersion.version_number == version_number)
    )
    if not ver:
        raise NotFoundError("Version not found")
    doc.content = ver.content
    db.commit()
    db.refresh(doc)
    return doc


# ---- PDF export ---------------------------------------------------------
@router.get("/{did}/pdf")
def export_pdf(did: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.get(Document, did)
    if not doc:
        raise NotFoundError("Document not found")
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(doc.title, styles["Title"]), Spacer(1, 12)]
    # Treat newlines as paragraph separators
    for para in (doc.content or "").split("\n\n"):
        story.append(Paragraph(para.replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 6))
    pdf.build(story)
    return Response(
        content=buf.getvalue(), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}.pdf"'},
    )


# ---- Tags ---------------------------------------------------------------
@router.get("/{did}/tags", response_model=list[DocumentTagOut])
def list_tags(did: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(DocumentTag).where(DocumentTag.document_id == did)).all()


@router.post("/tags", response_model=DocumentTagOut)
def add_tag(payload: DocumentTagIn, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    obj = DocumentTag(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---- Sharing ------------------------------------------------------------
@router.get("/{did}/shares", response_model=list[DocumentShareOut])
def list_shares(did: str, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    return db.scalars(select(DocumentShare).where(DocumentShare.document_id == did)).all()


@router.post("/shares", response_model=DocumentShareOut)
def add_share(payload: DocumentShareIn, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    obj = DocumentShare(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/shares/{sid}", status_code=204)
def remove_share(sid: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    obj = db.get(DocumentShare, sid)
    if obj:
        db.delete(obj)
        db.commit()


# ---- E-Signature --------------------------------------------------------
@router.post("/signatures", response_model=ESignatureOut)
def sign(payload: ESignatureIn, db: Session = Depends(get_db),
         current: User = Depends(get_current_user)):
    doc = db.get(Document, payload.document_id)
    if not doc:
        raise NotFoundError("Document not found")
    # Compute hash of (content + signer + timestamp) to bind the signature to the document state
    h = hashlib.sha256()
    h.update((doc.content or "").encode())
    h.update(payload.signer_name.encode())
    h.update(payload.signer_email.encode() if payload.signer_email else b"")
    h.update(date.today().isoformat().encode())
    sig = ESignature(
        document_id=payload.document_id,
        signer_name=payload.signer_name,
        signer_email=payload.signer_email,
        signature_hash=h.hexdigest(),
        is_verified=True,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig


@router.get("/{did}/signatures", response_model=list[ESignatureOut])
def list_signatures(did: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(ESignature).where(ESignature.document_id == did)).all()


# ---- Templates ----------------------------------------------------------
@router.get("/templates", response_model=list[DocumentTemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(DocumentTemplate).order_by(DocumentTemplate.name)).all()


@router.post("/templates", response_model=DocumentTemplateOut)
def create_template(payload: DocumentTemplateIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = DocumentTemplate(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/templates/{tid}/instantiate", response_model=DocumentOut)
def instantiate_template(tid: str, payload: dict, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    tpl = db.get(DocumentTemplate, tid)
    if not tpl:
        raise NotFoundError("Template not found")
    # Simple {{var}} substitution
    body = tpl.body or ""
    for k, v in (payload.get("variables") or {}).items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    doc = Document(title=payload.get("title", tpl.name), content=body, owner_id=current.id, visibility="private")
    db.add(doc)
    db.flush()
    db.add(DocumentVersion(document_id=doc.id, version_number=1, content=doc.content, author_id=current.id))
    db.commit()
    db.refresh(doc)
    return doc


# ---- Bulk rename --------------------------------------------------------
@router.post("/bulk-rename", response_model=BulkRenameOut)
def bulk_rename(payload: BulkRenameIn, db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    renamed = 0
    titles: dict[str, str] = {}
    for did in payload.document_ids:
        doc = db.get(Document, did)
        if not doc:
            continue
        new_title = doc.title
        if payload.replace:
            for old, new in payload.replace.items():
                new_title = new_title.replace(old, new)
        if payload.prefix:
            new_title = payload.prefix + new_title
        if payload.suffix:
            new_title = new_title + payload.suffix
        doc.title = new_title
        titles[did] = new_title
        renamed += 1
    db.commit()
    return BulkRenameOut(renamed=renamed, new_titles=titles)
