# Admin Guide — Decision Policy

This guide is for admins who need to change how the agent makes recommendations.
It does not require any code changes — just edit `policy.yaml` in this directory
and restart the backend (`uvicorn app.main:app`) for changes to take effect.

---

## `policy.yaml` — Decision policy

### Decision bands

The agent emits one of four recommendations (APPROVE / APPROVE_WITH_BRIDGE /
NEEDS_MORE_INFO / DENY) based on a 0-100 equivalency score. The bands are:

| Field | Default | Effect |
|---|---:|---|
| `approve_threshold` | 90 | Score ≥ this → `APPROVE` |
| `bridge_threshold` | 80 | Score ≥ this (and < approve) → `APPROVE_WITH_BRIDGE` |
| `needs_info_threshold` | 70 | Score ≥ this (and < bridge) → `NEEDS_MORE_INFO` |
| below `needs_info_threshold` | — | → `DENY` |

**To tighten approvals** (more conservative agent), raise `approve_threshold`
to 92 or 95. **To loosen**, lower it to 85.

### Behavior toggles

| Field | Default | Effect when true |
|---|---|---|
| `require_lab_parity` | `true` | If target requires a lab, source must show a lab component (else FIXABLE gap + bridge). |
| `require_credits_known` | `true` | Missing source credits forces `NEEDS_MORE_INFO`. |
| `require_topics_or_outcomes` | `true` | If both topics AND outcomes are unknown, force `NEEDS_MORE_INFO`. |

### Configurable hard rules (default off)

These are optional rules that act as **veto conditions** — if enabled and
violated, the decision is forced to `DENY`. If enabled but the required
evidence is unknown, it is forced to `NEEDS_MORE_INFO`. Leave at their defaults
to disable.

| Field | Default | Example value | Effect |
|---|---|---|---|
| `min_grade` | `null` (off) | `"C"` | Source grade must be at least this letter (A, A-, B+, ..., F). Needs transcript data. |
| `min_contact_hours` | `0` (off) | `45` | `contact_hours_lecture + contact_hours_lab` must be ≥ this. |
| `max_course_age_years` | `0` (off) | `10` | `term_taken` must be within this many years of the current year. Needs transcript data. |
| `must_include_topics` | `[]` (off) | `["ethics", "capstone"]` | Each listed topic must appear in the source course's topics. |

### Example — stricter policy for graduate-level equivalency

```yaml
approve_threshold: 92
bridge_threshold: 82
needs_info_threshold: 75

require_lab_parity: true
require_credits_known: true
require_topics_or_outcomes: true

min_grade: "B"              # grad courses require B or better
min_contact_hours: 40
max_course_age_years: 7     # grad courses must be within 7 years
must_include_topics: []
```

---

## Verification

After editing, you can confirm the new policy is loaded:

```bash
python -c "from app.main import load_policy_config; print(load_policy_config().model_dump())"
```

---

## Future work — per-target course profiles

The agent currently uses a permissive default target profile (3 credits, no lab,
no required topics or outcomes). Per-target customization (e.g., "CPSC-2150
Data Structures requires these specific topics") is handled by the GPT system
prompt rather than a per-course config file. If the team later wants to add
structured per-course profiles with required topics/outcomes lists, that can be
reintroduced as a `target_courses.yaml` in this directory.
