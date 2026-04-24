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
    score_cap = 100
    for ev in evidence_rows:
        if ev.fact_key == "credits_or_units" and ev.unknown:
            score_cap -= 20

    return _parse_llm_response(data, score_cap=score_cap)


def _parse_llm_response(data: dict, score_cap: int = 100) -> DecisionResult:
    """Parse the JSON response from GPT into a DecisionResult."""
    decision = Decision(data["decision"])
    confidence = Confidence(data.get("confidence", "MEDIUM"))
    score = int(data.get("equivalency_score", 0))

    # Cap score based on unknown evidence fields
    score = min(score, score_cap)

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
        reasons=reasons,
        gaps=gaps,
        bridge_plan=bridge_plan,
        missing_info_requests=missing_info,
    )
