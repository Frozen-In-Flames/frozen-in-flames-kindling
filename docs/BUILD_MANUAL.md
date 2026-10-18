# Open Music Creation System: The Build Manual

*Version 1.0. A unified specification for an open, professional-grade system that generates, edits, and re-renders complete songs from a persistent scene, reusable creative assets, and an explainable artist profile.*

## How to use this manual

This manual says what to build, in what order, and how to know each piece works. Every part has the same shape: **Purpose**, **Requirements** (MUST = required for release, SHOULD = expected, MAY = optional), and **Acceptance tests**. Part 22 gives the build sequence with exit criteria. Part 23 is a release checklist.

## Part 1. Product definition

**1.1 What you are building.** A music-creation system in which a song is a structured, editable *scene* and audio is one rendering of that scene. Three persistent layers sit on top of a generation engine:

1. The **Musical Scene**: the source of truth for structure, harmony, melody, lyrics, parts, automation, and production.
2. **Creative assets**: saved voice characters, virtual instruments, and production presets that are captured once and reused.
3. The **Artist Profile**: an explainable, editable model built from a creator's uploads that supplies context to every tool.

The core loop is **analyze → construct scene → render → inspect → revise**. A user can start from a text prompt, lyrics, a hummed melody, a stem, or a finished recording, and always end up with something they can change locally and re-render.

**1.2 Pick the first audience.** Choose one for v1; the choice drives every target below. Recommended: songwriters and producers who want to prototype full songs with vocals and then refine specific parts. Alternatives are backing-track producers and adaptive game music. Do not serve all of them at once.

**1.3 Quality targets.** Set a numeric threshold for every row before training anything, publish them, and review them quarterly.

| Dimension | Requirement | How it is measured |
| --- | --- | --- |
| Song quality | Convincing vocals and instruments, coherent arrangement, clean mix, few artifacts | Blinded listening panels; artifact detectors |
| Instruction following | Lyrics, genre, mood, tempo, key, instrumentation, and structure are reflected | Rubric scoring plus automatic checks (tempo, key, section timing) |
| Lyric fidelity | Every line present, in order, intelligible, aligned | ASR word error rate on isolated vocals; alignment error |
| Consistency | Same singer, palette, groove, and motifs across sections | Timbre similarity across sections; motif recurrence checks |
| Edit locality | Edits change the requested region or element and little else | Audio difference outside the edit mask (Part 12) |
| Reproducibility | Same scene, assets, seeds, and settings give the same render | Bit-level or perceptual-equivalence test |
| Latency | Fast draft previews; bounded full-render time | Wall-clock on reference hardware |
| Accessibility | Draft tier runs on a single consumer GPU | Benchmarks on the declared hardware tiers |

**1.4 Hardware tiers.** Declare three. *Draft*: single consumer GPU, fast previews, smaller models. *Studio*: workstation GPU, full-quality local rendering. *Hosted*: largest models, batch and long renders. Every feature must state which tiers it supports.

**1.5 Non-goals for v1.** Live-performance accompaniment; every language on day one; mobile-native inference; replacing the DAW (integrate with existing DAWs through export and plugins instead).

## Part 2. Architecture

**2.1 Principles.**

1. **The scene is the source of truth.** Rendered audio is derived and can always be regenerated from the scene, assets, seeds, and settings.
2. **Everything is inspectable and editable.** No hidden intermediates the user cannot see or change.
3. **Locality over reroll.** A targeted edit changes the target.
4. **Uncertainty is shown.** Inferred things carry confidence and alternatives. Insufficient input produces a warning, not a quiet guess.
5. **Identity is separate from performance.** A voice or instrument stays itself while its performance changes.
6. **Open and modular.** Each component has a documented interface and can be replaced.
7. **Consent and provenance are built in**, not bolted on (Part 19).

**2.2 Component map.**

| Layer | Components |
| --- | --- |
| Interface | Timeline editor, lyric editor, asset library, profile browser, A/B and version compare, CLI, API, DAW bridge |
| Workflow | Project service, scene store, version graph, job queue, render orchestrator |
| Intelligence | Prompt interpreter, composition planner, arrangement assistant, profile engine, reference analyzer |
| Assets | Voice characters, virtual instruments, production presets |
| Generation | Audio codec and latent space, song renderer, vocal renderer, instrument renderer, editing models |
| Production | Preset renderer, mixer, mastering stage, export |
| Foundation | Data pipeline, training stack, evaluation harness, provenance and consent registry |

**2.3 Data flow.**

1. Input arrives: prompt, lyrics, MIDI, stems, or finished audio.
2. The analyzer and interpreter produce a *draft scene* with confidences.
3. The user and planner refine it.
4. The orchestrator renders parts using assets and presets.
5. The mixer assembles the audio.
6. The user inspects, edits the scene or a region, and re-renders only what changed.
7. Every step is saved as a version.

## Part 3. The Musical Scene

