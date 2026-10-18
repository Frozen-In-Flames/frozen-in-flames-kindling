# Frozen In Flames: Kindling
## Open Music Creation System

Kindling is an open, professional-grade system that generates, edits, and re-renders complete songs from a persistent scene, reusable creative assets, and an explainable artist profile.

The name says what it is. Reusable voice characters, virtual instruments, and production presets are the kindling: the prepared fuel you lay down before every song. The musical scene is how you lay the fire. Rendering is the burn. And any song can be rekindled, changed exactly where you want, and burned again.

### What it is

A music-creation system in which a song is a structured, editable *scene* and audio is one rendering of that scene. Three persistent layers sit on top of a generation engine:

1. The **Musical Scene**: the source of truth for structure, harmony, melody, lyrics, parts, automation, and production.
2. **Creative assets**: saved voice characters, virtual instruments, and production presets, captured once and reused.
3. The **Artist Profile**: an explainable, editable model built from a creator's uploads that supplies context to every tool.

The core loop is **analyze → construct scene → render → inspect → revise**. A user can start from a text prompt, lyrics, a hummed melody, a stem, or a finished recording, and always end up with something they can change locally and re-render.

### Thesis

Do not compete on one-click song quality. Build an open, inspectable system that turns musical intent into a structured scene, renders it convincingly with reusable voices, instruments, and production styles, learns an explainable picture of each artist, and lets a creator change exactly what they want and nothing else.

### First audience (v1)

Songwriters and producers who want to prototype full songs with vocals, then refine specific parts.

### Quality targets

Every dimension has a numeric threshold, set before training anything, published, and reviewed quarterly. Thresholds live in [targets.yaml](targets.yaml); `tools/check_targets.py` reports which are still unset.

### Hardware tiers

- **Draft**: single consumer GPU. Fast previews, smaller models.
- **Studio**: workstation GPU. Full-quality local rendering.
- **Hosted**: largest models, batch and long renders.

Every feature states which tiers it supports.

### v1 non-goals

Live-performance accompaniment. Every language on day one. Mobile-native inference. Replacing the DAW (Kindling integrates with existing DAWs through export and plugins instead).

### Build versions

One version per part of the build manual. V1 is Part 1, Product definition (this document). V2 is Part 2, Architecture, and so on through V23, the release checklist. See [VERSIONS.md](VERSIONS.md). Nothing is skipped.

### Spec

The full build manual is the spec: [docs/BUILD_MANUAL.md](docs/BUILD_MANUAL.md). Every part has Purpose, Requirements (MUST / SHOULD / MAY), and Acceptance tests. Part 22 gives the build sequence with exit criteria. Part 23 is the release checklist.

### Functional milestone A (V24)

The upload / save / use loop is live in Python. See
[docs/functional-milestone-a.md](docs/functional-milestone-a.md).

```
kindling library upload track.wav --kind voice --name "Aries" \
    --consent-subject "Aries Hilton"
kindling library list
kindling render --prompt "dark driving verse and chorus, 100 bpm" \
    --lyrics-file lyrics.txt --voice voice_aries \
    --instrument guitar=inst_my_groove --preset preset_my_chain \
    --seed 7 --out song/
kindling export song/ --format stems --out song-stems/
```

Install the command with `pip install -e .` then use `kindling` directly.

### License

Apache-2.0. See [LICENSE](LICENSE).
