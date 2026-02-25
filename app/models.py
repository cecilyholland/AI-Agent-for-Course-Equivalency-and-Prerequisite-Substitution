import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Text, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import text

from sqlalchemy.dialects.postgresql import UUID, JSONB

Base = declarative_base()


class Request(Base):
    __tablename__ = "requests"

    request_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    student_id = Column(Text, nullable=False)
    student_name = Column(Text)
    course_requested = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    status = Column(Text, nullable=False)

    documents = relationship("Document", back_populates="request", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    doc_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    filename = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    sha256 = Column(Text, nullable=False)
    storage_uri = Column(Text, nullable=False)

    size_bytes = Column(Integer)

    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))

    request = relationship("Request", back_populates="documents")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    extraction_run_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    status = Column(Text, nullable=False)
    error_message = Column(Text)

    manifest_uri = Column(Text)
    manifest_sha256 = Column(Text)


class GroundedEvidence(Base):
    __tablename__ = "grounded_evidence"

    evidence_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)
    extraction_run_id = Column(UUID(as_uuid=True), ForeignKey("extraction_runs.extraction_run_id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    fact_type = Column(Text, nullable=False)
    fact_key = Column(Text)
    fact_value = Column(Text)
    fact_json = Column(JSONB)  # ✅ matches db_schema.sql (JSONB)

    unknown = Column(Boolean, nullable=False, server_default=text("FALSE"))
    notes = Column(Text)


class DecisionRun(Base):
    __tablename__ = "decision_runs"

    decision_run_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    status = Column(Text, nullable=False)
    error_message = Column(Text)

    decision_inputs = Column(JSONB)


class ReviewAction(Base):
    __tablename__ = "review_actions"

    review_action_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    reviewer_id = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    comment = Column(Text, nullable=False)

    decision_run_id = Column(UUID(as_uuid=True), ForeignKey("decision_runs.decision_run_id", ondelete="SET NULL"))

class DecisionResult(Base):
    __tablename__ = "decision_results"

    decision_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("decision_runs.decision_run_id", ondelete="CASCADE"),
        primary_key=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    # matches db_schema.sql: result_json JSONB NOT NULL
    result_json = Column(JSONB, nullable=False)

    # workflow signal from engine
    needs_more_info = Column(Boolean, nullable=False, server_default=text("FALSE"))

    # optional list/structure of fields needed
    missing_fields = Column(JSONB)
