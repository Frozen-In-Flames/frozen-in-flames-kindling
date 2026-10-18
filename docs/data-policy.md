# Data rights policy workstream (Part 4.5)

Rights and licensing policy depends on jurisdiction, sources, and
distribution. This document is the workstream; the license fields in every
data record encode its outcome, and the ledger enforces it.

## Owner

ASSIGNED: TBD. Name the policy owner before the first large training run.
The owner writes the policy, reviews the license ledger quarterly, and
signs off on every training manifest.

## Rules encoded in records

- `license.status`: cleared, pending, restricted, unknown.
- `license.training_allowed`: whether model training is permitted at all.
- `allowed_uses`: derived at ingest. Cleared plus training allowed gives
  train and evaluate. Training allowed without clearance gives evaluate
  only. Anything else gives none.
- `consent.voice_consent_id`: required before any voice in the record can
  back a voice character (Part 8.4, Part 19).
- Deletion requests are honored through `delete_record()`: the item leaves
  every future manifest and its derived assets are listed for cascade.

## Before the first large training run

1. Name the policy owner above.
2. Write the jurisdiction-specific policy and file it here.
3. Review the license ledger summary until every record used for training
   has status cleared.
4. Keep the manifests. Every training run cites its manifest id.
