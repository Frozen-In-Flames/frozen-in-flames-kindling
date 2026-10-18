# Audio-to-Preset Inverse Rendering (Part 10)

Treat a finished recording as evidence of a production setup, infer an
editable preset, and apply it to new material.

## Pipeline (10.1)

1. **Analyze** (`analyze_reference`): tonal balance (5 bands), spectral
   centroid, crest factor, stereo correlation, side level, space ratio,
   per-section changes, detected roles (bass/drums/harmonic/bright_lead
   from spectral signatures).
2. **Propose** (`propose_preset`): lowshelf/highshelf from tonal tilt,
   compressor from crest factor, delay from space ratio, widener from
   stereo correlation.
3. **Self-fit**: render the preset on new material; features move toward
   the reference (tested).
4. **Return** (`inverse_render`): preset + 2 alternatives + confidence +
   the full analysis.
5. **Apply** (`render_preset`): run the chain on any new audio.

## Preset format (10.2)

JSON-serializable dict: `chain` (ordered effects with params),
`targets` (measured reference features), `roles`, `sections`. Every
parameter has a validated range (`EFFECT_SPECS`); `edit_preset`
changes one parameter and returns a new preset. Not an opaque
embedding: every value is human-readable and editable.

Effects (real DSP in `effects.py`): lowshelf, highshelf, compressor,
delay (space), widener.

## Honesty about ambiguity (10.3)

Different chains can produce similar audio. The pipeline returns
plausible presets with confidence and alternatives, and the result
carries an explicit disclaimer: "plausible inference; different chains
can produce similar audio". It NEVER claims to recover the single true
chain.

Confidence (0..1) rises with clear signatures: strong tonal tilt,
extreme crest, clear stereo image.
