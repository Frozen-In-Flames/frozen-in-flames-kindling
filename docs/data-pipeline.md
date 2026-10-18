# Data pipeline (Part 4)

Reproducible, traceable data with labels good enough to train structured,
editable models.

## Stages

`kindling.data.Pipeline` runs every stage in order: ingest and validate,
normalize (canonical 48 kHz mono with a recorded loudness label), deduplicate
(exact sha256 plus a 512-bit perceptual fingerprint robust to small gain
changes), segment, analyze, separate (mid/side reference; the mix is always
kept), align lyrics from caller-provided transcripts, label instruments and
roles, score annotation quality, assign splits, write the record.

Analysis is classical DSP with numpy: onset-autocorrelation tempo, Krumhansl
key profiles, chroma-template chords, chroma-novelty sections, RMS energy,
and a spectral heuristic for instrument role. Every label carries a value,
a confidence, and the method that produced it.

## Honest boundaries

Three jobs need learned models that do not exist yet: lyric transcription
from audio, true source separation, and instrument classification. The
pipeline provides the interfaces and extension points for all three, plus
reference implementations whose limits are documented in the code: a
vocal-band onset aligner for provided transcripts, mid/side center
estimation, and a low-confidence spectral heuristic. Nothing is faked;
low-confidence labels are marked, not hidden, and training code can
threshold them.

## Records

The per-track record (`kindling/data/record.py`, schema in code) stores the
content hash, source and acquisition method, license status and terms,
allowed uses, processing versions, every derived label with confidence,
split assignment, and a deletion handle.

## Rules, enforced in code

- Splits are fixed early and never leak. Assignment is deterministic from the
  content hash, and near-duplicates (including alternate mixes) are pinned to
  the original's split. `leakage_audit()` proves zero cross-split duplicates.
- Provenance is queryable: `LicenseLedger.by_source()`,
  `by_license_status()`, `by_allowed_use()`, `by_split()`.
- Deletion propagates: `delete_record()` excludes the item from every future
  manifest and lists derived assets for cascading removal where policy
  requires.
- Manifests (`build_manifest(pipeline, "train" | "evaluate")`) pin the
  processing versions so runs are reproducible.

## Data browser

`kindling.data.browser` searches by any label or field, shows a record with
its confidences and failure flags, and writes an HTML report with an audio
player beside the aligned lyrics and section markers. CLI:

```
python -m kindling.data.browser --ledger <dir> search source=demo
python -m kindling.data.browser --ledger <dir> show rec_abc123
python -m kindling.data.browser --ledger <dir> report rec_abc123 --audio song.wav --out report.html
```

## Policy workstream

See `docs/data-policy.md`. The policy owner is assigned there before the
first large training run, and the license fields in every record encode the
policy outcome. The ledger enforces `allowed_uses` regardless.
