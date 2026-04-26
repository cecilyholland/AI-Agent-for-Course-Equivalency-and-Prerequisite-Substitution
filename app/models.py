import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Text, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import JSONB


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
    review_cycle = Column(Integer, nullable=False, server_default=text("1"))

    assigned_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("reviewers.reviewer_id", ondelete="SET NULL"))

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
    expires_at = Column(DateTime(timezone=True))

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
    fact_json = Column(JSONB)  

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

    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("reviewers.reviewer_id", ondelete="RESTRICT"), nullable=False)
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

class Transcript(Base):
    __tablename__ = "transcripts"

    transcript_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)
    course_code = Column(Text, nullable=False)
    grade = Column(Text, nullable=False)
    term_taken = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class CommitteeAssignment(Base):
    __tablename__ = "case_committee"

    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), primary_key=True)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("reviewers.reviewer_id", ondelete="CASCADE"), primary_key=True)
    review_cycle = Column(Integer, nullable=False, server_default=text("1"), primary_key=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class CommitteeVote(Base):
    __tablename__ = "committee_votes"

    vote_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("requests.request_id", ondelete="CASCADE"), nullable=False)
    review_cycle = Column(Integer, nullable=False, server_default=text("1"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    voter_id = Column(UUID(as_uuid=True), ForeignKey("reviewers.reviewer_id", ondelete="RESTRICT"), nullable=False)
    action = Column(Text, nullable=False)
    comment = Column(Text, nullable=False, server_default=text("''"))
    __table_args__ = (
        {"implicit_returning": True},
    )


class Reviewer(Base):
    __tablename__ = "reviewers"

    reviewer_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    reviewer_name = Column(Text)
    utc_id = Column(String, nullable=False, unique=True)
    password_hash = Column(Text)
    role = Column(Text, nullable=False, server_default=text("'reviewer'"))
    expires_at = Column(DateTime(timezone=True))
    is_deleted = Column(Boolean, nullable=False, server_default=text("FALSE"))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class Course(Base):
    __tablename__ = "courses"

    course_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    course_code = Column(Text, nullable=False, unique=True)
    display_name = Column(Text, nullable=False)
    department = Column(Text, nullable=False)
    credits = Column(Integer, nullable=False)
    lab_required = Column(Boolean, nullable=False, server_default=text("FALSE"))
    prerequisites = Column(Text)
    required_topics = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    required_outcomes = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
