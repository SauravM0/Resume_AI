Selection Evaluation Summary
Cases: 3 | Passed: 0 | Failed: 3
Averages: exp P/R=0.67/1.00, proj P/R=1.00/0.00, bullet P/R=0.56/1.00, skills=0.92, diversity=1.00, pathology_rate=1.00

[FAIL] SEL-001-backend-platform-strength overall=0.747 exp=0.67/1.00 proj=1.00/0.00 bullet=0.57/1.00 skills=1.00 diversity=1.00
  - experience violated exclusion: Frontend Developer @ PixelCraft -> Frontend Developer @ PixelCraft
  - project missing required expectation: Multi-Region Event Pipeline
  - bullet violated exclusion: jQuery admin UI -> Frontend Developer @ PixelCraft: Maintained a jQuery admin UI and shipped marketing site updates for seasonal campaigns.
  - project recall 0.00 below 0.50
  - average selected relevance 0.47 below 0.65
  - pathology: irrelevant old experience was included
[FAIL] SEL-002-recent-backend-over-legacy-java overall=0.727 exp=0.67/1.00 proj=1.00/0.00 bullet=0.60/1.00 skills=0.88 diversity=1.00
  - experience violated exclusion: Java Developer @ LegacyBank -> Java Developer @ LegacyBank
  - project missing required expectation: Billing API Migration
  - bullet violated exclusion: Struts monolith -> Java Developer @ LegacyBank: Maintained a Struts monolith and handled defect tickets for internal banking workflows.
  - skill missing required expectation: REST APIs
  - project recall 0.00 below 0.50
  - average selected relevance 0.44 below 0.60
  - pathology: irrelevant old experience was included
[FAIL] SEL-003-platform-breadth-balance overall=0.712 exp=0.67/1.00 proj=1.00/0.00 bullet=0.50/1.00 skills=0.88 diversity=1.00
  - experience violated exclusion: Web Developer @ Campus Labs -> Web Developer @ Campus Labs
  - project missing required expectation: Developer Provisioning Platform
  - bullet violated exclusion: WordPress sites -> Web Developer @ Campus Labs: Maintained WordPress sites and campus marketing pages for event promotions.
  - project recall 0.00 below 0.50
  - average selected relevance 0.45 below 0.62
  - pathology: irrelevant old experience was included