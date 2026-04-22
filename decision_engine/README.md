# Decision Engine

The decision engine evaluates course equivalency requests by comparing source course evidence against target course requirements. It produces one of four decisions: **APPROVE**, **APPROVE_WITH_BRIDGE**, **NEEDS_MORE_INFO**, or **DENY**.

## Architecture

The engine supports two modes:

| File | Mode | Description |
|------|------|-------------|
| `contracts.py` | Deterministic | Pure function `decide()` with no external dependencies. Scoring-based logic with configurable thresholds. |
| `llm_decision.py` | LLM-based | Calls OpenAI GPT with evidence and policy prompt. Returns same `DecisionResult` schema. |

Both modes use the same data contracts defined in `contracts.py`.

## Decision Outcomes

| Decision | When it occurs |
|----------|----------------|
| **APPROVE** | Score >= 90 with no FIXABLE, HARD, or INFO_MISSING gaps |
| **APPROVE_WITH_BRIDGE** | Score 80-89, OR score >= 90 with FIXABLE gaps |
| **NEEDS_MORE_INFO** | Any INFO_MISSING gap exists, OR score falls in ambiguous band (70-79) |
| **DENY** | Any HARD gap exists, OR score < 70 |

Priority order: INFO_MISSING gaps trigger NEEDS_MORE_INFO first, then HARD gaps trigger DENY, then score determines the remaining outcomes.

## Scoring System

The equivalency score is calculated from four components totaling 100 points:

| Component | Weight | Description |
|-----------|--------|-------------|
| Topics | 40 | Overlap between source topics and target required topics |
| Outcomes | 30 | Overlap between source outcomes and target required outcomes |
| Credits | 20 | Credit hour comparison |
| Lab Parity | 10 | Lab component match (when required) |

### Credits Scoring (20 points)

| Condition | Points | Gap |
|-----------|--------|-----|
| Exact match | 20 | None |
| Off by 1 | 10 | FIXABLE |
| Off by 2+ | 0 | HARD |
| Unknown | 0 | INFO_MISSING (if `require_credits_known`) |

### Lab Parity Scoring (10 points)

| Condition | Points | Gap |
|-----------|--------|-----|
| Lab not required by target | 10 | None |
| Lab required and source has lab | 10 | None |
| Lab required and source has no lab | 0 | FIXABLE |
| Lab required and source lab unknown | 0 | INFO_MISSING |

### Topics Scoring (40 points)

| Condition | Points | Gap |
|-----------|--------|-----|
| No required topics specified | 40 | None |
| All required topics matched | 40 | None |
| Partial match (N of M) | 40 * (N/M) | Bridge items for missing |
| Zero topics matched | 0 | HARD |
| Topics unknown (and outcomes unknown) | 0 | INFO_MISSING |

**Matching logic:** A required topic matches a source topic if:
- Substring match (case-insensitive), OR
- 60%+ content-word overlap (handles plurals, synonyms, extra modifiers)

### Outcomes Scoring (30 points)

| Condition | Points | Gap |
|-----------|--------|-----|
| No required outcomes specified | 30 | None |
| All required outcomes matched | 30 | None |
| Partial match (N of M) | 30 * (N/M) | Bridge items for missing |
| Zero outcomes matched | 0 | HARD |

## Gap Types

| Severity | Effect | Examples |
|----------|--------|----------|
| **HARD** | Forces DENY | Credits off by 2+, zero topic/outcome overlap, policy violations |
| **FIXABLE** | Forces BRIDGE (if score >= 80) | Credits off by 1, missing lab, partial topic/outcome matches |
| **INFO_MISSING** | Forces NEEDS_MORE_INFO | Unknown credits, topics, outcomes, lab; policy fields missing |

## Policy Configuration

The `PolicyConfig` controls thresholds and optional rules:

