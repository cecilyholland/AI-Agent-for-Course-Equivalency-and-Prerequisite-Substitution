"""
Test all seeded cases against the running Docker backend.
Fetches each case's AI decision via the API and prints a summary table.

Usage:
    python test_docker_cases.py                  # default: http://localhost:8000
    python test_docker_cases.py http://host:port  # custom backend URL
"""
import json
import sys
import urllib.request

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"


def api_get(path: str):
    resp = urllib.request.urlopen(f"{BASE_URL}{path}")
    return json.loads(resp.read())


def main():
    cases = api_get("/api/cases")
    cases.sort(key=lambda x: x.get("studentId", ""))

    results = []
    for c in cases:
        sid = c["studentId"]
        name = c["studentName"] or ""
        target = c["courseRequested"] or ""
        status = c["status"]
        cid = c["caseId"]

        decision = status
        score = "-"
        confidence = "-"

        if status == "INVALID":
            decision = "INVALID (prompt injection)"
        else:
            try:
                detail = api_get(f"/api/cases/{cid}")
                dr = detail.get("decisionResult")
                if dr and dr.get("resultJson"):
                    rj = dr["resultJson"]
                    decision = rj.get("decision", "N/A")
                    score = rj.get("equivalency_score", "N/A")
                    confidence = rj.get("confidence", "N/A")
            except Exception as e:
                decision = f"ERROR: {e}"

        results.append({
            "case": sid,
            "student": name,
            "target": target,
            "decision": decision,
            "score": score,
            "confidence": confidence,
        })

    # Print summary table
    print("=" * 90)
    print(f"{'Case':<8} {'Student':<20} {'Target':<12} {'Decision':<25} {'Score':<6} {'Confidence'}")
    print("-" * 90)
    for r in results:
        print(f"{r['case']:<8} {r['student']:<20} {r['target']:<12} {r['decision']:<25} {str(r['score']):<6} {r['confidence']}")
    print("=" * 90)

    # Summary counts
    decisions = [r["decision"] for r in results]
    print(f"\nTotal: {len(results)} cases")
    for d in ["APPROVE", "APPROVE_WITH_BRIDGE", "NEEDS_MORE_INFO", "DENY", "INVALID (prompt injection)"]:
        count = sum(1 for x in decisions if x == d)
        if count:
            print(f"  {d}: {count}")
    errors = sum(1 for x in decisions if x.startswith("ERROR"))
    if errors:
        print(f"  ERRORS: {errors}")


if __name__ == "__main__":
    main()
