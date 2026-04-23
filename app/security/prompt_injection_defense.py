# app/security/prompt_injection_defense.py
# Text-based prompt injection detection for PDF-derived text.
# if REJECT, extraction stops before chunking/parsing.

# Handles all 10 red-team cases:
#   RT-01  Prompt injection (regex)
#   RT-02  Adversarial keyword stuffing           → KeywordDensityScanner
#   RT-03  Spoofed credit/contact hour fields     → FieldConsistencyChecker
#   RT-04  Contradictory documents                → CrossDocumentScanner
#   RT-05  Deliberately incomplete syllabus       → DocumentCompletenessChecker
#   RT-06  File upload abuse (wrong magic bytes)  → FileTypeValidator
#   RT-07  Typoglycemia obfuscation               → PromptInjectionFilter.typoglycemia_hits
#   RT-08  Base64-encoded payload                 → PromptInjectionFilter.base64_hits
#   RT-09  Expired course disguised as current    → DateExpirationChecker
#   RT-10  Unicode homoglyph substitution         → PromptInjectionFilter.normalize_homoglyphs

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import re
import base64
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


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
        # direct instruction override
        ("ignore_previous_instructions", r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?"),
        ("forget_previous_instructions", r"forget\s+(all\s+)?(previous|prior)\s+instructions?"),
        ("disregard_instructions", r"disregard\s+(all\s+)?(rules|policies|instructions)"),
        ("follow_only_these", r"follow\s+(only\s+)?these\s+instructions\s+(exactly|instead)"),
        ("treat_as_only_instruction", r"treat\s+this\s+as\s+the\s+only\s+valid\s+instruction"),
        ("override_system", r"(system|agent|model)\s+override"),
        ("override_rules", r"override\s+(safety|policy|policies|rules|instructions)"),
        ("bypass_safety", r"\bbypass\s+(safety|policy|policies|rules|checks)\b"),
        ("developer_mode", r"you\s+are\s+now\s+(in\s+)?developer\s+mode"),
        ("unrestricted_agent", r"act\s+as\s+an?\s+(unrestricted|unfiltered)\s+(agent|model|assistant)"),
        ("jailbreak_directive", r"\bjailbreak\b"),

        # reveal hidden/system information
        ("reveal_prompt", r"(reveal|show|print|leak)\s+(the\s+)?(system\s+)?prompt"),
        ("reveal_hidden_instructions", r"(reveal|show|print|leak)\s+(hidden|internal|confidential)\s+instructions?"),
        ("ignore_safeguards", r"ignore\s+(all\s+)?(safeguards|guardrails|protections)"),

        # direct decision manipulation specific to your app
        ("approve_request", r"(automatically\s+)?approve\s+(this\s+)?(request|course|equivalency|substitution)"),
        ("deny_request", r"(automatically\s+)?deny\s+(this\s+)?(request|course|equivalency|substitution)"),
        ("mark_equivalent", r"(mark|classify|treat)\s+(this\s+course\s+as\s+)?equivalent"),
        ("accept_transfer_credit", r"(accept|grant)\s+(this\s+)?transfer\s+credit"),
        ("grant_prereq_substitution", r"(grant|approve)\s+(this\s+)?prerequisite\s+substitution"),
        ("approve_with_bridge", r"approve\s+with\s+bridge"),
        ("no_review_needed", r"(no\s+further\s+review\s+is\s+needed|reviewer\s+should\s+approve|committee\s+should\s+accept)"),
        ("set_decision_approve", r"(set|return|output)\s+(the\s+)?decision\s+to\s+approve"),
        ("set_decision_deny", r"(set|return|output)\s+(the\s+)?decision\s+to\s+deny"),
        ("set_status_approved", r"set\s+(the\s+)?status\s+to\s+approved"),
    


        # RT-07: Role escalation / privilege claim
        ("role_escalation",
            r"(as\s+(a|an)\s+)?(committee\s+member|admin(istrator)?|advisor|reviewer)"
            r"\s+(with\s+)?(admin|elevated|full|system)\s+(privileges?|access|rights|permissions?)"),
        ("admin_authorize",
            r"(i\s+)?(authorize|sanction|permit)\s+(the\s+)?(approval|grant|acceptance)\s+of\s+this"),
        ("admin_access_claim",
            r"\b(admin|administrator|privileged\s+user)\s+(has\s+)?(approved?|granted?|authorized?)"),
 
        # RT-08: Confidence / score manipulation
        ("confidence_manipulation",
            r"set\s+confidence\s+(score\s+)?(to\s+)?(1\.0|0?\.9\d|100\s*%|maximum|max)"),
        ("force_high_confidence",
            r"(output|respond|return)\s+with\s+(high|maximum|full)\s+confidence"),
        ("score_override",
            r"(set|force|override)\s+(the\s+)?(score|rating|confidence|similarity)\s+to\s+\d"),
 
        # RT-10: Structural / markup injection
        ("xml_system_tag",              r"<\s*system[_\-]?instruction\s*>"),
        ("json_system_role",            r'"role"\s*:\s*"system"'),
        ("structural_override",
            r"(override|bypass|ignore)\s+(safety|policy|policies|rules|instructions)"
            r".*?(approve|deny|accept|grant|equivalent)"),
    ]

    PATTERNS_MEDIUM: List[Tuple[str, str]] = [
        # prompt-injection terminology
        ("prompt_injection_term", r"\bprompt\s+injection\b"),
        ("system_prompt_term", r"\bsystem\s+prompt\b"),
        ("developer_message_term", r"\bdeveloper\s+message\b"),
        ("hidden_prompt_term", r"\bhidden\s+prompt\b"),

        # output coercion
        ("output_only", r"(output|respond|return)\s+only\s+['\"]?(approve|deny|needs\s+more\s+info|approve\s+with\s+bridge)['\"]?"),
        ("do_not_explain", r"do\s+not\s+(explain|justify|mention)"),
        ("only_final_answer", r"(provide|give)\s+only\s+the\s+final\s+answer"),

        # decision language that is suspicious in context
        ("recommend_approval", r"recommend\s+(approval|approve)"),
        ("recommend_denial", r"recommend\s+(denial|deny)"),
        ("count_as_equivalent", r"count\s+(this\s+course\s+)?as\s+equivalent"),
        ("meets_requirement", r"(treat|consider)\s+this\s+as\s+meeting\s+the\s+requirement"),
        ("auto_accept", r"(auto|automatic|automatically)\s+(accept|approve)"),

        # RT-07 medium variants
        ("no_review_medium",         r"(skip|omit|remove)\s+(the\s+)?(review|approval\s+step|committee\s+review)"),
        ("i_authorize",              r"\bi\s+authorize\s+(this|the)"),

        # RT-08 medium variants
        ("force_approve_confidence", r"(mark|flag|label)\s+(as\s+)?(high[- ]confidence|certain|definitive)"),
        ("suppress_uncertainty",     r"(do\s+not|don'?t)\s+(show|include|mention)\s+(uncertainty|confidence|caveat)"),
 
        # RT-10 medium variants
        ("fake_json_instruction",    r'"(content|instruction|command)"\s*:\s*"[^"]{5,}"'),
        ("bracket_command",          r"\[\s*(SYSTEM|INST|INSTRUCTION|CMD|COMMAND)\s*:"),
    ]

    FUZZY_KEYWORDS: List[str] = [
        # core control words
        "ignore",
        "bypass",
        "override",
        "reveal",
        "system",
        "prompt",
        "instruction",
        "directive",
        "policy",

        # decision manipulation words
        "approve",
        "deny",
        "accept",
        "reject",
        "decision",
        "reviewer",
        "equivalent",
        "equivalency",
        "substitution",
        "automatic",
        "automatically",
        "grant",
        "authorize",
        "confidence",
    ]

    TRIGGER_WORDS: List[str] = [
            "ignore",
            "override",
            "bypass",
            "reveal",
            "prompt",
            "developer",
            "directive",
            "instruction",
            "instructions",
            "reviewer",
            "committee",
            "advisor",
            "approve",
            "deny",
            "accept",
            "reject",
            "decision",
            "automatic",
            "automatically",
            "grant",
            "hidden",
            "confidential",
            "internal",
            "privileged", 
            "admin", 
            "administrator", 
            "confidence", 
            "score",
            "equivalent", 
            "equivalency", 
            "substitution",
        ]
    
    # Homoglyph Mapping, common Greek/Cyrillic letters that look like Latin ones
    _HOMOGLYPH_MAP: Dict[str, str] = {
        "\u0430": "a",   # Cyrillic а
        "\u0435": "e",   # Cyrillic е
        "\u043e": "o",   # Cyrillic о
        "\u0440": "r",   # Cyrillic р
        "\u0441": "c",   # Cyrillic с
        "\u0445": "x",   # Cyrillic х
        "\u0456": "i",   # Cyrillic і
        "\u0443": "y",   # Cyrillic у
        "\u03b1": "a",   # Greek α
        "\u03bf": "o",   # Greek ο
        "\u03c1": "r",   # Greek ρ
        "\u0399": "I",   # Greek Ι
        "\u03a1": "P",   # Greek Ρ
        "\u00e0": "a",   # Latin à (accent)
        "\u00e9": "e",   # Latin é
        "\u00f3": "o",   # Latin ó
    }

        # Precompile zero-width / invisible character pattern
    _ZW_PATTERN = re.compile(
        r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u034f\u2060\u2061\u2062\u2063]"
    )
 
    # Precompile base64 candidate pattern (≥ 20 base64 chars with padding)
    _B64_PATTERN = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


