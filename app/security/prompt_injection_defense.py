# app/security/prompt_injection_defense.py
# Text-based prompt injection detection for PDF-derived text.
# if REJECT, extraction stops before chunking/parsing.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import re


class Decision(str, Enum):
    ALLOW = "allow"
    REJECT = "reject"


@dataclass(frozen=True)
class Finding:
    detector: str              # "regex", "typoglycemia", "vigil"
    page_num: int              # 1-based
    severity: str              # "low", "medium", "high"
    points: int                # risk points contributed
    match: str                 # pattern name or "word~target"
    snippet: str               # manifest/logging
    detail: Dict[str, Any]     # extra structured info


@dataclass(frozen=True)
class ScanResult:
    detected: bool
    decision: Decision
    total_score: int
    findings: List[Finding]

# Narrow regex patterns focused on instruction-like prompt injection
# Typoglycemia-style detection for obfuscated keywords
# Light normalization
class PromptInjectionFilter:

    PATTERNS_HIGH: List[Tuple[str, str]] = [
        ("ignore_previous_instructions", r"ignore\s+(all\s+)?previous\s+instructions?"),
        ("developer_mode", r"you\s+are\s+now\s+(in\s+)?developer\s+mode"),
        ("system_override", r"\bsystem\s+override\b"),
        ("reveal_prompt", r"(reveal|show|print|leak)\s+(the\s+)?(system\s+)?prompt"),
        ("follow_only_these", r"follow\s+these\s+instructions\s+exactly"),
        ("disregard_policies", r"disregard\s+(all\s+)?(rules|policies|instructions)"),
        ("bypass_safety", r"\bbypass\s+(safety|policy|policies|rules)\b"),
    ]

    PATTERNS_MEDIUM: List[Tuple[str, str]] = [
        ("jailbreak", r"\bjailbreak\b"),
        ("prompt_injection_term", r"\bprompt\s+injection\b"),
        ("system_prompt_term", r"\bsystem\s+prompt\b"),
        ("developer_message_term", r"\bdeveloper\s+message\b"),
        ("override_rules", r"override\s+(safety|policy|policies|rules)"),
        ("do_not_explain", r"do\s+not\s+(explain|justify|mention)"),
    ]

    FUZZY_KEYWORDS: List[str] = ["ignore", "bypass", "override", "reveal", "system", "prompt"]


# Collapse whitespace/newlines and tame long repetition
    def normalize_for_scan(self, text: str) -> str:
        t = re.sub(r"\s+", " ", text or "")
        t = re.sub(r"(.)\1{3,}", r"\1", t)
        return t[:20000]


# Return list of (severity, name, pattern) for matches
    def regex_hits(self, text: str) -> List[Tuple[str, str, str]]:
        hits: List[Tuple[str, str, str]] = []
        for name, pat in self.PATTERNS_HIGH:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(("high", name, pat))
        for name, pat in self.PATTERNS_MEDIUM:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(("medium", name, pat))
        return hits


# Return list of (word, target) for typoglycemia variants
    def typoglycemia_hits(self, text: str) -> List[Tuple[str, str]]:
        hits: List[Tuple[str, str]] = []
        words = re.findall(r"\b\w+\b", (text or "").lower())
        for w in words:
            for target in self.FUZZY_KEYWORDS:
                if self._is_typoglycemia_variant(w, target):
                    hits.append((w, target))
        return hits

    @staticmethod
    def _is_typoglycemia_variant(word: str, target: str) -> bool:
        # Same first/last letter; middle letters are a permutation; not equal to target
        if len(word) != len(target) or len(word) < 4:
            return False
        return (
            word[0] == target[0]
            and word[-1] == target[-1]
            and sorted(word[1:-1]) == sorted(target[1:-1])
            and word != target
        )


# Optional Vigil integration. Off by default.
class VigilAdapter:

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self._app = None

    def _load(self) -> None:
        if self._app is not None:
            return
        from vigil import Vigil  # type: ignore
        self._app = Vigil.from_config(self.config_path)

    def scan(self, text: str) -> Dict[str, Any]:
        self._load()
        assert self._app is not None
        return self._app.input_scanner.perform_scan(text)



