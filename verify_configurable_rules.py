"""
Targeted verification of the configurable policy rules.

These rules are implemented in decision_engine/contracts.py but not naturally
exercised by the student-case dataset (transcripts are recent, grades are
passing, no policy-level mandatory topics are configured by default). This
script feeds hand-crafted evidence into decide() and asserts the expected
HARD gap fires. No OpenAI calls, no database — pure deterministic engine.

Usage:
    python verify_configurable_rules.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from decision_engine.contracts import (
    CourseEvidence, DecisionInputsPacket, EvidenceField,
    PolicyConfig, TargetCourseProfile, decide,
)


def _make_evidence(**overrides) -> CourseEvidence:
    """Build a CourseEvidence with sensible defaults, overridable per field."""
    defaults = {
        "credits": EvidenceField(value=3, unknown=False),
        "contact_hours_lecture": EvidenceField(value=45, unknown=False),
        "contact_hours_lab": EvidenceField(value=0, unknown=False),
        "lab_component": EvidenceField(value=False, unknown=False),
        "topics": EvidenceField(
            value=["variables", "control flow", "functions", "arrays", "basic algorithms"],
            unknown=False,
        ),
        "outcomes": EvidenceField(
            value=[
                "Write programs using fundamental programming constructs",
                "Decompose problems into functions",
                "Trace and debug simple programs",
            ],
            unknown=False,
        ),
        "assessments": EvidenceField(value=["Midterm", "Final"], unknown=False),
        "grade": EvidenceField(value="A", unknown=False),
        "term_taken": EvidenceField(value="Fall 2024", unknown=False),
    }
    defaults.update(overrides)
    return CourseEvidence(**defaults)


TARGET_PROGRAMMING_I = TargetCourseProfile(
    target_credits=3,
    target_lab_required=False,
    required_topics=["variables", "control flow", "functions", "arrays", "basic algorithms"],
    required_outcomes=[
        "Write programs using fundamental programming constructs",
        "Decompose problems into functions",
        "Trace and debug simple programs",
    ],
)


def _run(name: str, policy: PolicyConfig, evidence: CourseEvidence, expected_severity: str, expected_gap_substring: str) -> bool:
    """Run decide() and assert that a gap with the expected severity and substring is present."""
    packet = DecisionInputsPacket(
        case_id=f"test-{name}",
        source_course=evidence,
        target_course=TARGET_PROGRAMMING_I,
        policy=policy,
    )
    result = decide(packet)
    match = next(
        (g for g in result.gaps if g.severity == expected_severity and expected_gap_substring.lower() in g.text.lower()),
        None,
    )
    ok = match is not None
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
    print(f"         decision={result.decision.value}, score={result.equivalency_score}, confidence={result.confidence.value}")
    if match:
        print(f"         triggered gap: [{match.severity}] {match.text}")
    else:
        print(f"         expected a [{expected_severity}] gap containing '{expected_gap_substring}'; got:")
        for g in result.gaps:
            print(f"           - [{g.severity}] {g.text}")
    return ok


def test_min_grade_below_threshold() -> bool:
    """min_grade: "C" rule must fire a HARD gap when source grade is below C."""
    policy = PolicyConfig(min_grade="C")
    evidence = _make_evidence(grade=EvidenceField(value="D+", unknown=False))
    return _run(
        "min_grade below threshold (D+ < C)",
        policy, evidence,
        expected_severity="HARD",
        expected_gap_substring="does not meet minimum",
    )


def test_min_contact_hours_below_floor() -> bool:
    """min_contact_hours: 45 rule must fire a HARD gap when lecture+lab hours are below 45."""
    policy = PolicyConfig(min_contact_hours=45)
    evidence = _make_evidence(
        contact_hours_lecture=EvidenceField(value=30, unknown=False),
        contact_hours_lab=EvidenceField(value=0, unknown=False),
    )
    return _run(
        "min_contact_hours below floor (30h < 45h)",
        policy, evidence,
        expected_severity="HARD",
        expected_gap_substring="below minimum",
    )


def test_max_course_age_years_expired() -> bool:
    """max_course_age_years: 5 rule must fire a HARD gap when the source term is >5 years old."""
    policy = PolicyConfig(max_course_age_years=5)
    old_year = datetime.now(timezone.utc).year - 10
    evidence = _make_evidence(term_taken=EvidenceField(value=f"Fall {old_year}", unknown=False))
    return _run(
        f"max_course_age_years expired (source taken {old_year}, max 5 years)",
        policy, evidence,
        expected_severity="HARD",
        expected_gap_substring="years old",
    )


def test_must_include_topics_missing() -> bool:
    """must_include_topics: ['recursion'] rule must fire a HARD gap when source lacks recursion."""
    policy = PolicyConfig(must_include_topics=["recursion"])
    # Default evidence does not include 'recursion' in its topics list.
    return _run(
        "must_include_topics missing mandatory topic (recursion)",
        policy, _make_evidence(),
        expected_severity="HARD",
        expected_gap_substring="mandatory policy topics",
    )


def test_lab_parity_required_but_missing() -> bool:
    """Lab parity: target_lab_required=True plus source lab=False must fire FIXABLE gap with bridge item."""
    policy = PolicyConfig()
    target_with_lab = TargetCourseProfile(
        target_credits=3,
        target_lab_required=True,
        required_topics=["variables"],
        required_outcomes=["Write programs"],
    )
    evidence = _make_evidence(lab_component=EvidenceField(value=False, unknown=False))
    packet = DecisionInputsPacket(
        case_id="test-lab", source_course=evidence,
        target_course=target_with_lab, policy=policy,
    )
    result = decide(packet)
    gap_ok = any(g.severity == "FIXABLE" and "lab" in g.text.lower() for g in result.gaps)
    bridge_ok = any("lab" in b.text.lower() for b in result.bridge_plan_items)
    ok = gap_ok and bridge_ok
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] lab parity required-but-missing fires FIXABLE gap + bridge item")
    print(f"         decision={result.decision.value}, score={result.equivalency_score}")
    if not ok:
        print(f"         gap_ok={gap_ok}, bridge_ok={bridge_ok}")
    return ok


def test_bridge_plan_for_partial_match() -> bool:
    """Bridge plan: partial topic/outcome match must emit BridgeItems for each missing item."""
    policy = PolicyConfig()
    target = TargetCourseProfile(
        target_credits=3,
        target_lab_required=False,
        required_topics=["trees", "graphs", "hashing", "sorting"],
        required_outcomes=["Implement data structures", "Analyze complexity"],
    )
    evidence = _make_evidence(
        topics=EvidenceField(value=["trees", "graphs"], unknown=False),
        outcomes=EvidenceField(value=["Implement data structures"], unknown=False),
    )
    packet = DecisionInputsPacket(
        case_id="test-bridge", source_course=evidence,
        target_course=target, policy=policy,
    )
    result = decide(packet)
    missing_topics_bridged = sum(
        1 for b in result.bridge_plan_items
        if b.addresses_gap and b.addresses_gap.startswith("topic_missing:")
    )
    missing_outcomes_bridged = sum(
        1 for b in result.bridge_plan_items
        if b.addresses_gap and b.addresses_gap.startswith("outcome_missing:")
    )
    ok = missing_topics_bridged == 2 and missing_outcomes_bridged == 1
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] bridge plan emits items for each unmatched topic/outcome")
    print(f"         decision={result.decision.value}, score={result.equivalency_score}")
    print(f"         missing_topics_bridged={missing_topics_bridged}/2, missing_outcomes_bridged={missing_outcomes_bridged}/1")
    print(f"         bridge items ({len(result.bridge_plan_items)}):")
    for b in result.bridge_plan_items:
        print(f"           - {b.text}  ({b.addresses_gap})")
    return ok


def main() -> int:
    print("Configurable Policy Rules — deterministic verification")
    print("=" * 68)

    tests = [
        ("min_grade",              test_min_grade_below_threshold),
        ("lab parity",             test_lab_parity_required_but_missing),
        ("min_contact_hours",      test_min_contact_hours_below_floor),
        ("max_course_age_years",   test_max_course_age_years_expired),
        ("must_include_topics",    test_must_include_topics_missing),
        ("bridge plan generator",  test_bridge_plan_for_partial_match),
    ]

    passed = 0
    for label, fn in tests:
        print(f"\n--- {label} ---")
        if fn():
            passed += 1

    print("\n" + "=" * 68)
    print(f"Passed: {passed}/{len(tests)}")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
