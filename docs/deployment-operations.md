# Deployment and Operations (Part 18)

A professional system is more than a research notebook.

## Job system (18.4)

`JobQueue`: idempotent submission (same key returns the existing
job), retries with backoff budget, cancellation, progress callbacks,
and `recover()` after worker failure (requeues stuck jobs; jobs are
pure functions of params, so a cancelled or failed job never corrupts
the project).

## Staged results (18.2)

`staged_render` yields sketch, then draft, then final, so users can
decide before a full render finishes.

## Local and hosted (18.3)

Tiers: draft/studio run locally, hosted runs remotely. `tier_for`
upgrades the tier when the project exceeds its cap, never downgrades
below requested. The scene, assets, and project bundle move between
tiers without conversion (same format everywhere).

## Stability (18.5)

API versioned (`v1`); behavior stable within the major version.
Deprecation policy: old model versions stay available long enough
for projects to re-render (pinned in the project bundle, Part 15).

## Monitoring (18.6)

`Monitor`: latency p50 per stage, crashes, queue depth, cost per
generation, quality regressions. Automatic Part 17 checks run on a
sample of production renders, only on data the user agreed to share.

## Security (18.7)

`AccessControl`: per-user grants on projects/assets/profiles,
audit-logged access to sensitive assets (voice characters),
per-account rate limiting. Uploads and projects encrypted in transit
and at rest (transport responsibility; the access model is here).

## Inference (18.1)

Efficient inference via the distilled students (Part 9) and the
draft-tier reference renderer. Quantization/distillation only where
Part 17 tests show no unacceptable quality loss (the distillation
audit is the gate).
