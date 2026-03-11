import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, Text, Integer, Boolean, Date, DateTime, ForeignKey, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'paused', 'complete')", name="ck_campaigns_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    issue_brief = Column(Text, nullable=False)
    tone_instructions = Column(Text, nullable=True)
    stakeholders = Column(JSONB, nullable=False, default=list)
    emails_per_day = Column(Integer, default=10)
    status = Column(Text, default="draft")
    start_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    constituents = relationship("Constituent", back_populates="campaign", cascade="all, delete-orphan")
    sends = relationship("Send", back_populates="campaign", cascade="all, delete-orphan")


class Constituent(Base):
    __tablename__ = "constituents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    city = Column(Text, nullable=False)
    postal_code = Column(Text, nullable=False)
    riding = Column(Text, nullable=True)
    personal_concern = Column(Text, nullable=True)
    consent_given = Column(Boolean, default=False)
    consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    opted_full_name = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="constituents")
    sends = relationship("Send", back_populates="constituent", cascade="all, delete-orphan")


class Send(Base):
    __tablename__ = "sends"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'scheduled', 'generating', 'sent', 'bounced', 'replied', 'failed')",
            name="ck_sends_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    constituent_id = Column(UUID(as_uuid=True), ForeignKey("constituents.id", ondelete="CASCADE"), nullable=False)
    recipient_name = Column(Text, nullable=False)
    recipient_email = Column(Text, nullable=False)
    from_address = Column(Text, nullable=False)
    from_display_name = Column(Text, nullable=False)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    status = Column(Text, default="pending")
    mailgun_message_id = Column(Text, nullable=True)
    scheduled_for = Column(Date, nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="sends")
    constituent = relationship("Constituent", back_populates="sends")
    replies = relationship("Reply", back_populates="send", cascade="all, delete-orphan")


class Reply(Base):
    __tablename__ = "replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    send_id = Column(UUID(as_uuid=True), ForeignKey("sends.id", ondelete="CASCADE"), nullable=False)
    from_email = Column(Text, nullable=False)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    send = relationship("Send", back_populates="replies")
