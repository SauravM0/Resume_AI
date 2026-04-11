# Phase 7 Evaluation Dataset Guide

This directory contains evaluation packs for Phase 7 regression testing. The schema supports human authors writing cases in YAML or JSON without deep familiarity with the code.

## Pack Types

| Pack Type | Description | Required Inputs | Expected Outputs |
|----------|------------|-----------------|----------------|
| `jd_parse` | JD parsing only | job_description | phase1_expectations |
| `selection` | Ranking & selection | job_description + profile | selection_expectations |
| `end_to_end` | Full pipeline | job_description + profile | end_to_end_expectations |
| `red_team` | Adversarial tests | varies | varies |

## Directory Structure

```
fixtures/evaluation/
├── jd_parse/          # JD parsing regression cases
├── selection/         # Selection regression cases
├── end_to_end/        # End-to-end regression cases
└── red_team/          # Adversarial cases
```

## Writing Evaluation Cases

### Basic Structure

```yaml
pack_id: my_pack_id
pack_type: jd_parse  # or selection, end_to_end, red_team
description: What this pack tests

cases:
  - case_id: UNIQUE-001
    description: Human-readable description
    pack_type: jd_parse
    
    # Input: job description text
    job_description:
      raw_text: |
        Your job description here...
    
    # Expected outputs
    phase1_expectations:
      expected_job_title: Software Engineer
      expected_role_family: backend
      expected_seniority: senior
```

### Expected Output Types

The schema supports four expectation types:

1. **must_include**: The output MUST contain this value (fail if missing)
   ```yaml
   - type: must_include
     value: Python
     weight: 1.0
   ```

2. **must_not_include**: The output MUST NOT contain this value (fail if present)
   ```yaml
   - type: must_not_include
     value: React
     weight: 1.0
     reason: Backend role should not have frontend
   ```

3. **prefer_include**: Should contain this value (partial credit)
   ```yaml
   - type: prefer_include
     value: Kubernetes
     weight: 0.7
   ```

4. **acceptable_alternative**: Multiple valid answers (flexible matching)
   ```yaml
   - type: acceptable_alternative
     value: PostgreSQL
     match_mode: fuzzy
     weight: 0.8
   ```

### Match Modes

| Mode | Description |
|------|------------|
| `exact` | Exact string match |
| `fuzzy` | Fuzzy/case-insensitive match |
| `subset` | All expected values must be present |
| `superset` | Expected value among possible ones |

### Tags for Categorization

Use tags to categorize cases:

```yaml
tags:
  - backend          # role family
  - senior          # seniority level
  - system_design   # edge case type
  - noisy_jd       # quality issue
```

Recommended tag prefixes:
- Role family: `backend`, `frontend`, `fullstack`, `data`, `ml`, `platform`, `management`
- Seniority: `junior`, `mid`, `senior`, `staff`, `principal`, `director`
- Edge cases: `noisy_jd`, `sparse_profile`, `generic_jd`, `ambiguous_title`

### Profile References (for selection/end_to_end)

```yaml
profile:
  path: ../../profiles/senior_backend.json  # relative to this pack file
  summary: 5 years Python, distributed systems
```

## Templates

For packs with many similar cases, define reusable templates:

```yaml
pack_id: my_pack
pack_type: jd_parse
description: Test pack with templates

# Define templates
templates:
  base_backend:
    tags:
      - backend
    phase1_expectations:
      min_quality_score: 0.70
      min_parser_confidence: 0.65
  
  senior_scaling:
    expected_seniority: senior
    phase1_expectations:
      expected_skills:
        - type: must_include
          value: scalability
          weight: 1.0

# Use template with _template_ref
cases:
  - case_id: CASE-001
    _template_ref: base_backend
    job_description:
      raw_text: ...JD text...
```

## Validation

Run validation to catch errors:

```python
from resume_optimizer.evaluation.loader import load_evaluation_pack, validate_pack

pack = load_evaluation_pack("fixtures/evaluation/jd_parse/my_pack.yaml")
is_valid, errors = validate_pack(pack)

if not is_valid:
    print("Validation errors:")
    for err in errors:
        print(f"  - {err}")
```

## Loading and Running

```python
from resume_optimizer.evaluation.loader import load_evaluation_pack, validate_pack

# Load a pack
pack = load_evaluation_pack("fixtures/evaluation/jd_parse/backend_senior.yaml")

# Print summary
print(f"Pack: {pack.pack_id}")
print(f"Cases: {len(pack.cases)}")
for case in pack.cases:
    print(f"  - {case.case_id}: {case.description}")
```

## CI Usage

For CI, run:

```bash
python -c "
from resume_optimizer.evaluation.loader import load_all_packs
from pathlib import Path

packs = load_all_packs(Path('fixtures/evaluation'))
total_cases = sum(len(p.cases) for p in packs)
print(f'Loaded {len(packs)} packs with {total_cases} cases')
"
```

## Phase 7 Workflow Integration

The repository-level workflow entrypoint is:

```bash
PYTHONPATH=.:src python3 scripts/run_phase7.py run_all_phase7 --mode ci-safe
```

Key distinction:

- `selection` is deterministic and confidence-bearing in CI-safe mode
- `jd_parse`, `end_to_end`, and `red_team` require live model access for real quality confidence
- non-live runs of `end_to_end` and `red_team` are smoke-only and should never be interpreted as live-quality proof

For `selection`, CI-safe status now has two separate meanings that are both enforced:

- `regression guardrail`: whether metrics regressed relative to the checked-in baseline
- `absolute quality`: whether the run is actually acceptable product behavior

A stable but bad run must still fail. In practice that means obvious failures such as `0` passed cases, severe pathology rates, zero recall for required projects, or low average relevance are workflow failures, not acceptable passes.

Phase 2 selection authoring notes:

- The selector is two-level by design: it scores atomic evidence first, then optimizes the final experience/project set.
- A good case should test the final resume narrative, not only isolated keyword hits.
- Required projects are valid when they add unique proof, close gaps left by supporting experience, or materially improve the selected-set story.
- Compound requirements such as `REST APIs`, `distributed systems`, `observability`, or `incident response` should be written explicitly in the job text so the deterministic selection eval can measure them.
- Per-item relevance in selection eval is based on final retained utility, not only raw pre-selection aggregate score.

When authoring new cases:

- keep `selection` cases strategy-focused and deterministic
- keep `end_to_end` cases reviewer-visible and artifact-rich
- keep `red_team` cases pessimistic, failure-seeking, and explicit about:
  - the bad behavior being targeted
  - the acceptable fallback behavior
