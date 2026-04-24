from datetime import datetime
from typing import Optional, List, Dict, Literal, Any
from pydantic import BaseModel, Field
from uuid import UUID

class ReviewIn(BaseModel):
    action: Literal["APPROVE", "DENY", "REQUEST_INFO", "NEEDS_MORE_INFO", "APPROVE_WITH_BRIDGE"]
    comment: str = ""
    reviewerId: UUID

class ReviewerCreateIn(BaseModel):
    reviewerName: Optional[str] = None
    utcId: str
    password: Optional[str] = None
    role: Literal["reviewer", "admin", "committee"] = "reviewer"

class ReviewerOut(BaseModel):
    reviewerId: str
    reviewerName: Optional[str]
    utcId: str
    role: str
    expiresAt: Optional[datetime] = None
    isDeleted: bool
    createdAt: datetime

class CaseOut(BaseModel):
    caseId: str
    studentId: str
    studentName: Optional[str]
    assignedReviewerId: str | None = None
    courseRequested: Optional[str]
    status: str
    createdAt: datetime
    updatedAt: datetime


class DocumentOut(BaseModel):
    docId: str
    filename: str
    sha256: str
    storageUri: str
    createdAt: datetime
    isActive: bool
    expiresAt: Optional[datetime] = None


class CaseDetailOut(BaseModel):
    case: CaseOut
    documents: List[DocumentOut]
    evidencePacket: Dict[str, Any]
    decisionResult: Optional[Dict[str, Any]] = None
    auditLog: Dict[str, Any]

class ExtractionStartDocOut(BaseModel):
    docId: str
    filename: str
    sha256: str
    storageUri: str

class ExtractionStartOut(BaseModel):
    extractionRunId: str
    caseId: str
    status: str
    documents: List[ExtractionStartDocOut]

class ExtractionFactIn(BaseModel):
    factType: str
    factKey: Optional[str] = None
    factValue: Optional[str] = None
    factJson: Optional[Dict[str, Any]] = None
    unknown: bool = False

class ExtractionCompleteIn(BaseModel):
    extractionRunId: str
    facts: List[ExtractionFactIn]

class DecisionResultIn(BaseModel):
    decisionRunId: str
    resultJson: Dict[str, Any]
    needsMoreInfo: bool = False
    missingFields: Optional[Dict[str, Any]] = None


class CommitteeVoteIn(BaseModel):
    reviewerId: UUID
    action: Literal["approve", "deny", "needs_more_info", "approve_with_bridge"]
    comment: str = ""


class CommitteeMemberOut(BaseModel):
    reviewerId: str
    reviewerName: Optional[str]
    hasVoted: bool


class CommitteeInfoOut(BaseModel):
    members: List[CommitteeMemberOut]
    myVote: Optional[Dict[str, Any]] = None
    finalDecision: Optional[str] = None


class CourseIn(BaseModel):
    courseCode: str
    displayName: str
    department: str
    credits: int
    labRequired: bool = False
    prerequisites: Optional[str] = None
    requiredTopics: List[str] = []
    requiredOutcomes: List[str] = []
    description: Optional[str] = None


class CourseOut(BaseModel):
    courseId: str
    courseCode: str
    displayName: str
    department: str
    credits: int
    labRequired: bool
    prerequisites: Optional[str]
    requiredTopics: List[str]
    requiredOutcomes: List[str]
    description: Optional[str]
    createdAt: datetime
    updatedAt: datetime


class CourseUpdateIn(BaseModel):
    displayName: Optional[str] = None
    department: Optional[str] = None
    credits: Optional[int] = None
    labRequired: Optional[bool] = None
    prerequisites: Optional[str] = None
    requiredTopics: Optional[List[str]] = None
    requiredOutcomes: Optional[List[str]] = None
    description: Optional[str] = None


class LoginIn(BaseModel):
    utcId: str
    password: str


class LoginOut(BaseModel):
    reviewerId: str
    reviewerName: Optional[str]
    utcId: str
    role: str


class PolicyOut(BaseModel):
    # Score band thresholds (0-100)
    approveThreshold: int
    bridgeThreshold: int
    needsInfoThreshold: int
    # Behavior toggles
    requireLabParity: bool
    requireCreditsKnown: bool
    requireTopicsOrOutcomes: bool
    # Configurable rules
    minGrade: Optional[str] = None
    minContactHours: int = 0
    maxCourseAgeYears: int = 0
    mustIncludeTopics: List[str] = []


class PolicyUpdateIn(BaseModel):
    approveThreshold: Optional[int] = None
    bridgeThreshold: Optional[int] = None
    needsInfoThreshold: Optional[int] = None
    requireLabParity: Optional[bool] = None
    requireCreditsKnown: Optional[bool] = None
    requireTopicsOrOutcomes: Optional[bool] = None
    minGrade: Optional[str] = None
    minContactHours: Optional[int] = None
    maxCourseAgeYears: Optional[int] = None
    mustIncludeTopics: Optional[List[str]] = None