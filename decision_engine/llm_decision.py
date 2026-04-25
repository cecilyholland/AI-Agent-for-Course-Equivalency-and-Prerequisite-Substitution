"""
LLM-based decision engine.

Calls OpenAI (GPT) with the extracted evidence, citation chunks, and policy
to produce a structured equivalency decision with citations.

System prompt is loaded from prompts/policy.md (maintained by the Decision Logic
& Policy Engine Lead). Policy config comes from config/policy.yaml.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

import openai
from dotenv import load_dotenv

from decision_engine.contracts import (
    DecisionInputsPacket,
    DecisionResult,
    Decision,
    Confidence,
    ReasonItem,
    GapItem,
    Citation,
)

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

# ---------------------------------------------------------------------------
# Load system prompt from prompts/policy.md
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_PATH = os.path.join(_PROJECT_ROOT, "prompts", "policy.md")


def _load_system_prompt() -> str:
    """Read the policy prompt file. Cached after first call."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _format_evidence_for_prompt(
    evidence_rows: list,
    chunks_by_evidence: dict[str, list[dict]],
) -> str:
    """
    Format grounded evidence + citation chunks into a readable block for the prompt.

    evidence_rows: list of GroundedEvidence ORM objects
    chunks_by_evidence: dict mapping evidence_id -> list of chunk dicts
        each chunk dict has: chunk_uuid, page_num, snippet_text, full_text
    """
    lines = []
    for ev in evidence_rows:
        ev_id = str(ev.evidence_id)
        status = "UNKNOWN" if ev.unknown else "KNOWN"
        value = ev.fact_value or (json.dumps(ev.fact_json) if ev.fact_json else "N/A")

        lines.append(f"- Fact: {ev.fact_key} = {value} [{status}]")
        lines.append(f"  fact_type: {ev.fact_type}")

        chunks = chunks_by_evidence.get(ev_id, [])
        if chunks:
            for ch in chunks:
                chunk_id = str(ch["chunk_uuid"])
                page = ch.get("page_num", "?")
                snippet = ch.get("snippet_text") or ch.get("full_text") or "(no text)"
                # Truncate very long snippets
                if len(snippet) > 500:
                    snippet = snippet[:500] + "..."
                lines.append(f"    [chunk_id: {chunk_id}, page: {page}]")
                lines.append(f"    \"{snippet}\"")
        else:
            lines.append(f"    (no citation chunks linked)")

        lines.append("")

    return "\n".join(lines)


def _format_target_for_prompt(packet: DecisionInputsPacket) -> str:
    """Format the target course profile for the prompt."""
    tgt = packet.target_course
    policy = packet.policy

    lines = [
        f"Target Credits: {tgt.target_credits}",
        f"Lab Required: {tgt.target_lab_required}",
        f"Required Topics: {tgt.required_topics if tgt.required_topics else 'None specified'}",
        f"Required Outcomes: {tgt.required_outcomes if tgt.required_outcomes else 'None specified'}",
        "",
        "Policy Thresholds:",
        f"  Approve threshold: {policy.approve_threshold}",
        f"  Bridge threshold: {policy.bridge_threshold}",
        f"  Require lab parity: {policy.require_lab_parity}",
        f"  Require credits known: {policy.require_credits_known}",
        f"  Require topics or outcomes: {policy.require_topics_or_outcomes}",
    ]

    # Configurable veto rules — include only when enabled, so the LLM is
    # not distracted by defaults. When enabled, these act as HARD vetoes
    # per the scoring rubric in prompts/policy.md.
    configurable_rules: list[str] = []
    if policy.min_grade:
        configurable_rules.append(
            f"  min_grade: {policy.min_grade} — source grade must be >= this letter; below => HARD gap (DENY)"
        )
    if policy.min_contact_hours and policy.min_contact_hours > 0:
        configurable_rules.append(
            f"  min_contact_hours: {policy.min_contact_hours} — total lecture + lab hours must meet this floor; below => HARD gap"
        )
    if policy.max_course_age_years and policy.max_course_age_years > 0:
        configurable_rules.append(
            f"  max_course_age_years: {policy.max_course_age_years} — source term must be within this many years of today; older => HARD gap (course too old)"
        )
    if policy.must_include_topics:
        configurable_rules.append(
            f"  must_include_topics: {policy.must_include_topics} — every listed topic must appear in source topics; any missing => HARD gap"
        )

    if configurable_rules:
        lines.append("")
        lines.append("Configurable Veto Rules (enabled):")
        lines.extend(configurable_rules)

    return "\n".join(lines)


