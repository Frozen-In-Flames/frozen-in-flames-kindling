# Voice Characters (Part 8)

A voice character is a reusable asset: the identity of a voice, separated
from any particular performance. Build it once from reference material,
then render many songs with it. The character carries the identity; the
performance carries the song.

## The asset

A voice character stores:

- **identity**: the identity vector (timbre statistics, range, dynamics,
  vowel space) extracted from the reference. Stable across performances.
- **range_map**: pitch range and vocal registers with reliability scores.
- **timbre**: spectral characteristics.
- **pronunciation**: languages and phoneme coverage.
- **controls**: the 10 expressive vocal controls (from Part 7) the
  character supports.
- **reference_summary**: what the reference material was and how
  sufficient it was (8.1, 8.3).
- **version**: starts at v1; forking creates new versions.
- **owner, consent, provenance**: who owns it, what rights basis, where
  the reference came from.

## Building from reference (8.1, 8.3)

`analyze_reference(samples, rate, languages)` runs a deterministic
analysis:

- **Pitch**: real cepstrum (robust to formant filtering and missing
  fundamentals). Range is the central 96% of voiced frames
  (outlier-resistant).
- **Dynamics**: RMS distribution in dB (p10/p50/p90/range).
- **Registers**: chest/mix/head by pitch with reliability from observed
  seconds.
- **Vowel coverage**: band-energy vectors over 1 s voiced windows,
  greedily clustered by cosine similarity. Each cluster is one distinct
  spectral state. Labels are estimated (nearest template) and marked
  as such; the count is the metric.

`sufficiency_report(reference_summary, requested)` runs BEFORE building
or rendering. It checks:

- Requested pitch range within reference range (2 semitone tolerance).
- 4+ distinct vowel qualities observed.
- Belt above 0.5 needs 6+ dB dynamics span (evidence of varied effort).
- Requested language in the reference languages.

Gaps come with options (what to record, how to transpose), not just
refusals.

## Consent (8.4)

`create_voice_character` REQUIRES consent or licensed rights. No consent,
no character. The consent record stores the subject, the rights basis,
and verification. This is not optional and not bypassable.

## Rendering with a character (8.3, 8.7)

`render_with_character(store, voice_id, aligned_lyrics, performance)`:

1. Checks the performance is supported (refuses with options if not).
2. Renders through the vocal renderer (Part 7).
3. Marks provenance: voice id, version, identity vector, watermark.

**Identity stability (8.7)**: changing the performance (dynamics, belt,
etc.) MUST NOT change the identity vector. The character is who sings;
the performance is how. Tests enforce this.

## Sharing, forking, revocation (8.5, 8.6)

- **Fork**: create a modified copy (new version, provenance links to
  parent).
- **Share**: grant access to another owner (recorded in the asset).
- **Revoke**: immediately blocks rendering. Revoked characters refuse
  all renders.
- **Delete**: removes the character. Renders already made keep their
  provenance marks.

## Watermarking (8.8)

Every render is marked with voice id, version, and identity vector in
its metadata. This is the provenance hook; the audio watermark
(Sec. 19) builds on it.

## What is interface vs implementation

- **Real**: cepstral pitch tracking, dynamics analysis, register mapping,
  vowel clustering, sufficiency gating, consent enforcement, identity
  stability, provenance marking.
- **Reference**: the analysis is deterministic DSP, not a trained model.
  A trained voice model would plug in behind the same interfaces
  (`VoiceCharacterStoreABC`, the renderer protocol).
- **Honest limits**: vowel labels are estimated; the count is reliable
  but the names are approximate. Documented in the code.
