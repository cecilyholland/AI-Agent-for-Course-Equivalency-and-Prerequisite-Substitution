"""
LLM-based decision engine.

Calls OpenAI (GPT) with the extracted evidence, citation chunks, and policy
to produce a structured equivalency decision with citations.
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
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an AI course equivalency evaluator for a university.

Your job: given extracted evidence about a SOURCE course (from uploaded syllabi/catalogs)
and a TARGET course profile, decide whether the source course is equivalent to the target.

## Scoring and Decision Thresholds

You must assign an equivalency_score (0-100) and then use these bands to determine the decision:

- **90-100 → APPROVE**: The source course fully satisfies the target course requirements.
  All essential criteria match (credits, topics, outcomes, lab if required).

- **80-89 → APPROVE_WITH_BRIDGE**: The source course is mostly equivalent but has minor
  non-essential gaps that can be resolved with a bridge plan (e.g., one extra
  assignment, a short module, or a 1-credit supplement). The core content matches
  but small supplementary pieces are missing.

- **70-79 → NEEDS_MORE_INFO**: Some important information is missing from the evidence
  and you cannot make a confident decision without it. Use this when key facts
  (like credits, core topics, or outcomes) are unknown or unclear.
  Do NOT use this for minor gaps — only when missing info prevents a decision.

- **Below 70 → DENY**: The source course has major gaps that cannot be bridged.
  Examples: credits differ by more than 1, required topics are completely absent,
  or hard requirements are unmet.

## Citation Requirements

Every reason and gap you provide MUST cite the chunk_id(s) from the evidence that
support your claim. This is critical for audit purposes.

## Output Format

Return ONLY valid JSON matching this exact schema (no markdown, no explanation outside JSON):

{
  "decision": "APPROVE" | "DENY" | "NEEDS_MORE_INFO" | "APPROVE_WITH_BRIDGE",
  "equivalency_score": <integer 0-100>,
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "reasons": [
    {"text": "explanation of why this supports equivalency", "citations": [{"chunk_id": "..."}]}
  ],
  "gaps": [
    {"text": "what is missing or mismatched", "severity": "HARD" | "FIXABLE" | "INFO_MISSING", "citations": [{"chunk_id": "..."}]}
  ],
  "bridge_plan": ["action item 1", "action item 2"],
  "missing_info_requests": ["what additional info is needed"]
}

Severity meanings:
- HARD: Cannot be resolved, leads to DENY
- FIXABLE: Minor gap, can be bridged (leads to APPROVE_WITH_BRIDGE)
- INFO_MISSING: Key info not available, leads to NEEDS_MORE_INFO
"""