def build_decision_prompt(
    packet: DecisionInputsPacket,
    evidence_rows: list,
    chunks_by_evidence: dict[str, list[dict]],
) -> str:
    """Build the user message for the GPT decision call."""
    evidence_text = _format_evidence_for_prompt(evidence_rows, chunks_by_evidence)
    target_text = _format_target_for_prompt(packet)

    user_msg = f"""\
## Case ID: {packet.case_id}

## Target Course Requirements
{target_text}

## Extracted Evidence from Source Course Documents
{evidence_text}

## Instructions
Based on the evidence above and the target course requirements, produce your equivalency decision.

IMPORTANT: The extraction pipeline may not have produced explicit topic or outcome lists. You MUST infer topic and outcome coverage from the course title, description, and any catalog match data provided in the evidence. For example, a course titled "Anatomy and Physiology" clearly covers topics like "skeletal system", "muscular system", "nervous system", "cell biology", etc. Count inferred matches when scoring topic and outcome coverage. Do NOT report "No required topics matched" if the course title and description clearly relate to the target course's subject area.

SCORING REMINDER: Follow the scoring rubric strictly. Unknown/missing credits = 0 points for credit parity (out of 20). Unknown/missing lab info = 0 points for lab parity (out of 10). Do NOT award full marks for components where the evidence is unknown or missing. A perfect score of 100 is only possible when ALL four components (topics, outcomes, credits, lab) are confirmed with evidence.

Remember: cite chunk_ids for every reason and gap. Return ONLY the JSON object.
"""
    return user_msg


# ---------------------------------------------------------------------------
# OpenAI API call
# ---------------------------------------------------------------------------

def call_llm_decision(
    packet: DecisionInputsPacket,
    evidence_rows: list,
    chunks_by_evidence: dict[str, list[dict]],
    model: str = "gpt-4o",
) -> DecisionResult:
    """
    Call OpenAI GPT to produce an equivalency decision.

    Args:
        packet: The DecisionInputsPacket with target/policy info
        evidence_rows: list of GroundedEvidence ORM objects
        chunks_by_evidence: dict mapping str(evidence_id) -> list of chunk dicts
        model: OpenAI model to use (default gpt-4o)

    Returns:
        DecisionResult (same schema the deterministic engine returns)
    """
    system_prompt = _load_system_prompt()
    user_message = build_decision_prompt(packet, evidence_rows, chunks_by_evidence)

    client = openai.OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    # Compute score cap based on unknown evidence fields
    # Credits unknown = lose 20 pts (credit parity can't be confirmed)
    # Lab required but unknown/missing = lose 10 pts (lab parity can't be confirmed)
    score_cap = 100
    for ev in evidence_rows:
        if ev.fact_key == "credits_or_units" and ev.unknown:
            score_cap -= 20

    if packet.target_course.target_lab_required:
        lab_confirmed = False
        for ev in evidence_rows:
            if ev.fact_key in ("lab_component", "contact_hours_lab") and not ev.unknown:
                lab_confirmed = True
                break
        if not lab_confirmed:
            score_cap -= 10

    # Deterministic evidence-quality fallback — structural, not LLM-judged.
    # Per field: 0 if unknown, 70 if known no citation, 100 if known with citation.
    # Averaged across the evidence fact_keys actually produced by the extraction
    # pipeline (course_code/title/description drive the LLM's inference when
    # explicit topics/outcomes lists are not extracted).
    policy = packet.policy
    evidence_keys = {
        "course_code", "title", "description",
        "credits_or_units",
        "contact_hours_lecture", "contact_hours_lab", "lab_component",
        "topics", "outcomes", "assessments",
        "prerequisites",
    }
    if policy.min_grade:
        evidence_keys.add("grade")
    if policy.max_course_age_years and policy.max_course_age_years > 0:
        evidence_keys.add("term_taken")

    scores: list[int] = []
    for ev in evidence_rows:
        if ev.fact_key not in evidence_keys:
            continue
        if ev.unknown or (ev.fact_value in (None, "") and not ev.fact_json):
            scores.append(0)
            continue
        has_citation = bool(chunks_by_evidence.get(str(ev.evidence_id)))
        scores.append(100 if has_citation else 70)

    fallback_eq = int(sum(scores) / max(1, len(scores))) if scores else 0

    return _parse_llm_response(
        data, score_cap=score_cap, fallback_evidence_quality=fallback_eq,
    )


