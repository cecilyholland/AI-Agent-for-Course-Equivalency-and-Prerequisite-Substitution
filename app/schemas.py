# schemas.py

from datetime import datetime
from typing import Optional, List, Dict, Literal, Any
from pydantic import BaseModel


class CaseOut(BaseModel):
    caseId: str
    studentId: str
    studentName: Optional[str]
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


class ReviewIn(BaseModel):
    action: Literal["APPROVE", "DENY", "REQUEST_INFO"]
    comment: str
    reviewerId: str



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