```python
class PolicyConfig:
    # Score thresholds
    approve_threshold: int = 90
    bridge_threshold: int = 80
    needs_info_threshold: int = 70

    # Required evidence toggles
    require_lab_parity: bool = True
    require_credits_known: bool = True
    require_topics_or_outcomes: bool = True

    # Optional hard rules (disabled by default)
    min_grade: Optional[str] = None          # e.g., "C" - fails if grade below
    min_contact_hours: int = 0               # e.g., 45 - fails if hours below
    max_course_age_years: int = 0            # e.g., 5 - fails if course too old
    must_include_topics: List[str] = []      # mandatory topics beyond target requirements
```

### Optional Policy Rules

When enabled, these create additional HARD or INFO_MISSING gaps:

| Rule | Condition | Gap |
|------|-----------|-----|
| `min_grade: "C"` | Grade below C | HARD |
| `min_grade: "C"` | Grade unknown | INFO_MISSING |
| `min_contact_hours: 45` | Total hours < 45 | HARD |
| `min_contact_hours: 45` | Hours unknown | INFO_MISSING |
| `max_course_age_years: 5` | Course > 5 years old | HARD |
| `max_course_age_years: 5` | Term unknown | INFO_MISSING |
| `must_include_topics: ["ethics"]` | Topic not found | HARD |

## Example Scenarios

### APPROVE (score 100, no gaps)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 4 vs 4 (exact match) | 20 |
| Lab | Required + present | 10 |
| Topics | 4/4 matched | 40 |
| Outcomes | 3/3 matched | 30 |
| **Total** | | **100** |

### APPROVE_WITH_BRIDGE (score 90, FIXABLE gap)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 3 vs 4 (off by 1) | 10 |
| Lab | Required + present | 10 |
| Topics | 4/4 matched | 40 |
| Outcomes | 3/3 matched | 30 |
| **Total** | | **90** |

Result: Score >= 90 but FIXABLE gap exists, so APPROVE_WITH_BRIDGE.

### APPROVE_WITH_BRIDGE (score 80, bridge band)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 4 vs 4 (exact match) | 20 |
| Lab | Required + present | 10 |
| Topics | 3/4 matched (75%) | 30 |
| Outcomes | 2/3 matched (67%) | 20 |
| **Total** | | **80** |

Result: Score in bridge band (80-89), so APPROVE_WITH_BRIDGE.

### NEEDS_MORE_INFO (INFO_MISSING gap)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | Unknown | 0 |
| Lab | Required + present | 10 |
| Topics | 4/4 matched | 40 |
| Outcomes | 3/3 matched | 30 |
| **Total** | | **80** |

Result: INFO_MISSING gap on credits, so NEEDS_MORE_INFO regardless of score.

### NEEDS_MORE_INFO (ambiguous band)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 4 vs 4 (exact match) | 20 |
| Lab | Required + present | 10 |
| Topics | 2/4 matched (50%) | 20 |
| Outcomes | 2/3 matched (67%) | 20 |
| **Total** | | **70** |

Result: Score in ambiguous band (70-79), no HARD gaps, so NEEDS_MORE_INFO.

### DENY (HARD gap)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 2 vs 4 (off by 2) | 0 |
| Lab | Required + present | 10 |
| Topics | 3/4 matched | 30 |
| Outcomes | 2/3 matched | 20 |
| **Total** | | **60** |

Result: HARD gap on credits, so DENY regardless of other factors.

### DENY (low score)

| Component | Scenario | Points |
|-----------|----------|--------|
| Credits | 3 vs 4 (off by 1) | 10 |
| Lab | Required + missing | 0 |
| Topics | 2/4 matched (50%) | 20 |
| Outcomes | 1/3 matched (33%) | 10 |
| **Total** | | **40** |

Result: Score < 70, no INFO_MISSING, so DENY.

## Data Contracts

### Input: `DecisionInputsPacket`

```python
class DecisionInputsPacket:
    case_id: str
    source_course: CourseEvidence      # extracted evidence from source documents
    target_course: TargetCourseProfile # requirements to match against
    policy: PolicyConfig               # thresholds and rules
```

### Source Evidence: `CourseEvidence`

