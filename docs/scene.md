# The Musical Scene (Part 3)

One shared representation connecting intent, symbolic music, performance,
and audio. The scene is the source of truth; rendered audio is derived and
can always be regenerated from the scene, assets, seeds, and settings.

## Format

The open, documented format is `kindling/scene/scene.schema.json`
(JSON Schema, draft 2020-12). Scenes are plain dicts validated against it,
so the in-memory format and the on-disk format are the same thing.

A scene holds: timeline (tempo, meter, and key maps plus section boundaries
in bars and seconds), sections, harmony, melody, lyrics, parts, vocal parts,
automation lanes, the production graph, render settings, and provenance.

Every element carries metadata: `source` (user, planner, inferred,
imported), `confidence` (0 to 1), `locked` (the system must not change it),
and `realization` (intent, symbolic, performance, audio). Partially realized
scenes are valid: a section can exist as an intent ("bigger second chorus")
long before it has notes.

Asset references are content-addressed: `{"id", "version", "sha256"}`,
displayed as `id@version`.

## Store

`kindling.scene.SceneStore` implements the interface contract:

- Immutable versions. Version ids are the sha256 of the canonical scene
  JSON, so identical scenes always get identical ids. Loading returns a
  copy; nothing stored is ever mutated.
- Branches and full parent history.
- Human-readable element-level diffs, for example
  `chorus (sec_chorus2): energy 0.6 -> 0.8` or `added part 'pad' (role: pad)`.
- Three-way merges with conflict reporting. Conflicts are reported with
  both values, never silently resolved.

## Import and export

- MIDI: `kindling.scene.midi` reads and writes real MIDI files (format 0/1,
  note on/off, tempo map, time signature, track names). Round-trip keeps
  every note: pitch, start, duration, velocity.
- MusicXML: `kindling.scene.musicxml_io` reads and writes score-partwise
  files for the subset the scene needs.
- Finished audio and stems: `kindling.scene.audio_import` analyzes WAV
  files deterministically (duration, peak, RMS, onset-based tempo estimate
  with confidence, per-second energy curve) and imports them as
  audio-realization elements. Structural content is marked as not yet
  analyzed, with a warning, instead of being invented. The reference
  analyzer (V6) and preset inference (V10) build on this.

## Acceptance

- MIDI round-trip with no note loss: tested.
- Saved scene re-render reproducibility: version ids are deterministic;
  the render side is covered in V6 and V15.
- Edit one section, diff lists only that section's elements: tested.