# remove zero-width chars that might be used to obfuscate patterns (RT-05)
    def strip_zero_width(self, text: str) -> str:
        return self._ZW_PATTERN.sub("", text)
 

 # Replace base64-encoded payloads with a placeholder (RT-08)
    def normalize_homoglyphs(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        return "".join(self._HOMOGLYPH_MAP.get(ch, ch) for ch in text)


# Collapse whitespace/newlines and tame long repetition
    def normalize_for_scan(self, text: str) -> str:
        t = self.strip_zero_width(text or "")
        t = self.normalize_homoglyphs(t)
        t = re.sub(r"\s+", " ", t)
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


    def trigger_word_hits(self, text: str) -> List[str]:
        words = re.findall(r"\b\w+\b", (text or "").lower())
        word_set = set(words)
        return sorted([w for w in self.TRIGGER_WORDS if w in word_set])


    def typoglycemia_hits(self, text: str) -> List[Tuple[str, str]]:
        hits: List[Tuple[str, str]] = []
        words = re.findall(r"\b\w+\b", (text or "").lower())
        for w in words:
            for target in self.FUZZY_KEYWORDS:
                if self._is_typoglycemia_variant(w, target):
                    hits.append((w, target))
        return hits
    

# RT-08: Find base64 blobs, decode, and scan decoded text for patterns
    def base64_hits(self, raw_text: str) -> List[Tuple[str, str]]:
        suspicious: List[Tuple[str, str]] = []
        for m in self._B64_PATTERN.finditer(raw_text):
            blob = m.group(0)
            # Pad to valid length before decoding
            padded = blob + "=" * (-len(blob) % 4)
            try:
                decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
            except Exception:
                continue
            # Only flag if decoded text looks like prose (printable, >= 10 chars)
            if len(decoded) >= 10 and decoded.isprintable():
                normalised = self.normalize_for_scan(decoded)
                if self.regex_hits(normalised) or self.trigger_word_hits(normalised):
                    suspicious.append((blob, decoded))
        return suspicious
    

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
        reject_threshold: int = 10,
        points_high_regex: int = 5,
        points_medium_regex: int = 3,
        points_typoglycemia: int = 2,
        points_trigger_word: int = 1,
        points_multi_hit_bonus: int = 2,
        max_trigger_hits_per_page: int = 10,
        max_findings: int = 50,
    ) -> None:
        self.filter = PromptInjectionFilter()

        self.reject_threshold = int(reject_threshold)
        self.points_high_regex = int(points_high_regex)
        self.points_medium_regex = int(points_medium_regex)
        self.points_typoglycemia = int(points_typoglycemia)
        self.points_trigger_word = int(points_trigger_word)
        self.points_multi_hit_bonus = int(points_multi_hit_bonus)
        self.max_trigger_hits_per_page = int(max_trigger_hits_per_page)
        self.max_findings = int(max_findings)
        self.points_base64 = 6

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
            b64_hits = self.filter.base64_hits(raw or "")
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


                        # 2) Trigger-word hits (low severity)
            trigger_hits = self.filter.trigger_word_hits(scan_text)[: self.max_trigger_hits_per_page]
            for trig in trigger_hits:
                detected_any = True
                page_signals += 1

                pts = self.points_trigger_word
                page_points += pts

                findings.append(
                    Finding(
                        detector="trigger_word",
                        page_num=page_num,
                        severity="low",
                        points=pts,
                        match=trig,
                        snippet=scan_text[:180],
                        detail={},
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

            for blob, decoded in b64_hits:
                detected_any = True
                page_signals += 1
                pts = self.points_base64
                page_points += pts
                findings.append(Finding(
                    detector="base64_decode", page_num=page_num, severity="high",
                    points=pts, match="base64_encoded_injection",
                    snippet=blob[:60] + "…",
                    detail={"decoded_preview": decoded[:120]},
                ))
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

        detected = detected_any or any(f.detector in ("regex", "trigger_word", "typoglycemia", "base64_decode") for f in findings)

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
    

# Separate metadata scanning that can be called before page-level scanning.
# Metadata injection is reported with page_num=0 to indicate non-page origin.
# Metadata findings are weighted the same as page findings.
    def scan_metadata(self, metadata: Dict[str, Any]) -> ScanResult:
        combined = " ".join(
            str(v) for v in metadata.values() if v is not None
        )
        # Reuse scan_pages on a single synthetic "page 0" chunk
        raw_result = self.scan_pages([combined])
 
        # Re-tag findings with page_num=0 to flag metadata origin
        retagged = [
            Finding(
                detector=f.detector, page_num=0, severity=f.severity,
                points=f.points, match=f.match,
                snippet=f.snippet, detail={**f.detail, "source": "metadata"},
            )
            for f in raw_result.findings
        ]
        return ScanResult(
            detected=raw_result.detected,
            decision=raw_result.decision,
            total_score=raw_result.total_score,
            findings=retagged,
        )
    
# RT-06 FileTypeValidator - check magic bytes of uploaded file before processing
@dataclass(frozen=True)
class FileTypeResult:
    is_valid: bool
    declared_extension: str   # ".pdf"
    detected_type: str        # "pdf", "zip", "jpeg", "unknown"
    detail: str
 
 # Validate uploaded files by inspecting magic bytes, not just the extension.
 # result = FileTypeValidator().validate(Path("upload.pdf"))
# if not result.is_valid:
# reject the upload
class FileTypeValidator:
 
    # (magic_bytes_prefix, detected_type_label)
    _SIGNATURES: List[Tuple[bytes, str]] = [
        (b"%PDF",             "pdf"),
        (b"\xff\xd8\xff",    "jpeg"),
        (b"\x89PNG\r\n",     "png"),
        (b"GIF87a",          "gif"),
        (b"GIF89a",          "gif"),
        (b"PK\x03\x04",      "zip"),   # also docx, xlsx, pptx
        (b"\xd0\xcf\x11\xe0","ole"),   # legacy .doc / .xls
        (b"%!PS",            "postscript"),
        (b"\x25\x50\x44\x46", "pdf"),  # alternate PDF sig
    ]
 
    # Which detected types are acceptable for each declared extension
    _ALLOWED: Dict[str, List[str]] = {
        ".pdf":  ["pdf"],
        ".jpg":  ["jpeg"],
        ".jpeg": ["jpeg"],
        ".png":  ["png"],
        ".gif":  ["gif"],
        ".docx": ["zip"],
        ".xlsx": ["zip"],
        ".pptx": ["zip"],
    }
 
 # Returns FileTypeResult with is_valid=False if extension is not allowed or magic bytes don't match expected type.
    def validate(self, file_path: Path) -> FileTypeResult:
        declared_ext = file_path.suffix.lower()
 
        try:
            with open(file_path, "rb") as fh:
                header = fh.read(16)
        except OSError as exc:
            return FileTypeResult(
                is_valid=False,
                declared_extension=declared_ext,
                detected_type="unreadable",
                detail=f"Could not read file: {exc}",
            )
 
        detected = self._detect(header)
        allowed = self._ALLOWED.get(declared_ext, [])
 
        if not allowed:
            return FileTypeResult(
                is_valid=False,
                declared_extension=declared_ext,
                detected_type=detected,
                detail=f"Extension '{declared_ext}' is not in the permitted list.",
            )
 
        is_valid = detected in allowed
        detail = (
            f"OK — declared '{declared_ext}', detected '{detected}'."
            if is_valid
            else f"MISMATCH — declared '{declared_ext}' but magic bytes indicate '{detected}'."
        )
        return FileTypeResult(
            is_valid=is_valid,
            declared_extension=declared_ext,
            detected_type=detected,
            detail=detail,
        )
 
    def _detect(self, header: bytes) -> str:
        for sig, label in self._SIGNATURES:
            if header.startswith(sig):
                return label
        return "unknown"
    
# RT-05 DocumentCompletenessChecker
# heuristic checks for signs of truncated or incomplete documents, which may indicate an attempt 
# to hide malicious content in the missing parts. 
# This could include checking for: 
#   abrupt endings, missing expected sections (like a syllabus missing a grading policy)
#   or metadata indicating the document was edited/saved in a way that suggests tampering.
@dataclass
class CompletenessResult:
    is_complete: bool
    score: float                    # 0.0 – 1.0
    present_fields: List[str]
    missing_fields: List[str]
    detail: str
 
 
#     Check that a submitted syllabus contains the minimum fields required for a course equivalency decision.
 # All fields are detected by regex over the full concatenated text. Adjust ``required_fields`` to match your policy engine's expectations.
 #  result = DocumentCompletenessChecker().check(pages_text)
        #if not result.is_complete:
            # flag as incomplete; decision engine should return NEEDS_MORE_INFO
class DocumentCompletenessChecker:

 
    # (field_name, regex_pattern)
    # A field is "present" if its pattern matches anywhere in the document.
    REQUIRED_FIELDS: List[Tuple[str, str]] = [
        ("course_title",
            r"(course\s+(title|name|number)|[A-Z]{2,6}\s*\d{3,4})"),
        ("credit_hours",
            r"\b(\d+(\.\d+)?)\s*(credit|semester|unit)s?\b"),
        ("instructor",
            r"(instructor|professor|faculty|taught\s+by|dr\.?|prof\.?)\s+\w+"),
        ("learning_outcomes",
            r"(learning\s+outcome|student\s+learning|course\s+objective|upon\s+completion)"),
        ("weekly_topics",
            r"(week\s*\d+|schedule|course\s+outline|topic\s+list|module\s+\d+)"),
        ("assessment_breakdown",
            r"(grading|assessment|exam|quiz|midterm|final|assignment)\s*[\:\-\—]?\s*\d{1,3}\s*%"),
        ("contact_hours",
            r"\b(\d+(\.\d+)?)\s*(contact|lecture|lab|hour)s?\s+(per\s+week|per\s+semester|weekly|total)"),
        ("institution_name",
            r"(university|college|institute|school)\s+of\s+\w+|\w+\s+(university|college|institute)"),
    ]
 
    # Completeness threshold — fraction of required fields that must be present
    COMPLETENESS_THRESHOLD: float = 0.75
 
    def check(self, pages_text: List[str]) -> CompletenessResult:
        full_text = " ".join(pages_text or [])
        normalised = re.sub(r"\s+", " ", full_text).lower()
 
        present, missing = [], []
        for field_name, pattern in self.REQUIRED_FIELDS:
            if re.search(pattern, normalised, re.IGNORECASE):
                present.append(field_name)
            else:
                missing.append(field_name)
 
        score = len(present) / len(self.REQUIRED_FIELDS) if self.REQUIRED_FIELDS else 1.0
        is_complete = score >= self.COMPLETENESS_THRESHOLD
 
        detail = (
            f"Completeness {score:.0%} ({len(present)}/{len(self.REQUIRED_FIELDS)} fields). "
            + (f"Missing: {', '.join(missing)}." if missing else "All required fields present.")
        )
        return CompletenessResult(
            is_complete=is_complete,
            score=round(score, 3),
            present_fields=present,
            missing_fields=missing,
            detail=detail,
        )
    
# RT-09 DateExpirationChecker - detect if a syllabus is outdated/expired based on date references in the text.
# Extract years from document text and metadata, then flag if the course appears to be older than the configured cutoff.
@dataclass
class ExpirationResult:
    is_expired: bool
    years_found: List[int]
    most_recent_year: Optional[int]
    cutoff_year: int
    detail: str
 
 
class DateExpirationChecker:
    # Regex for 4-digit years in a plausible academic range
    _YEAR_PATTERN = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
 
    def __init__(self, max_age_years: int = 10) -> None:
        self.max_age_years = max_age_years
 
    def check(
        self,
        pages_text: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExpirationResult:
        current_year = datetime.now(tz=timezone.utc).year
        cutoff_year  = current_year - self.max_age_years
 
        # Collect all year mentions from page text
        all_text = " ".join(pages_text or [])
        if metadata:
            all_text += " " + " ".join(str(v) for v in metadata.values() if v)
 
        years_found = [
            int(m.group()) for m in self._YEAR_PATTERN.finditer(all_text)
        ]
 
        if not years_found:
            return ExpirationResult(
                is_expired=False,
                years_found=[],
                most_recent_year=None,
                cutoff_year=cutoff_year,
                detail="No years found in document — cannot determine recency.",
            )
 
        most_recent = max(years_found)
        is_expired  = most_recent < cutoff_year
 
        detail = (
            f"Most recent year found: {most_recent}. "
            f"Cutoff: {cutoff_year} ({self.max_age_years}-year policy). "
            + ("EXPIRED — course predates recency window." if is_expired
               else "Within recency window.")
        )
        return ExpirationResult(
            is_expired=is_expired,
            years_found=sorted(set(years_found)),
            most_recent_year=most_recent,
            cutoff_year=cutoff_year,
            detail=detail,
        )
    
# RT-02 Keyword Stuffing
# Detect syllabi stuffed with UTC-course or equivalency keywords to game the
# decision engine. Look for unusually high density of keywords, especially if repeated unnaturally.
@dataclass
class DensityResult:
    is_suspicious: bool
    density: float              # flagged_keywords / total_words
    top_offenders: List[Tuple[str, int]]   # (word, count) sorted desc
    repeated_phrases: List[str]            # exact phrases seen 3+ times
    detail: str
 
 
class KeywordDensityScanner:
 
    # Words that carry outsized weight in equivalency scoring
    TARGET_KEYWORDS: List[str] = [
        "equivalent", "equivalency", "prerequisite", "substitution",
        "learning outcome", "credit hour", "contact hour",
        "pathology", "anatomy", "physiology", "microbiology",
        "biochemistry", "epidemiology", "immunology",
        "cell biology", "genetics", "molecular biology",
        "approved", "meets requirement", "satisfies",
    ]
 
    # Density threshold — flagged keyword occurrences / total words
    DENSITY_THRESHOLD: float = 0.04     # 4 %
 
    # Phrase repetition threshold — flag if an exact phrase appears >= N times
    PHRASE_REPEAT_THRESHOLD: int = 3
 
    def scan(self, pages_text: List[str]) -> DensityResult:
        full_text = " ".join(pages_text or [])
        words     = re.findall(r"\b\w+\b", full_text.lower())
        total     = len(words) or 1
 
        # Count single-word keyword hits
        word_counts: Counter = Counter(words)
        single_kw = [kw for kw in self.TARGET_KEYWORDS if " " not in kw]
        multi_kw  = [kw for kw in self.TARGET_KEYWORDS if " " in kw]
 
        flagged_count = sum(word_counts[kw] for kw in single_kw)
        top_offenders = sorted(
            [(kw, word_counts[kw]) for kw in single_kw if word_counts[kw] > 0],
            key=lambda x: x[1], reverse=True,
        )[:10]
 
        # Count multi-word phrase hits
        repeated_phrases: List[str] = []
        for phrase in multi_kw:
            occurrences = len(re.findall(re.escape(phrase), full_text, re.IGNORECASE))
            flagged_count += occurrences
            if occurrences >= self.PHRASE_REPEAT_THRESHOLD:
                repeated_phrases.append(f'"{phrase}" x{occurrences}')
 
        # Check for any phrase repeated suspiciously often
        sentences = re.split(r"[.!?\n]", full_text)
        sentence_counter: Counter = Counter(
            s.strip().lower() for s in sentences if len(s.strip()) > 20
        )
        for sent, cnt in sentence_counter.items():
            if cnt >= self.PHRASE_REPEAT_THRESHOLD:
                repeated_phrases.append(f'"{sent[:60]}…" x{cnt}')
 
        density = flagged_count / total
        is_suspicious = (
            density >= self.DENSITY_THRESHOLD or bool(repeated_phrases)
        )
 
        detail = (
            f"Keyword density: {density:.2%} (threshold {self.DENSITY_THRESHOLD:.0%}). "
            + (f"Repeated phrases detected: {'; '.join(repeated_phrases[:5])}." if repeated_phrases
               else "No suspicious phrase repetition.")
        )
        return DensityResult(
            is_suspicious=is_suspicious,
            density=round(density, 4),
            top_offenders=top_offenders,
            repeated_phrases=repeated_phrases,
            detail=detail,
        )
    
# RT-03 Fied Consistency Checker
# Check for internal consistency of key fields across the document. 
# For example, if a syllabus lists multiple course titles or credit hours, 
# that may indicate an attempt to confuse the decision engine.
@dataclass
class ConsistencyResult:
    is_suspicious: bool
    credit_hours_found: List[float]
    contact_hours_found: List[float]
    issues: List[str]
    detail: str
 
 
class FieldConsistencyChecker:

 
    CREDIT_PATTERN  = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:semester\s+)?credit(?:\s+hour)?s?", re.IGNORECASE
    )
    CONTACT_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?)\s*contact\s+hours?(?:\s+per\s+week)?", re.IGNORECASE
    )
 
    # Plausible value ranges
    CREDIT_MIN,  CREDIT_MAX  = 1.0, 6.0
    CONTACT_MIN, CONTACT_MAX = 1.0, 10.0
 
    def check(self, pages_text: List[str]) -> ConsistencyResult:
        full_text = " ".join(pages_text or [])
        issues: List[str] = []
 
        credits  = [float(m) for m in self.CREDIT_PATTERN.findall(full_text)]
        contacts = [float(m) for m in self.CONTACT_PATTERN.findall(full_text)]
 
        # Out-of-range checks
        for val in credits:
            if not (self.CREDIT_MIN <= val <= self.CREDIT_MAX):
                issues.append(f"Credit hour value {val} is outside plausible range "
                               f"({self.CREDIT_MIN}–{self.CREDIT_MAX}).")
 
        for val in contacts:
            if not (self.CONTACT_MIN <= val <= self.CONTACT_MAX):
                issues.append(f"Contact hour value {val} is outside plausible range "
                               f"({self.CONTACT_MIN}–{self.CONTACT_MAX}).")
 
        # Internal consistency — flag if multiple distinct credit values appear
        unique_credits = set(credits)
        if len(unique_credits) > 1:
            issues.append(
                f"Inconsistent credit hour values within document: {sorted(unique_credits)}."
            )
 
        unique_contacts = set(contacts)
        if len(unique_contacts) > 1:
            issues.append(
                f"Inconsistent contact hour values within document: {sorted(unique_contacts)}."
            )
 
        is_suspicious = bool(issues)
        detail = "; ".join(issues) if issues else (
            f"Fields consistent. Credits: {sorted(unique_credits) or 'not found'}. "
            f"Contact hours: {sorted(unique_contacts) or 'not found'}."
        )
        return ConsistencyResult(
            is_suspicious=is_suspicious,
            credit_hours_found=credits,
            contact_hours_found=contacts,
            issues=issues,
            detail=detail,
        )
    
