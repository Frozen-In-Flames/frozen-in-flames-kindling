# Song planning and rendering (Part 6)

## Prompt interpreter (6.1)

`kindling.planning.interpret()` turns natural language, tags, lyrics, and
controls into a draft scene plus an assumptions list. It extracts tempo
("92 bpm"), key ("F# minor"), sections (verse, chorus, bridge, intro,
outro, pre-chorus), and mood words that bias energy, and records every
default it chose ("assumed 120 BPM (no tempo in prompt)") instead of hiding
it. The scene it returns is fully readable and editable.

## Composition planner (6.2)

`ReferencePlanner` proposes form, harmony, motifs, energy curve, and
arrangement from real functional harmony: per-section-type progressions in
the song's key and mode (for example C major verse: C - G - Am - F),
singable interval motifs on the song's scale, section-archetype energy
curves, and role assignments with entrances and exits per section.
`alternatives(scene, element, count)` offers variants of harmony, energy, or
motif. Locked elements are never touched by the planner.

## Renderer (6.3)

`ReferenceRenderer` honors the stable interface: scene fragment in, audio
and metadata out. It renders deterministically with simple synthesis
(plucked, pad, and bass tones, noise-based drums, a soft guide tone for
vocal parts). The guide tone is honest about what it is: the metadata warns
that real vocal rendering is Part 7. Same seed and scene always give the
same audio.

The structured bake-off (`kindling.planning.bakeoff`) judges registered
renderers, autoregressive, parallel-latent, or planner-hybrid, against the
Part 1 targets, not demos: validity, determinism, coherence pass rate, and
cost. The reference renderer runs as the baseline every learned renderer
must beat, and the winner can replace it without touching the interface.

## Hierarchical generation (6.4)

`HierarchicalRenderer` plans at song level, refines at section level, and
renders at chunk level. Chunks are 4-bar windows with 1-bar overlap, rebased
so each chunk starts at bar 1 beat 0. Every chunk is rendered with its
surrounding context: the previous chunk's tail audio and the next chunk's
scene, both passed in and recorded. Overlaps join with an equal-power
crossfade, so chunk boundaries do not click.

## Long-form coherence (6.5)

`coherence_report(scene, audio, rate)` runs the automatic checks: tempo
drift per section against the tempo map, key violations per section against
the key map, lyric completeness (every line referenced), motif return (the
planner's motif intervals recurring in the melody), and intentional
transitions (arrangement changes or explicit transition marks at every
boundary; unmarked boundaries are warnings).

## Preview tiers (6.6)

Sketch (first 8 seconds at low rate, lowest cost), draft (full song, good
enough for decisions), final (full quality). Rendering is deterministic, so
a change heard in the sketch predicts the change in the final.
