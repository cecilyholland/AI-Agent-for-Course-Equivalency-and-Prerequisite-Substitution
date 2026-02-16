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


def _norm_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return [str(val).strip()] if str(val).strip() else []


def _contains_required(required: str, candidates: List[str]) -> bool:
    r = required.lower().strip()
    if not r:
        return False
    for c in candidates:
        c2 = c.lower()
        if r in c2 or c2 in r:
            return True
    return False


def _overlap_score(required_items: List[str], found_items: List[str], weight: int):
    """Returns (points, matched_required_items)."""
    if not required_items:
        return weight, []  # nothing required => full credit
    matched = [r for r in required_items if _contains_required(r, found_items)]
    ratio = len(matched) / max(1, len(required_items))
    points = int(round(weight * ratio))
    return points, matched


def decide(packet: DecisionInputsPacket) -> DecisionResult:
    """
    MVP decision engine:
    - deterministic, no IO
    - simple scoring + gap analysis
    """
    policy = packet.policy
    src = packet.source_course
    tgt = packet.target_course

    reasons: List[ReasonItem] = []
    gaps: List[GapItem] = []
    bridge_plan: List[str] = []
    missing_info: List[str] = []

    # Weights (sum to 100)
    W_TOPICS = 40
    W_OUTCOMES = 30
    W_CREDITS = 20
    W_LAB = 10

    score = 0

    # ---------------------------
    # Credits
    # ---------------------------
    credits_unknown = src.credits.unknown or src.credits.value is None
    if credits_unknown:
        if policy.require_credits_known:
            gaps.append(GapItem(
                text="Source course credits are unknown.",
                severity="INFO_MISSING",
                citations=src.credits.citations,
            ))
            missing_info.append("Provide official credit hours for the source course (catalog/syllabus).")
        # no points if unknown
    else:
        try:
            src_credits = int(src.credits.value)
        except Exception:
            src_credits = None

        if src_credits is None:
            gaps.append(GapItem(
                text="Source course credits could not be parsed as a number.",
                severity="INFO_MISSING",
                citations=src.credits.citations,
            ))
            missing_info.append("Provide credits in a clear numeric format.")
        else:
            if src_credits == tgt.target_credits:
                score += W_CREDITS
                reasons.append(ReasonItem(
                    text=f"Credits match ({src_credits} credits).",
                    citations=src.credits.citations,
                ))
            elif abs(src_credits - tgt.target_credits) == 1:
                score += int(W_CREDITS * 0.5)
                gaps.append(GapItem(
                    text=f"Credits are close but not equal (source {src_credits} vs target {tgt.target_credits}).",
                    severity="FIXABLE",
                    citations=src.credits.citations,
                ))
                bridge_plan.append("Complete an additional 1-credit bridge component if required by the department.")
            else:
                gaps.append(GapItem(
                    text=f"Credits do not match (source {src_credits} vs target {tgt.target_credits}).",
                    severity="HARD",
                    citations=src.credits.citations,
                ))

    # ---------------------------
    # Lab parity
    # ---------------------------
    lab_required = tgt.target_lab_required and policy.require_lab_parity
    lab_unknown = src.lab_component.unknown or src.lab_component.value is None

    if lab_required:
        if lab_unknown:
            gaps.append(GapItem(
                text="Target course requires a lab, but source lab information is unknown.",
                severity="INFO_MISSING",
                citations=src.lab_component.citations,
            ))
            missing_info.append("Provide evidence whether the source course includes a lab component (catalog/syllabus).")
        else:
            has_lab = bool(src.lab_component.value)
            if has_lab:
                score += W_LAB
                reasons.append(ReasonItem(
                    text="Lab requirement satisfied (source includes a lab component).",
                    citations=src.lab_component.citations,
                ))
            else:
                gaps.append(GapItem(
                    text="Target course requires a lab, but source course does not show a lab component.",
                    severity="FIXABLE",
                    citations=src.lab_component.citations,
                ))
                bridge_plan.append("Take the target lab (or an approved lab equivalent) as a bridge requirement.")
    else:
        # If lab not required, give full credit for lab component
        score += W_LAB

    # ---------------------------
    # Topics / outcomes overlap
    # ---------------------------
    topics = _norm_list(src.topics.value)
    outcomes = _norm_list(src.outcomes.value)

    topics_unknown = src.topics.unknown or (src.topics.value is None)
    outcomes_unknown = src.outcomes.unknown or (src.outcomes.value is None)

    if policy.require_topics_or_outcomes and (topics_unknown and outcomes_unknown):
        gaps.append(GapItem(
            text="Both topics and learning outcomes are missing/unknown for the source course.",
            severity="INFO_MISSING",
            citations=(src.topics.citations + src.outcomes.citations),
        ))
        missing_info.append("Provide course topics and/or learning outcomes from the syllabus or official catalog.")
    else:
        # Topics score (against required topics)
        pts_t, matched_topics = _overlap_score(tgt.required_topics, topics, W_TOPICS)
        score += pts_t
        if tgt.required_topics:
            if matched_topics:
                reasons.append(ReasonItem(
                    text=f"Matched {len(matched_topics)}/{len(tgt.required_topics)} required topics.",
                    citations=src.topics.citations,
                ))
            else:
                gaps.append(GapItem(
                    text="No required topics were clearly matched.",
                    severity="HARD",
                    citations=src.topics.citations,
                ))
        else:
            reasons.append(ReasonItem(
                text="No required topics specified for target course; topics not used as a strict constraint.",
                citations=[],
            ))

        # Outcomes score (against required outcomes)
        pts_o, matched_outcomes = _overlap_score(tgt.required_outcomes, outcomes, W_OUTCOMES)
        score += pts_o
        if tgt.required_outcomes:
            if matched_outcomes:
                reasons.append(ReasonItem(
                    text=f"Matched {len(matched_outcomes)}/{len(tgt.required_outcomes)} required learning outcomes.",
                    citations=src.outcomes.citations,
                ))
            else:
                gaps.append(GapItem(
                    text="No required learning outcomes were clearly matched.",
                    severity="HARD",
                    citations=src.outcomes.citations,
                ))
        else:
            reasons.append(ReasonItem(
                text="No required learning outcomes specified for target course; outcomes not used as a strict constraint.",
                citations=[],
            ))

    # ---------------------------
    # Decision rules
    # ---------------------------
    has_info_missing = any(g.severity == "INFO_MISSING" for g in gaps)
    has_hard = any(g.severity == "HARD" for g in gaps)

    if has_info_missing:
        decision = Decision.NEEDS_MORE_INFO
    else:
        if score >= policy.approve_threshold and not has_hard:
            decision = Decision.APPROVE
        elif score >= policy.bridge_threshold and not has_hard:
            decision = Decision.APPROVE_WITH_BRIDGE
        elif score >= policy.bridge_threshold and has_hard:
            decision = Decision.DENY
        else:
            decision = Decision.DENY

    # Confidence (simple heuristic)
    unknown_count = sum([
        1 if credits_unknown else 0,
        1 if lab_unknown else 0,
        1 if topics_unknown else 0,
        1 if outcomes_unknown else 0,
    ])
    if decision == Decision.NEEDS_MORE_INFO:
        confidence = Confidence.LOW
    elif unknown_count == 0 and (score >= policy.approve_threshold + 10 or score <= policy.bridge_threshold - 10):
        confidence = Confidence.HIGH
    elif unknown_count <= 1:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    return DecisionResult(
        decision=decision,
        equivalency_score=max(0, min(100, int(score))),
        confidence=confidence,
        reasons=reasons,
        gaps=gaps,
        bridge_plan=bridge_plan,
        missing_info_requests=missing_info,
    )