# RT-04 Cross-Document Reference Checker
# Detect if a syllabus references external documents (e.g. "see attached") that may contain
@dataclass
class CrossDocumentResult:
    has_contradictions: bool
    contradictions: List[str]
    document_summaries: List[Dict[str, Any]]
    detail: str
 
 
class CrossDocumentScanner:
 
    _CREDIT_PAT  = re.compile(r"(\d+(?:\.\d+)?)\s*(?:semester\s+)?credit(?:\s+hour)?s?", re.IGNORECASE)
    _CONTACT_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*contact\s+hours?", re.IGNORECASE)
    _YEAR_PAT    = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
    _COURSE_PAT  = re.compile(r"\b([A-Z]{2,6})\s*(\d{3,4})\b")
 
    def scan(self, documents: List[Tuple[str, List[str]]]) -> CrossDocumentResult:
        """
        Args:
            documents: list of (doc_name, pages_text) tuples.
        """
        if len(documents) < 2:
            return CrossDocumentResult(
                has_contradictions=False,
                contradictions=[],
                document_summaries=[],
                detail="Cross-document scan requires at least 2 documents.",
            )
 
        summaries: List[Dict[str, Any]] = []
        for doc_name, pages in documents:
            full = " ".join(pages or [])
            summaries.append({
                "name":          doc_name,
                "credits":       set(float(v) for v in self._CREDIT_PAT.findall(full)),
                "contact_hours": set(float(v) for v in self._CONTACT_PAT.findall(full)),
                "years":         set(int(m.group()) for m in self._YEAR_PAT.finditer(full)),
                "course_codes":  set(m.group() for m in self._COURSE_PAT.finditer(full)),
            })
 
        contradictions: List[str] = []
 
        # Compare every pair of documents
        for i in range(len(summaries)):
            for j in range(i + 1, len(summaries)):
                a, b = summaries[i], summaries[j]
                name_pair = f"'{a['name']}' vs '{b['name']}'"
 
                # Credit hours
                if a["credits"] and b["credits"] and not a["credits"] & b["credits"]:
                    contradictions.append(
                        f"{name_pair}: conflicting credit hours "
                        f"{sorted(a['credits'])} vs {sorted(b['credits'])}."
                    )
 
                # Contact hours
                if a["contact_hours"] and b["contact_hours"] \
                        and not a["contact_hours"] & b["contact_hours"]:
                    contradictions.append(
                        f"{name_pair}: conflicting contact hours "
                        f"{sorted(a['contact_hours'])} vs {sorted(b['contact_hours'])}."
                    )
 
                # Year ranges — flag if completely non-overlapping
                if a["years"] and b["years"] and not a["years"] & b["years"]:
                    contradictions.append(
                        f"{name_pair}: non-overlapping year ranges "
                        f"{sorted(a['years'])} vs {sorted(b['years'])}."
                    )
 
                # Course codes — flag if both have codes and they share none
                if a["course_codes"] and b["course_codes"] \
                        and not a["course_codes"] & b["course_codes"]:
                    contradictions.append(
                        f"{name_pair}: no common course codes — "
                        f"may describe different courses."
                    )
 
        detail = (
            f"{len(contradictions)} contradiction(s) found across {len(documents)} documents."
            if contradictions else
            f"No contradictions found across {len(documents)} documents."
        )
        # Serialise sets to sorted lists for JSON compatibility
        for s in summaries:
            for k in ("credits", "contact_hours", "years", "course_codes"):
                s[k] = sorted(s[k])
 
        return CrossDocumentResult(
            has_contradictions=bool(contradictions),
            contradictions=contradictions,
            document_summaries=summaries,
            detail=detail,
        )