def _parse_llm_response(data: dict, score_cap: int = 100, fallback_evidence_quality: int = 0) -> DecisionResult:
    """Parse the JSON response from GPT into a DecisionResult.

    fallback_evidence_quality is used when the LLM omits the evidence_quality_score
    field (or returns 0), since evidence quality is a structural property of the
    source evidence rather than something the LLM should be judging.
    """
    decision = Decision(data["decision"])
    confidence = Confidence(data.get("confidence", "MEDIUM"))
    score = int(data.get("equivalency_score", 0))

    # Cap score based on unknown evidence fields
    score = min(score, score_cap)

    # evidence_quality_score: prefer deterministic computation from the evidence
    # rows (passed in as fallback) over the LLM's self-report.
    try:
        llm_eq = int(data.get("evidence_quality_score") or 0)
    except (TypeError, ValueError):
        llm_eq = 0
    evidence_quality = fallback_evidence_quality if fallback_evidence_quality > 0 else llm_eq
    evidence_quality = max(0, min(100, evidence_quality))

    def _safe_citation(c):
        if isinstance(c, dict):
            return Citation(doc_id=c.get("doc_id", ""), chunk_id=c.get("chunk_id"))
        return Citation(doc_id="", chunk_id=str(c) if c else None)

    # Parse reasons
    reasons = []
    for r in data.get("reasons", []):
        citations = [_safe_citation(c) for c in r.get("citations", [])]
        reasons.append(ReasonItem(text=r["text"], citations=citations))

    # Parse gaps
    gaps = []
    for g in data.get("gaps", []):
        citations = [_safe_citation(c) for c in g.get("citations", [])]
        gaps.append(GapItem(
            text=g["text"],
            severity=g.get("severity", "HARD"),
            citations=citations,
        ))

    # Handle both bridge_plan (old format) and bridge_plan_items (new format from policy.md)
    bridge_plan = data.get("bridge_plan", [])
    if not bridge_plan:
        bridge_plan_items = data.get("bridge_plan_items", [])
        bridge_plan = [item.get("text", str(item)) if isinstance(item, dict) else item for item in bridge_plan_items]

    missing_info = data.get("missing_info_requests", [])

    # Override the LLM's decision with score-based bands to ensure consistency
    score = max(0, min(100, score))
    if score >= 90:
        decision = Decision.APPROVE
    elif score >= 80:
        decision = Decision.APPROVE_WITH_BRIDGE
    elif score >= 70:
        decision = Decision.NEEDS_MORE_INFO
    else:
        decision = Decision.DENY

    return DecisionResult(
        decision=decision,
        equivalency_score=score,
        confidence=confidence,
        evidence_quality_score=evidence_quality,
        reasons=reasons,
        gaps=gaps,
        bridge_plan=bridge_plan,
        missing_info_requests=missing_info,
    )
