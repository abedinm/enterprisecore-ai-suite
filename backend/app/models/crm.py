from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UniqueConstraint

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Contact(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    company: Mapped[str | None] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(80))
    tags: Mapped[str] = mapped_column(Text, default="[]")


class Lead(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    source: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(60), default="new", index=True)
    score: Mapped[int] = mapped_column(default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class Deal(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), index=True)
    stage: Mapped[str] = mapped_column(String(80), default="qualified", index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    probability: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    expected_close_date: Mapped[date | None] = mapped_column(Date)


class FollowUp(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    notes: Mapped[str] = mapped_column(Text, default="")


class CommunicationEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str | None] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, default="")


class Contract(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    file_path: Mapped[str | None] = mapped_column(String(500))


class Proposal(IdMixin, TenantMixin, TimestampMixin, Base):
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    body: Mapped[str] = mapped_column(Text, default="")


class Quotation(IdMixin, TenantMixin, TimestampMixin, Base):
    quote_number: Mapped[str] = mapped_column(String(60), index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    __table_args__ = (UniqueConstraint("tenant_id", "quote_number", name="uq_quotations_tenant_number"),)


class EmailCampaign(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    sent_count: Mapped[int] = mapped_column(default=0)
    open_count: Mapped[int] = mapped_column(default=0)
    click_count: Mapped[int] = mapped_column(default=0)


class CustomerSegment(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(160))
    rules: Mapped[str] = mapped_column(Text, default="{}")
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_customer_segments_tenant_name"),)
