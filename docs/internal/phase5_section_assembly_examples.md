# Phase 5 Section Assembly Output Example

The Phase 5 section assembly layer is deterministic. It does not choose content strategy or rewrite text. It only turns bounded generation outputs plus the upstream section plan into render-ready section payloads.

## Example structure

```json
{
  "schema_version": "phase5.section.assembly.v1",
  "context_id": "ctx.assembly",
  "source_profile_id": "profile.assembly",
  "assembled_summary": {
    "section_id": "section.summary",
    "title": "Summary",
    "text": "Backend engineer with experience building Python services on AWS."
  },
  "assembled_experience_sections": [
    {
      "section_id": "section.experience",
      "title": "Experience",
      "items": [
        {
          "source_item_id": "exp.1",
          "title": "Senior Backend Engineer",
          "organization": "Acme",
          "bullets": [
            {
              "source_bullet_id": "exp.1.b1",
              "text": "Rewritten exp.1.b1.",
              "evidence_ids_used": ["ev.exp.1.b1"]
            }
          ]
        }
      ]
    }
  ],
  "assembled_project_sections": [],
  "assembled_skill_section": {
    "section_id": "section.skills",
    "title": "Skills",
    "grouped_skills": [
      {
        "group_id": "group.skills.1",
        "label": "Languages",
        "skill_names": ["Python"],
        "source_item_ids": ["skill.python"]
      }
    ],
    "rendered_skill_lines": ["Languages: Python"]
  },
  "assembled_education_section": null,
  "assembled_certification_section": {
    "section_id": "section.certifications",
    "title": "Certifications",
    "items": [
      {
        "source_item_id": "cert.1",
        "name": "AWS Certified Developer",
        "issuer": "Amazon Web Services",
        "details": "Issued 2024-06"
      }
    ]
  },
  "omitted_items_with_reasons": [
    {
      "source_item_id": "proj.1",
      "source_item_type": "project",
      "reason": "space_constraint",
      "detail": "planned bullet omitted because the total page bullet budget was exhausted",
      "source_bullet_ids": ["proj.1.b1"],
      "section_id": "section.projects"
    }
  ],
  "assembly_warnings": [
    "missing rewritten bullet for exp.2.b1; source text was used during assembly"
  ],
  "budget_signals": {
    "target_page_count": 1,
    "max_total_bullets": 8,
    "used_total_bullets": 8,
    "remaining_bullet_budget": 0,
    "within_budget": true,
    "omitted_item_ids": ["proj.1"]
  }
}
```

## Behavioral notes

- Planner-selected section and item order is preserved.
- Bullet truncation is deterministic and traceable through `omitted_items_with_reasons`.
- Missing bullet rewrites do not silently drop content. Assembly falls back to normalized source text and records a warning.
- Education remains `null` until bounded education evidence is added to the Phase 5 context.
