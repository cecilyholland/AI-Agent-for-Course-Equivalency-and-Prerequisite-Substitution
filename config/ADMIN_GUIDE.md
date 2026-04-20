# Admin Guide — Decision Policy & Target Courses

This guide is for admins who need to change how the agent makes recommendations
or add new UTC courses the agent can evaluate toward. It does not require any
code changes — just edit the YAML files in this directory and restart the
backend (`uvicorn app.main:app`) for changes to take effect.

## Files

| File | Purpose |
|---|---|
| `policy.yaml` | System-wide decision policy — thresholds and configurable rules |
| `target_courses.yaml` | One entry per UTC course the agent can evaluate toward |

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

## `target_courses.yaml` — Adding a new UTC course

Each entry under `targets:` describes one UTC course an equivalency request can
evaluate toward. The key (e.g., `CPSC-2150`) is the course code. The backend
normalizes user input — `CPSC 2150`, `cpsc2150`, `CPSC-2150` all match this key.

### Schema

```yaml
targets:
  <COURSE-CODE>:
    display_name: str             # human-readable label
    target_credits: int           # expected credit hours
    target_lab_required: bool     # does the course require a lab?
    required_topics: list[str]    # topics the source must cover
    required_outcomes: list[str]  # learning outcomes the source must demonstrate
```

### Example — adding a new course

```yaml
targets:
  CPSC-4240:
    display_name: "Intro to Machine Learning"
    target_credits: 3
    target_lab_required: false
    required_topics:
      - supervised learning
      - unsupervised learning
      - neural networks
      - model evaluation
    required_outcomes:
      - Train and evaluate basic ML models
      - Choose appropriate models for a given task
      - Analyze model performance metrics
```

### Tips

- **Be specific on `required_topics`** — these drive 40% of the equivalency score. Vague entries (e.g., `"programming"`) won't match source syllabi well. Prefer concrete names (e.g., `"linked lists"`, `"SQL"`).
- **Don't over-require.** The scoring is proportional — requiring 10 topics when most syllabi cover 5 will force everything into `APPROVE_WITH_BRIDGE`. Aim for 5-8 required topics.
- **`target_lab_required: true`** triggers the lab-parity rule. Use only for courses that truly require a lab (e.g., Digital Logic, Organic Chemistry).

---

## Verification

After editing either file, confirm the new config is loaded:

```bash
python -c "
from app.main import load_policy_config, load_target_profile
print(load_policy_config().model_dump())
print(load_target_profile('CPSC-2150').model_dump())
"
```
