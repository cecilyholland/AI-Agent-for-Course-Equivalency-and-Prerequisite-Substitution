from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, Field


class Decision(str, Enum):
    APPROVE = "APPROVE"
    DENY = "DENY"
    NEEDS_MORE_INFO = "NEEDS_MORE_INFO"
    APPROVE_WITH_BRIDGE = "APPROVE_WITH_BRIDGE"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Citation(BaseModel):
    doc_id: str
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    span: Optional[str] = None
    snippet: Optional[str] = None


class EvidenceField(BaseModel):
    """
    General evidence container:
    - value: the extracted value (list/str/int/bool/etc.)
    - unknown: True if not found/uncertain
    - citations: where the value came from
    """
    value: Optional[Any] = None
    unknown: bool = False
    citations: List[Citation] = Field(default_factory=list)


class CourseEvidence(BaseModel):
    credits: EvidenceField
    contact_hours_lecture: EvidenceField
    contact_hours_lab: EvidenceField
    lab_component: EvidenceField          # expect True/False when known
    topics: EvidenceField                 # expect List[str] when known
    outcomes: EvidenceField               # expect List[str] when known
    assessments: EvidenceField            # expect List[str] when known


class TargetCourseProfile(BaseModel):
    target_credits: int
    target_lab_required: bool
    required_topics: List[str] = Field(default_factory=list)
    required_outcomes: List[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    approve_threshold: int = 80
    bridge_threshold: int = 65

    # hard rules / toggles (can expand later)
    require_lab_parity: bool = True

    # needs-more-info triggers (v1)
    require_credits_known: bool = True
    require_topics_or_outcomes: bool = True


class DecisionInputsPacket(BaseModel):
    """
    Built by backend from stored evidence.
    Decision engine must be a pure function over this packet.
    """
    case_id: str
    source_course: CourseEvidence
    target_course: TargetCourseProfile
    policy: PolicyConfig


class ReasonItem(BaseModel):
    text: str
    citations: List[Citation] = Field(default_factory=list)


class GapItem(BaseModel):
    text: str
    severity: Literal["HARD", "FIXABLE", "INFO_MISSING"]
    citations: List[Citation] = Field(default_factory=list)


class DecisionResult(BaseModel):
    decision: Decision
    equivalency_score: int
    confidence: Confidence
    reasons: List[ReasonItem] = Field(default_factory=list)
    gaps: List[GapItem] = Field(default_factory=list)
    bridge_plan: List[str] = Field(default_factory=list)
    missing_info_requests: List[str] = Field(default_factory=list)


def decide(packet: DecisionInputsPacket) -> DecisionResult:
    """
    Contract:
    - No DB/network/filesystem access
    - Deterministic for same inputs
    - Backend handles orchestration + persistence + versioning
    """
    raise NotImplementedError("Contract-only PR. Logic added in next PR.")