**Purpose.** One shared representation connecting intent, symbolic music, performance, and audio.

**3.1 Contents.** The scene MUST represent:

- **Timeline:** tempo map, meter map, key map, section boundaries in bars and seconds.
- **Sections:** type (intro, verse, pre-chorus, chorus, bridge, outro, custom), length, energy target, density target.
- **Harmony:** chord progression per section, with optional voicings.
- **Melody:** note events with timing and pitch, or contour-only form.
- **Lyrics:** text, language, syllable segmentation, syllable-to-note alignment, phrasing marks.
- **Parts:** one per musical role, with assigned instrument asset, note and articulation data, dynamics, and expression curves.
- **Vocal parts:** assigned voice character, performance instruction, lyric lines.
- **Automation:** lanes for any parameter, per section or continuous.
- **Production graph:** preset reference or inline chain, routing, sends and returns.
- **Render settings:** sample rate, seeds, model and asset versions, quality tier.
- **Provenance:** who or what created each element.

**3.2 Per-element metadata.** Every element carries `source` (user, planner, inferred, imported), `confidence`, `locked` (the system must not change it), and `realization` level.

**3.3 Realization levels.** The system MUST work with partially realized scenes. An element can exist at four levels:

1. *Intent*: described in words or tags (for example, "bigger second chorus").
2. *Symbolic*: notes, chords, and lyrics with timing.
3. *Performance*: expressive timing, dynamics, articulations, vocal delivery parameters.
4. *Audio*: a rendered take, linked to the exact scene version and seeds that produced it.

**3.4 Example (abridged).**

```
scene:
  id: scn_0042
  parent: scn_0041
  timeline:
    tempo: [{bar: 1, bpm: 92}]
    meter: [{bar: 1, sig: 4/4}]
    key: [{bar: 1, key: F# minor}]
  sections:
    - id: sec_verse1
      type: verse
      bars: [9, 24]
      energy: 0.35
      lyrics: [ln_01, ln_02, ln_03, ln_04]
    - id: sec_chorus1
      type: chorus
      bars: [25, 40]
      energy: 0.8
  parts:
    - id: part_bass
      role: bass
      instrument: inst_sub_bass@v3
      realization: performance
      locked: false
  vocals:
    - id: vox_lead
      voice: voice_mara@v2
      performance: {style: close, dynamics: soft, vibrato: low}
  production:
    preset: preset_warm_tape@v1
  render:
    seed: 88123
    tier: studio
```

**3.5 Operations.** The scene store MUST support immutable versions, branches, element-level diffs, merges with conflict reporting, and content-addressed references to assets. A diff MUST be readable by a person (for example, "chorus 2 energy 0.6 → 0.8; added pad part").

**3.6 Import and export.** Import MIDI, MusicXML, stems, and finished audio (through analysis, with confidences). Export MIDI, stems, mixed audio, and the scene itself in an open, documented format.

**Acceptance tests.** Round-trip a MIDI file through the scene and back with no note loss. Re-render a saved scene on the same tier and pass the reproducibility test. Edit one section and confirm the diff lists only that section's elements.

## Part 4. Data pipeline

**Purpose.** Reproducible, traceable data with labels good enough to train structured, editable models.

**4.1 Stages.** Ingest and validate; normalize format and apply the loudness policy; deduplicate; segment; analyze (tempo, beats, key, chords, sections, energy); detect and separate vocals and instruments while keeping the original mix; transcribe lyrics and align words and syllables to the singing; label instruments and roles; score annotation quality; assign splits; write the record.

**4.2 Per-track record.** Each record MUST store: content hash; source and acquisition method; license or consent status and its terms; allowed uses (train, evaluate, none); processing versions; every derived label with a confidence; split assignment; and a deletion handle.

**4.3 Rules.**

- **Splits are fixed early and never leak.** Deduplicate across splits, including near-duplicates and alternate mixes of the same song.
- **Provenance is queryable.** You must be able to answer "which training items came from this source" and filter by license status.
- **Deletion propagates.** Removing an item or a user upload MUST exclude it from future training runs and remove dependent derived assets where policy requires.
- **Low-confidence labels are marked, not hidden.** Training code can threshold them.

**4.4 Data browser.** Build an internal tool to search by any label, play audio with aligned lyrics and section markers, inspect label confidence, and flag failures. Researchers should use it weekly. If nobody opens it, the pipeline is not trusted.

**4.5 Policy workstream.** Rights and licensing policy depends on jurisdiction, sources, and distribution. Assign an owner, write the policy before the first large training run, and encode its outcome in the license fields above.

**Acceptance tests.** Pick 100 random records: each is traceable to source, license status, and processing versions. Pick 100 aligned lyrics: median word alignment error meets the Part 1 target. A leakage audit finds zero cross-split duplicates.

## Part 5. Audio representation

**Purpose.** A compressed representation that can be generated efficiently without losing what musicians care about.

**Requirements.**

