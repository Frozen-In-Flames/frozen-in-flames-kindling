# Editing Engine (Part 12)

Editing is the central differentiator. Prompt-to-song with a full
reroll is not enough.

## Operations (12.1)

All ten, in `operations.py`, each deterministic given the seed:

- **inpaint**: replace notes in a time range with generated fill.
- **continue**: extend by N bars, carrying the last phrase forward.
- **regenerate_section**: rhythmic/velocity variation within a section,
  pitches kept (identity preserved).
- **part_stem**: generate, remove, or rebalance (quieter/louder) a part.
- **arrangement**: density up/down, section energy shifts.
- **lyric_edit**: change one line, flag for realignment.
- **performance_replace**: softer/stronger, push/lay-back timing.
- **asset_swap**: swap voice/instrument/preset refs, recorded in render
  metadata.
- **reference_condition**: guide with a reference's density or melody.
- **automation_edit**: change a parameter curve over a time range.

## Edit contract (12.2)

`EditRequest`: operation, scene version, selection (time/part/element),
instruction, lock set, seed, optional reference. `EditReport`: what
changed, what was kept, seeds/assets used, locked-element guarantees,
locality measurements.

## Locality (12.3)

- `edit_mask`: boolean mask for the edited time range.
- `outside_mask_distance`: perceptual (log-spectral) distance outside
  the mask; crossfaded splices keep it under 3 dB in tests.
- `seam_score`: click and level-jump measurement at boundaries.
- `verify_locked`: locked elements must be bit-exact or perceptually
  unchanged; raises otherwise, stating the guarantee level.
- `crossfade_edits`: 10 ms crossfaded splicing.

## Dependency-aware re-rendering (12.4)

`DependencyGraph` maps scene elements to render nodes. `preview`
shows what will be re-rendered before an expensive operation;
`affected_nodes` resolves transitively (part -> section mix -> master).

## Takes (12.5)

`TakeManager`: add takes (each a version with seed + metadata),
`comp` across takes with crossfades, `best_take` by a metric.
