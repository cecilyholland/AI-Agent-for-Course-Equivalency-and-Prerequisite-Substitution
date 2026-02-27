from datetime import datetime
from typing import Optional, List, Dict, Literal, Any
from pydantic import BaseModel, Field
from uuid import UUID

class ReviewIn(BaseModel):
    action: Literal["APPROVE", "DENY", "REQUEST_INFO", "NEEDS_MORE_INFO"]
    comment: str = Field(min_length=1)
    reviewerId: UUID

class ReviewerCreateIn(BaseModel):
    reviewerName: Optional[str] = None

class ReviewerOut(BaseModel):
    reviewerId: str
    reviewerName: Optional[str]
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