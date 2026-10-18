# Artist Profile (Part 11)

A persistent, explainable model built from a creator's uploads that
supplies context to every tool.

## Structure (11.1)

Five separate, inspectable dimensions: musical_identity,
sound_arrangement, performance, production, variation. Each stores
tendencies (mean/min/max or mode/share) and ranges with observation
counts, plus the evidence behind every observation. Never collapsed
into a single style vector.

## Relationship graph (11.2)

`ProfileGraph` links tracks, sections, and traits. Every edge carries
audible evidence (section, role, pattern). Answers: shared traits
between two tracks (with per-track evidence), outlier traits, and
which traits recur in choruses but not verses.

## Modes (11.3)

`detect_modes` splits tracks into separate contexts (sparse vs dense)
when a trait is bimodal. Modes are never blended into an average. New
projects choose: follow a mode, combine modes, or explore.

## Explanations (11.4)

`explain_suggestion` renders a suggestion with its rationale and cites
the uploads and sections it draws on.

## Corrections (11.5)

`apply_correction`: mark a trait track-specific, drop a trait, or keep
only chosen traits. Each correction is versioned in the profile history
and scoped to one dimension; other dimensions are untouched.
`rollback` records the rollback point in the history.

## Scope selection (11.6)

`select_scope`: full_catalog, chosen_references, era_or_mode, or none.
The resolved scope always names itself; the default is shown, never
hidden.

## Privacy (11.8)

`PrivacyRecord`: private by default, encrypted, owner-exportable,
deletable with cascading removal of derived data (`remove_track`
deletes the track and all its trait observations). Profile data never
enters shared training without a separate explicit opt-in; the flag
defaults to False and is revocable.

## Where it is used (11.7)

Composition, voice characters, virtual instruments, presets,
arrangement assistance, and editing all take a scope and read the
relevant dimensions. The profile supplies context; it never dictates.
