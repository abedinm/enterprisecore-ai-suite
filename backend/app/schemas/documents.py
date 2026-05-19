"""Document-management schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    content: str = ""
    file_path: str | None = None
    visibility: str = "private"


class DocumentOut(ORMModel):
    id: str
    title: str
    content: str
    file_path: str | None
    owner_id: str | None
    visibility: str
    created_at: datetime
    updated_at: datetime


class DocumentVersionOut(ORMModel):
    id: str
    document_id: str
    version_number: int
    content: str
    author_id: str | None
    created_at: datetime


class DocumentTagIn(BaseModel):
    document_id: str
    tag: str


class DocumentTagOut(ORMModel):
    id: str
    document_id: str
    tag: str


class DocumentShareIn(BaseModel):
    document_id: str
    user_id: str | None = None
    permission: str = "read"


class DocumentShareOut(ORMModel):
    id: str
    document_id: str
    user_id: str | None
    permission: str


class ESignatureIn(BaseModel):
    document_id: str
    signer_name: str
    signer_email: str | None = None


class ESignatureOut(ORMModel):
    id: str
    document_id: str
    signer_name: str
    signer_email: str | None
    signature_hash: str
    is_verified: bool


class DocumentTemplateIn(BaseModel):
    name: str
    body: str = ""
    category: str | None = None


class DocumentTemplateOut(ORMModel):
    id: str
    name: str
    body: str
    category: str | None


class BulkRenameIn(BaseModel):
    document_ids: list[str]
    prefix: str | None = None
    suffix: str | None = None
    replace: dict[str, str] | None = None


class BulkRenameOut(BaseModel):
    renamed: int
    new_titles: dict[str, str]