- MUST preserve timbre, transients, stereo image, and fine musical detail at the target sample rate (44.1 or 48 kHz stereo).
- MUST support decoding isolated regions, because editing needs local reconstruction.
- SHOULD support stem-aware or multi-track latents so separate parts can be generated and replaced.
- SHOULD offer more than one compression rate: a fast draft rate and a high-fidelity rate.
- MUST be evaluated on its own before any generator is built on it.

**Acceptance tests.** Reconstruction listening tests on drums, vocals, solo piano, dense mixes, and quiet material. Objective checks for spectral error, transient smearing, stereo correlation, and loudness drift. Encode-edit-decode round trips that show no seams at region boundaries.

## Part 6. Song planning and rendering

**6.1 Prompt interpreter.** Converts natural language, tags, lyrics, and controls into a draft scene. It MUST output a scene the user can read and MUST list its assumptions (for example, "assumed 4/4, 92 BPM, F# minor").

**6.2 Composition planner.** Proposes form, harmony, motifs, energy curve, and arrangement, conditioned on the scene, assets, and any selected profile context. It MUST offer alternatives on request and respect locked elements.

**6.3 Renderer.** Converts scene, assets, and preset into audio. Run a structured bake-off between autoregressive token models, parallel latent-generation models, and a planner-plus-renderer hybrid. Judge them against the Part 1 targets, not demos. Keep the renderer behind a stable interface (scene fragment in; audio and metadata out) so the winner can be replaced later.

**6.4 Hierarchical generation.** Plan at song level, refine at section level, render at phrase or chunk level. Chunks MUST overlap, and each chunk MUST be conditioned on the surrounding audio and scene context, before and after it where available.

**6.5 Long-form coherence.** Implement and test: tempo and harmony consistency across boundaries; motif return and development; energy curves across the whole song; intentional transitions (fills, risers, breaks) instead of fades; consistent vocal identity; no skipped or repeated lyric lines.

**6.6 Preview tiers.** Provide a *sketch* (seconds, lowest cost), a *draft* (good enough for decisions), and a *final* (full quality). A change heard in the sketch SHOULD predict the change in the final.

**Acceptance tests.** On the fixed suite (Part 17), raters score transitions and coherence above threshold; automatic checks show tempo drift and key violations below threshold; lyric completeness is met on every test song.

## Part 7. Vocals and lyrics

**Purpose.** Vocals are the hardest quality challenge. Treat them as their own system.

**Requirements.**

- MUST align lyrics to melody at syllable level, with per-language pronunciation handling (grapheme-to-phoneme, stress, elision).
- MUST support line-level regeneration: change a line, realign it, and re-sing only that line while neighboring lines keep their audio.
- MUST expose expressive controls: dynamics, breathiness, vibrato, belt, whisper, phrasing, push or lay-back timing, doubles, and harmonies.
- MUST report intelligibility automatically (ASR on isolated rendered vocals) and flag lines below threshold.
- SHOULD support multilingual lyrics and code-switching. List supported languages explicitly and test each separately.

**Acceptance tests.** Word error rate on rendered vocals below the Part 1 threshold for each declared language. A changed lyric line re-renders with unchanged surrounding audio (Part 12 locality). Blinded vocal-quality ratings by trained vocalists.

## Part 8. Voice characters

**Purpose.** A saved, reusable singing identity that can perform new lyrics and melodies.

**8.1 Asset specification.** A voice character MUST contain:

- Identity representation: what makes the voice this voice.
- Usable range map, with reliability per register.
- Timbral traits and register transitions.
- Pronunciation and language behavior.
- Expressive controls and their valid ranges.
- Reference summary: what material it was built from and how sufficient that material was.
- Version, owner, consent record, and creation provenance.

**8.2 Identity versus performance.** The performance instruction (soft, belt, whisper, bright, laid-back) is a separate input. Changing it MUST NOT change identity. Test this directly.

**8.3 Building from a reference.** Accept short and noisy references. Run a **sufficiency report** before building: coverage of pitch range, vowels, dynamics, and registers. When a requested performance is outside what the reference supports (for example, a high belt from a reference of soft mid-range singing), the system MUST say so and offer options instead of producing an unstable imitation.

**8.4 Consent and control.** Creating a voice character from a person's voice MUST require a recorded consent statement tied to that person and verified against the reference audio, or documented rights for a licensed or synthetic source. Store ownership. Let the owner revoke and delete. Mark rendered vocals with a robust, detectable watermark and provenance metadata. This is a release requirement, not a later feature.

**8.5 Reuse.** Save, version, share (with permissions), and fork characters. Every render records which version was used.

**Acceptance tests.** Identity similarity holds across new lyrics, melodies, registers, and styles above threshold. Listeners do not judge two performance styles of one character to be different people. The sufficiency report correctly flags deliberately inadequate references. A revoked character cannot be used for new renders.

## Part 9. Virtual instruments

**Purpose.** Instruments that perform parts musically, not just play a sound.

