# Consent, Provenance, Privacy, and Safety (Part 19)

Engineering requirements with acceptance tests, not policy footnotes.

## Voice consent (19.1)

`verify_consent`: recorded, verified consent tied to the person, or
documented rights for licensed/synthetic sources. Blocks named real
persons without verified personal consent. `RevocationRegistry`:
owner revocation takes effect immediately for new renders.

## Watermark and provenance (19.2)

`embed_watermark`: 64-bit spread-spectrum mark in the 2-4 kHz band
(inaudible at low strength). `detect_watermark`: the detection tool,
returning payload bits and confidence. `sign_provenance` /
`verify_provenance`: HMAC-SHA256 metadata. `survival_report`: honest
statement of where the mark survives (re-encoding, resampling, mild
compression) and where it does not (band filtering, pitch-shift,
re-recording).

## Training data governance (19.3)

`DataGovernance`: opt-outs honored, deletion requests processed, and
NO training on user uploads/assets by default. Training requires a
separate, explicit, revocable opt-in per owner.

## User data (19.4)

`UserDataManager`: 365-day retention, owner export, and deletion that
cascades to derived assets, traits, and caches.

## Misuse handling (19.5)

`MisuseMonitor`: counts consent failures and bulk creation attempts
(metadata only, never audio content). Flags repeated failures and
bulk impersonation attempts for limiting. Usage policy and
reporting/takedown channel are documented here; the channel itself is
operational (not code).

## Transparency (19.6) and legal (19.7)

`openness_statement`: exactly what is open (code, Apache-2.0) and what
is not (weights, datasets). The word "open" is used for nothing else.
`legal_policy`: versioned record of counsel review areas per
jurisdiction.