FEW_SHOT_EXAMPLES = """\
## Examples

### Example 1: APPROVE
Evidence: Source course has 3 credits (chunk_id: "c-001"), covers data structures, algorithms, complexity analysis (chunk_id: "c-002"), includes programming assignments and exams (chunk_id: "c-003").
Target: 3 credits, required topics: ["data structures", "algorithms", "complexity analysis"].

Decision:
{"decision": "APPROVE", "equivalency_score": 95, "confidence": "HIGH", "reasons": [{"text": "Credits match exactly (3 credits source = 3 credits target)", "citations": [{"chunk_id": "c-001"}]}, {"text": "All required topics covered: data structures, algorithms, complexity analysis", "citations": [{"chunk_id": "c-002"}]}], "gaps": [], "bridge_plan": [], "missing_info_requests": []}

### Example 2: DENY
Evidence: Source course has 2 credits (chunk_id: "c-010"), covers introductory programming only (chunk_id: "c-011"), no lab component (chunk_id: "c-012").
Target: 4 credits, required topics: ["operating systems", "process management", "memory management"], lab required.

Decision:
{"decision": "DENY", "equivalency_score": 10, "confidence": "HIGH", "reasons": [], "gaps": [{"text": "Credits far below target (2 vs 4 required)", "severity": "HARD", "citations": [{"chunk_id": "c-010"}]}, {"text": "Course content (introductory programming) does not cover any required OS topics", "severity": "HARD", "citations": [{"chunk_id": "c-011"}]}, {"text": "No lab component but target requires lab", "severity": "HARD", "citations": [{"chunk_id": "c-012"}]}], "bridge_plan": [], "missing_info_requests": []}

### Example 3: NEEDS_MORE_INFO
Evidence: Source course title is "Advanced Computing" (chunk_id: "c-020"), credits are not stated in the document (unknown), topics list not found in syllabus.
Target: 3 credits, required topics: ["machine learning", "neural networks"].

Decision:
{"decision": "NEEDS_MORE_INFO", "equivalency_score": 0, "confidence": "LOW", "reasons": [], "gaps": [{"text": "Credit hours not found in uploaded documents", "severity": "INFO_MISSING", "citations": [{"chunk_id": "c-020"}]}, {"text": "Course topics and learning outcomes not available in provided materials", "severity": "INFO_MISSING", "citations": [{"chunk_id": "c-020"}]}], "bridge_plan": [], "missing_info_requests": ["Provide official catalog entry or syllabus showing credit hours", "Provide course syllabus with topics list or learning outcomes"]}

### Example 4: APPROVE_WITH_BRIDGE
Evidence: Source course has 3 credits (chunk_id: "c-030"), covers databases, SQL, normalization, transactions (chunk_id: "c-031"), includes assignments but no group project (chunk_id: "c-032").
Target: 3 credits, required topics: ["databases", "SQL", "normalization", "transactions", "NoSQL databases"].

Decision:
{"decision": "APPROVE_WITH_BRIDGE", "equivalency_score": 82, "confidence": "MEDIUM", "reasons": [{"text": "Credits match (3 = 3)", "citations": [{"chunk_id": "c-030"}]}, {"text": "Covers 4 of 5 required topics: databases, SQL, normalization, transactions", "citations": [{"chunk_id": "c-031"}]}], "gaps": [{"text": "NoSQL databases topic not covered in source course - this is a supplementary topic that can be bridged", "severity": "FIXABLE", "citations": [{"chunk_id": "c-031"}]}], "bridge_plan": ["Complete a supplementary module on NoSQL databases (estimated 2-3 weeks self-study)"], "missing_info_requests": []}
"""


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
    user_message = build_decision_prompt(packet, evidence_rows, chunks_by_evidence)

    client = openai.OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLES},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    return _parse_llm_response(data)


def _parse_llm_response(data: dict) -> DecisionResult:
    """Parse the JSON response from GPT into a DecisionResult."""
    # Map decision string to enum
    decision = Decision(data["decision"])
    confidence = Confidence(data.get("confidence", "MEDIUM"))
    score = int(data.get("equivalency_score", 0))

    # Parse reasons
    reasons = []
    for r in data.get("reasons", []):
        citations = [
            Citation(doc_id=c.get("doc_id", ""), chunk_id=c.get("chunk_id"))
            for c in r.get("citations", [])
        ]
        reasons.append(ReasonItem(text=r["text"], citations=citations))

    # Parse gaps
    gaps = []
    for g in data.get("gaps", []):
        citations = [
            Citation(doc_id=c.get("doc_id", ""), chunk_id=c.get("chunk_id"))
            for c in g.get("citations", [])
        ]
        gaps.append(GapItem(
            text=g["text"],
            severity=g.get("severity", "HARD"),
            citations=citations,
        ))

    bridge_plan = data.get("bridge_plan", [])
    missing_info = data.get("missing_info_requests", [])

    return DecisionResult(
        decision=decision,
        equivalency_score=max(0, min(100, score)),
        confidence=confidence,
        reasons=reasons,
        gaps=gaps,
        bridge_plan=bridge_plan,
        missing_info_requests=missing_info,
    )