**9.1 Asset specification.** An instrument MUST expose: pitch range; articulations; dynamics; timing and humanization; phrasing and expression curves; sound-design controls (tone, attack, space); and context inputs (the scene's harmony, tempo, density, and neighboring parts).

**9.2 Performance behavior.** Given a part and context, the instrument produces a realistic performance, for example strummed versus fingerpicked guitar voicings, or a bass line that locks with the kick. It MUST render consistently across the whole song.

**9.3 Distillation workflow.**

1. Choose a teacher: a large model, a sampled library, or a synthesis pipeline.
2. Generate a broad, controlled set of performances across controls and contexts.
3. Train a smaller student for the target hardware tier.
4. Run a **loss audit** comparing student to teacher on timbre, range, articulation, expression, controllability, and latency.
5. Record the audit in the asset. Ship only if it clears thresholds.

**Acceptance tests.** The instrument performs unseen passages, not only training material. Controls produce monotonic, audible effects. The student-teacher audit is within tolerance. Draft-tier real-time factor meets target.

## Part 10. Audio-to-preset inverse rendering

**Purpose.** Treat a finished recording as evidence of a production setup, infer an editable preset, and apply it to new material.

**10.1 Pipeline.**

1. Analyze the reference: separate sources where possible, detect roles, measure tonal balance, dynamics, stereo image, space, and per-section changes.
2. Propose a structured preset.
3. Render the preset on the reference's own material and compare, to check fit.
4. Return the preset with alternatives and confidence.
5. Apply it to new material; the user listens, compares, and refines.

**10.2 Preset format.** An editable graph or parameterized recipe covering: instrument and source-role choices; arrangement and register tendencies; effects with order, parameters, and ranges; spatial, dynamic, and tonal targets; per-section automation and transition behavior. Not an opaque embedding.

**10.3 Honesty about ambiguity.** Different chains can produce similar audio. The system MUST return plausible presets with confidence and alternatives, and MUST NOT claim to recover the single true chain.

**Acceptance tests.** Self-fit: the preset rendered on the reference closely matches it. Transfer: producers judge that the preset applied to different songs and instrumentation captures the reference's character. Editability: changing one preset parameter changes the render predictably.

## Part 11. Artist profile

**Purpose.** A persistent, explainable model built from a creator's uploads that supplies context to every tool.

**11.1 Structure.** The profile has separate, inspectable dimensions. Each stores tendencies and ranges, not a recipe:

- **Musical identity:** harmony, melody shapes, rhythmic feel, phrasing, song structure.
- **Sound and arrangement:** instruments, roles, combinations, density, register, how parts enter and develop.
- **Performance:** vocal character, delivery, timing, dynamics, articulation, expressive range.
- **Production:** tonal balance, space, effects, stereo image, dynamics, automation habits.
- **Variation:** what changes by track, section, era, or mood.

Never collapse these into a single style vector.

**11.2 Relationship graph.** Each upload gets a track-level analysis. A graph links tracks, sections, parts, performances, presets, and recurring traits. Every edge MUST point to audible evidence (a section, pattern, role, or feature), not only a similarity score. The system MUST be able to answer: what do these two tracks share; what makes this one an outlier; which traits recur in choruses but not verses; is the new demo closer to the sparse songs or the dense ones; which traits are probably specific to one recording.

**11.3 Modes.** If the artist has distinct modes (sparse versus dense, early versus recent), represent them as separate contexts. Do not blend them into an average. For a new project, offer three choices: follow a mode, combine modes, or explore away from them.

**11.4 Explanations.** Every profile-driven suggestion MUST show its rationale and cite the uploads and sections it draws on. Example: "Close, dry vocal and sparse verse texture from tracks A and B; brighter chorus lift from track C."

**11.5 Corrections.** Users can mark a trait as specific to one track, keep a trait but drop another, combine traits from different uploads, or declare a new direction. A correction updates only the relevant dimension, is versioned, and can be rolled back. The profile keeps a visible history.

**11.6 Scope selection.** Every tool that uses the profile exposes a context selector: full catalog, chosen references, an era or mode, or none. The default is shown, never hidden.

**11.7 Where the profile is used.**

- Composition: structures, chords, melodies, and transitions consistent with selected references.
- Voice characters: preserve identity while the performance varies.
- Virtual instruments: choose parts, articulations, and registers that fit the artist's habits.
- Presets: reuse or adapt inferred chains without applying them indiscriminately.
- Arrangement assistance: suggest what to add, remove, or develop in the current section.
- Editing: make a local change while preserving the project's chosen direction.

**11.8 Privacy.** Profiles are private by default. Uploads and derived profile data are encrypted, exportable by the owner, and deletable with cascading removal of derived data. Profile data MUST NOT enter shared training sets without a separate, explicit opt-in.

**Acceptance tests.** The system explains why two uploads feel related with specific evidence and identifies meaningful differences. Carrying over a chosen subset of traits changes only those traits. Output with profile context on differs measurably from output with it off. Deleting an upload removes it and its derived traits.

## Part 12. Editing engine

**Purpose.** Editing is the central differentiator. Prompt-to-song with a full reroll is not enough.

**12.1 Operations.** The engine MUST support:

- **Inpainting:** replace a selected time range while preserving the surrounding audio.
- **Continuation:** extend an intro, section, or full track.
- **Section regeneration:** produce another verse or chorus without losing the song's identity.
- **Part and stem operations:** generate, replace, extract, remove, or rebalance a vocal or instrument.
- **Arrangement edits:** add or remove an instrument, change density, shift the energy of a section.
- **Lyric edits:** change a line and realign the singing to the music.
- **Performance replacement:** re-perform one phrase or part with a different instruction.
- **Asset swap:** change the voice character, instrument, or preset and re-render affected elements.
- **Reference conditioning:** guide any of the above with a supplied melody, chord chart, performance, or sound palette.
- **Automation editing:** change a parameter curve and re-render only what it touches.

**12.2 Edit contract.** Every edit takes a scene version, a target selection (time range, part, or element), an instruction, and a lock set. It returns a new scene version, new audio for the affected elements, and an **edit report** listing what changed, what was kept, and which seeds and assets were used.

**12.3 Locality.** A targeted edit MUST mostly affect the requested area or element.

- Define an **edit mask** for each operation (time range and, where relevant, stem).
- Measure audio difference outside the mask with a perceptual distance. Set the threshold in Part 1.
- Measure seams at mask boundaries (clicks, level jumps, phase problems).
- Locked elements MUST be unchanged; state whether the guarantee is bit-exact or perceptual.
- Measure the intended change inside the mask against the instruction.

**12.4 Dependency-aware re-rendering.** Keep a dependency graph from scene elements to rendered audio. After an edit, re-render only nodes whose inputs changed, then re-run the mix. Show the user what will be re-rendered before an expensive operation.

**12.5 Takes.** Generate several alternatives on request, compare them side by side, and allow comping across takes. Every take is a version.

**Acceptance tests.** On the edit suite (Part 17), median outside-mask difference is below threshold; no audible seams in blinded checks; instruction success rate meets target for each operation; a lyric edit changes only the edited line and its immediate transitions.

## Part 13. Mix, mastering, and export

**13.1 Mixer.** Applies levels, panning, tone, dynamics, space, buses, and automation from the production graph and scene. It MUST be deterministic given the same inputs. It MUST avoid clipping and report loudness and true-peak values.

**13.2 Mastering stage.** Optional and separable. Offers loudness targets for common destinations, optional reference matching, and a bypass. Never apply mastering silently.

**13.3 Export.** Provide:

- Mixed audio (WAV at 16 or 24 bit, 44.1 or 48 kHz) and common compressed formats.
- Stems for every part and vocal, time-aligned and loudness-labeled.
- MIDI and a score-like representation where the system can produce one reliably; state clearly where it cannot.
- Lyrics with timing.
- The scene file, asset versions, seeds, and render settings as a sidecar.
- Provenance and watermark metadata (Part 19).

**Acceptance tests.** Exported stems sum to the mix within tolerance. Exports open correctly in at least three common DAWs. Clipping, silence, DC offset, and channel-swap checks pass on the full test suite.

## Part 14. Interface, API, and DAW integration

**14.1 Interface.** The user MUST be able to do the following without learning the model:

- Write a prompt and lyrics with section markers.
- Set tempo, key, structure, mood, instrumentation, and energy directly.
- See and edit the scene as a timeline: sections, parts, lyrics, automation.
- Select a region or element and request an edit.
- Browse the asset library (voices, instruments, presets) and the artist profile with its evidence.
- Compare takes and versions, undo, branch, and return to earlier renders.
- Read an explanation for any generated choice and correct it.

**14.2 API.** A versioned, documented API with an OpenAPI description covering: scene read and write, render and edit jobs, asset operations, profile operations, exports, and job status and cancellation. Behavior MUST stay stable between releases within a major version.

**14.3 CLI and local app.** A command-line tool that can render a saved scene reproducibly, and a local interface that runs on the Draft tier.

**14.4 DAW bridge.** Phase one: export stems with tempo and meter maps and import MIDI and stems. Phase two (MAY, if resources justify it): a plugin that places renders and edits on the host timeline.

**Acceptance tests.** A new user goes from prompt to exported, edited song within a set time in moderated sessions. Every control documented in the interface is documented in the API. A scripted render from the CLI matches the interface render.

## Part 15. Project state, versioning, and reproducibility

**15.1 Project bundle.** A project contains scenes and their version graph; pinned asset versions; seeds; render settings; cached audio linked to exact scene versions; and references to profile snapshots used.

**15.2 Pinning.** Record hashes of model weights, tokenizer, preset engine, and mixer for every render. A render MUST be reproducible from its recorded inputs.

**15.3 Reproducibility levels.** State per tier: *Level A*, bit-exact on pinned software and hardware; *Level B*, perceptually equivalent across hardware. Do not claim a level you have not tested.

**15.4 Migration.** The scene schema uses semantic versioning. Old projects MUST open in new releases through automated migration, with a report of any lossy step.

**Acceptance tests.** Re-render a stored project six months later from its bundle and pass the declared level. Migrate a corpus of old projects with zero unreported loss.

## Part 16. Training program

Train in stages. Each stage has an exit gate; do not start the next stage at scale until the gate is met. Instrumental generation, singing, and editing are separate quality challenges. Evaluate them independently before claiming general strength.

| Stage | Goal | Exit gate |
| --- | --- | --- |
| 1. Audio representation | Codec or latent space that keeps timbre, transients, stereo image, detail | Part 5 acceptance tests |
| 2. General music | Broad structure and sound across genres | Instrumental suite passes quality and structure thresholds |
| 3. Lyrics and vocals | Intelligible, aligned, expressive singing | Part 7 acceptance tests per language |
| 4. Conditioning | Follow scene, structure, controls, references, and edits | Instruction-following and locality thresholds |
| 5. Asset models | Voice encoder, instrument students, preset inference | Parts 8, 9, 10 acceptance tests |
| 6. Preference tuning | Improve musical usefulness using expert and user ratings | Blinded preference gain without regressions elsewhere |
| 7. Efficiency | Distill and optimize for Draft and Studio tiers | Latency and quality targets on each tier |

**Practices.**

- Run small-scale ablations before every large run. Record the decision each ablation informed.
- Evaluate checkpoints on the regression suite automatically; block promotion on regression.
- Store configs, data manifests, seeds, and code revisions with every checkpoint.
- Keep the preference data and its collection protocol versioned and auditable.
- Never tune on the test sets.

## Part 17. Evaluation program

Automatic metrics catch regressions. Professional quality requires listening.

**17.1 Fixed suite.** Build a frozen test suite across genres, languages, tempos, vocal types, song lengths, and prompt styles, plus a held-out hard set. Version it. Refresh on a published schedule without leaking into training.

**17.2 Human evaluation.** Run blinded comparisons with musicians, producers, vocalists, and ordinary listeners. Rate separately: prompt adherence, composition, vocal quality, coherence, production, and edit success. Report inter-rater agreement. Publish the protocol.

**17.3 Automatic checks.**

- Tempo and key accuracy; section timing.
- Lyric word error rate and alignment error.
- Loudness, clipping, silence, clicks, discontinuities, channel problems.
- Identity similarity for voice characters; timbre consistency across sections.
- Edit locality and boundary seams.
- Reproducibility.

**17.4 Transfer tests.** Test capabilities beyond the input that created them:

- Does a voice character stay recognizable on new lyrics and melodies?
- Does an inferred preset work on a different song and instrumentation?
- Does a distilled instrument perform new passages, not only training examples?
- Can one asset change while the others stay stable?
- Do edits behave predictably across sections and full-length renders?

**17.5 Reliability.** Render every suite prompt across multiple seeds. Report the share of outputs passing all automatic checks and the rate of severe failures. A system that sounds impressive once but fails unpredictably is not a professional tool, so reliability and controllability are release criteria.

**17.6 Reporting.** Publish the evaluation protocol, results, and representative failure cases, not only selected demos. Ship a model card for every released model and a datasheet for every released dataset.

**17.7 Release gates.**

| Gate | Condition |
| --- | --- |
| Quality | All Part 1 thresholds met on the fixed suite |
| Vocals | Part 7 thresholds met for each declared language |
| Editing | Locality and instruction success thresholds met per operation |
| Assets | Part 8, 9, and 10 acceptance tests pass, including consent checks |
| Reliability | Pass rate and severe-failure rate within targets across seeds |
| Reproducibility | Declared level verified on each tier |
| Safety | Part 19 requirements verified |
| Documentation | Model cards, datasheets, and user docs complete |

## Part 18. Deployment and operations

**Purpose.** A professional system is more than a research notebook. Optimize the whole workflow (interpretation, generation, editing, mixing, download), not just raw model speed.

**18.1 Inference.** Efficient GPU inference with memory management, batching, and fast model loading. Apply quantization or distillation only where Part 17 tests show no unacceptable quality loss.

**18.2 Staged results.** Stream the sketch, then draft, then final, so users can decide before a full render finishes.

**18.3 Local and hosted.** Smaller models run locally on the Draft and Studio tiers. Larger models run hosted. The scene, assets, and project bundle move between them without conversion.

**18.4 Job system.** Queues, retries, cancellation, progress reporting, idempotent job submission, and recovery from worker failure. A cancelled or failed job never corrupts the project.

**18.5 Stability.** Version the API and the models. Behavior stays stable inside a major version. Publish a deprecation policy and keep old model versions available long enough for projects to be re-rendered.

**18.6 Monitoring.** Track latency per stage, crashes, queue depth, cost per generation, and quality regressions. Run the automatic checks from Part 17 on a sample of production renders, using only data the user has agreed to share.

**18.7 Security.** Encrypt uploads and projects in transit and at rest. Enforce per-user access control on projects, assets, and profiles. Protect credentials, rate-limit by account, and log access to sensitive assets such as voice characters.

**Acceptance tests.** Kill a worker mid-render and recover with no data loss. Run a load test at the planned concurrency within latency targets. Verify that a project created on a hosted tier opens and re-renders on a local tier at the declared reproducibility level.

## Part 19. Consent, provenance, privacy, and safety

**Purpose.** These are engineering requirements with acceptance tests, not policy footnotes. The most sensitive capabilities in this system are voice characters and artist profiles built from other people's audio.

**19.1 Voice consent.** Implement Part 8.4 in full: recorded, verified consent tied to the person whose voice is used, or documented rights for a licensed or synthetic source. Block creation of a voice character of a named real person, including public figures, without that verification. Support owner revocation that takes effect for new renders immediately.

**19.2 Watermark and provenance.** Every render carries an inaudible watermark and signed provenance metadata that identifies the system, model versions, and project. Release a detection tool. State honestly how well the watermark survives common transformations (re-encoding, resampling, mild editing) and where it does not.

**19.3 Training data governance.** Use the Part 4 license ledger. Honor opt-outs and deletion requests. Do not train on user uploads or user-created assets by default; use a separate, explicit, revocable opt-in.

**19.4 User data.** Define retention. Provide owner export and deletion. Deletion cascades to derived assets, profile traits, caches, and backups on a stated schedule.

**19.5 Misuse handling.** Publish a usage policy. Provide a reporting and takedown channel. Detect and limit abuse patterns (bulk impersonation attempts, repeated consent failures) in ways that do not require listening to private projects.

**19.6 Transparency about openness.** State exactly which code, weights, datasets, and assets are open, and under what licenses. Do not use the word open for anything that is not.

**19.7 Legal review.** Assign counsel to review data sources, licensing, voice rights, and distribution for each jurisdiction you ship in. Version the policies the same way as code.

**Acceptance tests.** An attempt to create a voice character without valid consent fails. A revoked voice cannot be rendered. Watermark detection rate on the test suite is reported before and after a defined set of transformations. A deletion request removes the upload and every derived trait and asset in the verification audit.

## Part 20. Team and resources

| Role | Responsibility |
| --- | --- |
| Audio and music-generation research | Codec, renderers, vocal models, editing models |
| Music information retrieval and DSP | Analysis, alignment, source separation, preset inference, mixer |
| Training and inference engineering | Distributed training, efficient inference, deployment tiers |
| Data engineering and evaluation | Pipeline, data browser, test suites, metrics, listening studies |
| Music practitioners | Songwriters, producers, vocalists, and mixers who judge output and shape the product |
| Product, frontend, backend, tooling | Interface, scene store, API, CLI, DAW bridge |
| Trust, safety, and legal | Consent systems, provenance, policy, licensing |
| Release, documentation, community | Packaging, docs, support, contributor process |

**Cost drivers.** Sustained expert labor, experimentation, compute, storage, audio review, and long-term maintenance. A small team can build a compelling focused system. Broad, polished coverage across genres, languages, vocals, editing, and hardware is a much larger undertaking, so scope to the audience chosen in Part 1.

**Rule of ownership.** Every Part of this manual has one named owner who is accountable for its acceptance tests.

## Part 21. Risks and mitigations

| Risk | Early signal | Mitigation |
| --- | --- | --- |
| Vocals unintelligible or unstable | High word error rate; identity drift across sections | Treat vocals as a separate system; line-level evaluation; limit the declared language list |
| Edits change too much | Large outside-mask difference | Local reconstruction in the codec; condition on surrounding audio; dependency-aware re-rendering |
| Long-form incoherence | Rater scores fall as length grows | Hierarchical planning; overlap and continuity conditioning; transition tests |
| Voice misuse | Impersonation reports; consent failures | Verified consent; watermark and provenance; takedown channel |
| Data rights uncertainty | Gaps in the license ledger | Policy owner; license filtering; legal review before large runs |
| Profile collapses to generic output | Outputs converge on an average | Separate dimensions and modes; evidence-linked traits; correction tools |
| Preset inference overclaims | Transfer tests fail | Return alternatives with confidence; show fit on the reference |
| Scope creep | Too many genres, languages, and features at once | One audience; explicit language list; phase gates |
| Compute cost too high | Cost per generation above target | Tiers; distillation; staged previews |
| Reproducibility drift | Old projects no longer re-render | Pin and hash everything; test at each release |
| Demo bias | Strong demos, weak suite results | Frozen suites; publish failure cases |

## Part 22. Build sequence

Phases overlap where dependencies allow. After Phase 1, run structured listening tests every cycle, find the biggest user-visible failure, and improve that capability rather than scaling everything at once.

1. **Phase 0, Decisions.** Choose the first audience, quality thresholds, hardware tiers, supported languages, licensing approach, and policy owner. *Exit:* a published targets document.
2. **Phase 1, Foundations.** Build the scene format and project renderer using existing components for generation. Build the data pipeline, evaluation harness, and a consent and provenance registry. *Exit:* a prompt becomes a scene and then audio end to end; the reproducibility test passes; evaluation suite v0 exists.
3. **Phase 2, Representation and baseline generation.** Build and evaluate the codec, run the renderer bake-off, and ship a baseline instrumental renderer. *Exit:* Part 5 tests pass; bake-off report published.
4. **Phase 3, Vocals and lyrics.** Build alignment, the vocal renderer, expressive controls, and line-level regeneration. *Exit:* Part 7 tests pass for each declared language.
5. **Phase 4, Editing.** Build inpainting, continuation, section regeneration, and the locality measurement. Make these reliable before adding more features. *Exit:* Part 12 tests pass.
6. **Phase 5, Assets.** Build voice characters (with consent), virtual instruments (with distillation), and preset inference. *Exit:* Parts 8, 9, and 10 tests pass.
7. **Phase 6, Artist profile.** Build the profile, relationship graph, explanations, corrections, and scope selection. *Exit:* Part 11 tests pass.
8. **Phase 7, Workflow.** Build the timeline interface, takes and versioning, API, CLI, and DAW export. *Exit:* Part 14 tests pass, including moderated user sessions.
9. **Phase 8, Full-song planning.** Add song-level planning, long-form coherence, and richer controls. *Exit:* Part 6 coherence and transition thresholds met on the fixed suite.
10. **Phase 9, Efficiency and deployment.** Optimize for the Draft and Studio tiers, build the job system and monitoring, and harden security. *Exit:* Part 18 tests pass.
11. **Phase 10, Release.** Verify every gate in 17.7, complete model cards, datasheets, and documentation, and publish code, weights, and the evaluation protocol with a clear statement of what is open. *Exit:* release checklist (Part 23) complete.
12. **Phase 11, Expansion.** Add genres, languages, and workflows in the order that evaluation results support.

## Part 23. Release checklist

A release ships only when every item is verified and recorded.

- Targets: all Part 1 thresholds set, published, and met on the fixed suite.
- Scene: round-trip, diff, and reproducibility tests pass.
- Data: leakage audit clean; license ledger complete for all training data.
- Representation: reconstruction and seam tests pass.
- Generation: long-form coherence and lyric completeness thresholds met.
- Vocals: intelligibility thresholds met in every declared language.
- Voice characters: identity, sufficiency, and consent tests pass; revocation works.
- Instruments: unseen-passage, control, and loss-audit tests pass.
- Presets: self-fit, transfer, and editability tests pass.
- Artist profile: evidence, correction, scope, and deletion tests pass.
- Editing: locality, seam, and instruction-success thresholds met per operation.
- Mix and export: loudness, clipping, stem-sum, and DAW-open checks pass.
- Interface and API: moderated sessions succeed; API documentation matches the interface.
- Reliability: multi-seed pass rate and severe-failure rate within targets.
- Operations: failure recovery, load, security, and cross-tier reproducibility verified.
- Safety: watermark, provenance, consent, privacy, and deletion verified.
- Transparency: model cards, datasheets, evaluation protocol, failure cases, and open-component statement published.

## Glossary

- **Scene:** the structured representation of a song (timeline, sections, harmony, melody, lyrics, parts, automation, production). Audio is a rendering of it.
- **Realization level:** how concrete a scene element is: intent, symbolic, performance, or audio.
- **Voice character:** a saved, versioned singing identity with range, timbre, language behavior, and expressive controls, separate from any one performance.
- **Instrument asset:** a reusable generator that performs musical parts with musical and sound-design controls.
- **Preset:** an editable production graph or recipe (sources, effects, order, parameters, automation) inferred from or applied to audio.
- **Artist profile:** an evolving, explainable model of recurring and varying traits across a creator's uploads.
- **Mode:** a distinct context within a profile, such as an era or a sparse versus dense approach.
- **Edit mask:** the time range and elements an edit is allowed to change.
- **Locality:** the degree to which an edit changes only its target.
- **Edit report:** the record of what an edit changed, kept, and used.
- **Sufficiency report:** an assessment of whether a reference supports a requested voice performance.
- **Loss audit:** a comparison of a distilled student against its teacher.
- **Take:** one rendered alternative of a part, section, or edit, stored as a version.
- **Tiers:** Draft (consumer GPU), Studio (workstation), Hosted (largest models and long renders).

---

**The thesis in one line.** Do not compete only on one-click song quality. Build an open, inspectable system that turns musical intent into a structured scene, renders it convincingly with reusable voices, instruments, and production styles, learns an explainable picture of each artist, and lets a creator change exactly what they want and nothing else.