```python
class CourseEvidence:
    credits: EvidenceField              # int
    contact_hours_lecture: EvidenceField # int
    contact_hours_lab: EvidenceField    # int
    lab_component: EvidenceField        # bool
    topics: EvidenceField               # List[str]
    outcomes: EvidenceField             # List[str]
    assessments: EvidenceField          # List[str]
    grade: EvidenceField                # str, e.g., "B+"
    term_taken: EvidenceField           # str, e.g., "Fall 2022"
```

Each `EvidenceField` has:
- `value`: the extracted value (or None)
- `unknown`: True if the value couldn't be determined
- `citations`: list of `Citation` objects linking to source documents

### Output: `DecisionResult`

```python
class DecisionResult:
    decision: Decision                  # APPROVE, DENY, NEEDS_MORE_INFO, APPROVE_WITH_BRIDGE
    equivalency_score: int              # 0-100
    confidence: Confidence              # HIGH, MEDIUM, LOW
    evidence_quality_score: int         # 0-100, how complete the evidence is
    reasons: List[ReasonItem]           # positive findings with citations
    gaps: List[GapItem]                 # issues found (HARD, FIXABLE, INFO_MISSING)
    bridge_plan: List[str]              # remediation steps (backward compat)
    bridge_plan_items: List[BridgeItem] # structured remediation steps
    missing_info_requests: List[str]    # what additional info is needed
```

## Confidence Scoring

Confidence reflects certainty in the decision, separate from the equivalency score:

- Starts at 100, then applies penalties:
  - Each unknown field: -12
  - Each INFO_MISSING gap: -10
  - Score near threshold boundary: -10 to -30
- APPROVE_WITH_BRIDGE capped at MEDIUM (inherently uncertain)
- NEEDS_MORE_INFO always LOW (by definition uncertain)

Final mapping: >= 75 HIGH, >= 45 MEDIUM, else LOW.

## Committee Voting

For committee review, `aggregate_committee_votes()` applies majority-rule with conservative tiebreaking:

```python
priority = [DENY, NEEDS_MORE_INFO, APPROVE_WITH_BRIDGE, APPROVE]
```

Empty vote list returns NEEDS_MORE_INFO.

## LLM Decision Mode

The `llm_decision.py` module provides an alternative LLM-based decision path:

1. Loads system prompt from `prompts/policy.md`
2. Formats evidence and target requirements into a structured prompt
3. Calls OpenAI GPT (default: gpt-4o) with `temperature=0.2`
4. Parses JSON response into the same `DecisionResult` schema

Use `call_llm_decision()` when you want nuanced reasoning or when the deterministic rules don't capture edge cases well.

## Usage

### Deterministic Mode

```python
from decision_engine.contracts import (
    decide,
    DecisionInputsPacket,
    CourseEvidence,
    TargetCourseProfile,
    PolicyConfig,
    EvidenceField,
)

packet = DecisionInputsPacket(
    case_id="case-001",
    source_course=CourseEvidence(
        credits=EvidenceField(value=4, unknown=False),
        lab_component=EvidenceField(value=True, unknown=False),
        topics=EvidenceField(value=["loops", "functions", "data structures"], unknown=False),
        outcomes=EvidenceField(value=["write programs", "debug code"], unknown=False),
        # ... other fields
    ),
    target_course=TargetCourseProfile(
        target_credits=4,
        target_lab_required=True,
        required_topics=["loops", "functions", "data structures", "algorithms"],
        required_outcomes=["write programs", "debug code", "analyze complexity"],
    ),
    policy=PolicyConfig(),
)

result = decide(packet)
print(result.decision)           # Decision.APPROVE_WITH_BRIDGE
print(result.equivalency_score)  # 85
print(result.gaps)               # [GapItem(...)]
print(result.bridge_plan)        # ["Cover missing topic 'algorithms'...", ...]
```

### LLM Mode

```python
from decision_engine.llm_decision import call_llm_decision

result = call_llm_decision(
    packet=packet,
    evidence_rows=grounded_evidence_list,
    chunks_by_evidence=chunks_dict,
    model="gpt-4o",
)
```