# Main entry point for the extraction pipeline.
# if decision == REJECT => stop extraction before chunking/parsing
class PromptInjectionDefense:

    def __init__(
        self,
        *,
        enable_vigil: bool = False,
        vigil_config_path: Optional[str] = None,
        reject_threshold: int = 7,
        points_high_regex: int = 5,
        points_medium_regex: int = 3,
        points_typoglycemia: int = 2,
        points_multi_hit_bonus: int = 2,
        max_findings: int = 50,
    ) -> None:
        self.filter = PromptInjectionFilter()

        self.reject_threshold = int(reject_threshold)
        self.points_high_regex = int(points_high_regex)
        self.points_medium_regex = int(points_medium_regex)
        self.points_typoglycemia = int(points_typoglycemia)
        self.points_multi_hit_bonus = int(points_multi_hit_bonus)
        self.max_findings = int(max_findings)

        self.vigil: Optional[VigilAdapter] = None
        if enable_vigil:
            if not vigil_config_path:
                raise ValueError("vigil_config_path is required if enable_vigil=True")
            self.vigil = VigilAdapter(vigil_config_path)

    def scan_pages(self, pages_text: List[str]) -> ScanResult:
        findings: List[Finding] = []
        per_page_points: Dict[int, int] = {}
        detected_any = False

        for page_num, raw in enumerate(pages_text or [], start=1):
            scan_text = self.filter.normalize_for_scan(raw or "")

            page_points = 0
            page_signals = 0

            # 1) Regex hits
            for severity, name, pat in self.filter.regex_hits(scan_text):
                detected_any = True
                page_signals += 1

                pts = self.points_high_regex if severity == "high" else self.points_medium_regex
                page_points += pts

                findings.append(
                    Finding(
                        detector="regex",
                        page_num=page_num,
                        severity=severity,
                        points=pts,
                        match=name,
                        snippet=scan_text[:180],
                        detail={"pattern": pat},
                    )
                )
                if len(findings) >= self.max_findings:
                    break

            if len(findings) >= self.max_findings:
                per_page_points[page_num] = page_points
                break

            # 2) Typoglycemia hits
            for w, target in self.filter.typoglycemia_hits(scan_text):
                detected_any = True
                page_signals += 1

                pts = self.points_typoglycemia
                page_points += pts

                findings.append(
                    Finding(
                        detector="typoglycemia",
                        page_num=page_num,
                        severity="low",
                        points=pts,
                        match=f"{w}~{target}",
                        snippet=scan_text[:180],
                        detail={},
                    )
                )
                if len(findings) >= self.max_findings:
                    break

            if len(findings) >= self.max_findings:
                per_page_points[page_num] = page_points
                break

            # 3) Vigil (optional)
            if self.vigil is not None and scan_text.strip():
                try:
                    vres = self.vigil.scan(scan_text)
                    if self._vigil_result_is_flag(vres):
                        detected_any = True
                        page_signals += 1

                        pts = self.points_high_regex + 2  # treat as strong
                        page_points += pts

                        findings.append(
                            Finding(
                                detector="vigil",
                                page_num=page_num,
                                severity="high",
                                points=pts,
                                match="vigil_flag",
                                snippet=scan_text[:180],
                                detail={"vigil_result": vres},
                            )
                        )
                except Exception as e:
                    # Vigil failure will not block rule-based detection
                    findings.append(
                        Finding(
                            detector="vigil_error",
                            page_num=page_num,
                            severity="low",
                            points=0,
                            match="vigil_error",
                            snippet=scan_text[:180],
                            detail={"error": str(e)},
                        )
                    )

            # Multi-hit bonus
            # distinguishes “instructiony” pages
            if page_signals >= 2:
                page_points += self.points_multi_hit_bonus
                findings.append(
                    Finding(
                        detector="bonus",
                        page_num=page_num,
                        severity="medium",
                        points=self.points_multi_hit_bonus,
                        match="multi_signal_bonus",
                        snippet=scan_text[:180],
                        detail={"signal_count": page_signals},
                    )
                )

            per_page_points[page_num] = page_points

        total_score = sum(per_page_points.values())
        decision = Decision.REJECT if total_score >= self.reject_threshold else Decision.ALLOW

        detected = detected_any or any(f.detector in ("regex", "typoglycemia", "vigil") for f in findings)

        return ScanResult(
            detected=detected,
            decision=decision,
            total_score=total_score,
            findings=findings[: self.max_findings],
        )

    @staticmethod
    def _vigil_result_is_flag(vres: Any) -> bool:
        if not isinstance(vres, dict):
            return False

        for k in ("malicious", "is_malicious", "blocked", "flagged"):
            if k in vres and bool(vres[k]):
                return True

        detections = vres.get("detections")
        if isinstance(detections, list) and len(detections) > 0:
            return True

        results = vres.get("results")
        if isinstance(results, list):
            for r in results:
                if isinstance(r, dict) and (r.get("match") or r.get("blocked") or r.get("flagged")):
                    return True

        return False