# Phase 5 Bullet Rewrite Examples

## Backend metric bullet
- Before: `Built Python APIs that reduced latency by 35% on AWS.`
- After: `Built Python APIs on AWS, reducing latency by 35%.`

## Frontend lead bullet
- Before: `Led design system work in React and TypeScript for the web app.`
- After: `Led design system work in React and TypeScript for the web app.`

## DevOps bullet
- Before: `Automated Terraform-based infrastructure deployments in AWS.`
- After: `Automated AWS infrastructure deployments with Terraform.`

## Conservative fallback case
- Before: `Built Python APIs that reduced latency by 35% on AWS.`
- Unsafe model output: `Owned platform architecture in Python and AWS, reducing latency by 50%.`
- Final output: `Built Python APIs that reduced latency by 35% on AWS.`

Review guidance:
- Rewrites may improve clarity and ordering.
- Rewrites must not upgrade ownership, scope, or impact.
- When the model drifts, the module falls back to normalized source text.
