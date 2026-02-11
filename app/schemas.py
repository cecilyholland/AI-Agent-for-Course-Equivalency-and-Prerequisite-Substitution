# schemas.py

from datetime import datetime
from typing import Optional, List, Dict, Any
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
    action: str  # APPROVE | DENY | REQUEST_INFO
    comment: Optional[str]
    reviewerId: Optional[str]


class CaseDetailOut(BaseModel):
    case: CaseOut
    documents: List[DocumentOut]
    decisionPacket: Dict[str, Any]
    auditLog: Dict[str, Any]
