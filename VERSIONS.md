# Build versions

Each version implements one part of the build manual (`docs/BUILD_MANUAL.md`), in order. Nothing is skipped.

- **V1**: Part 1. Product definition
- **V2**: Part 2. Architecture
- **V3**: Part 3. The Musical Scene
- **V4**: Part 4. Data pipeline
- **V5**: Part 5. Audio representation
- **V6**: Part 6. Song planning and rendering
- **V7**: Part 7. Vocals and lyrics
- **V8**: Part 8. Voice characters
- **V9**: Part 9. Virtual instruments
- **V10**: Part 10. Audio-to-preset inverse rendering
- **V11**: Part 11. Artist profile
- **V12**: Part 12. Editing engine
- **V13**: Part 13. Mix, mastering, and export
- **V14**: Part 14. Interface, API, and DAW integration
- **V15**: Part 15. Project state, versioning, and reproducibility
- **V16**: Part 16. Training program
- **V17**: Part 17. Evaluation program
- **V18**: Part 18. Deployment and operations
- **V19**: Part 19. Consent, provenance, privacy, and safety
- **V20**: Part 20. Team and resources
- **V21**: Part 21. Risks and mitigations
- **V22**: Part 22. Build sequence
- **V23**: Part 23. Release checklist
- **V24**: Functional milestone A. Upload / save / use loop: on-disk asset
  library (voice, instrument, preset), render-from-library song builds,
  extended CLI, proven with real audio (228 tests green)
- **V25**: Vocal separation (classical DSP). `kindling/assets/separate.py`:
  center-channel plus REPET-style repeating-background cues, numpy/scipy
  only, no learned models. Opt-in `separate_vocals` flag on
  `analyze_reference`; honest SDR/SIR eval on synthetic mixtures
  (vocal +18.7 dB SDR, +23.6 dB SIR). `docs/vocal-separation.md`.
  voice_aries v1 deliberately unchanged.
- **V26** (web app v7): Words you can hear. The owner's design, in his
  framing: the words are generated first in shaped noise, then retuned to
  the voice profile, so the text keeps a base of real English and the
  biometric adaptation is a layer on top, never a substitute. New phoneme
  layer (`web/js/phonemes.js`): rule-based grapheme-to-phoneme with a
  130-entry exception dictionary, 39-phoneme inventory, letter-span
  alignment with the existing syllable timing. The renderer
  (`web/js/render.js`) is now a formant-track synth: onsets, nucleus, and
  codas time-proportioned per note, F1/F2/F3 gliding between phoneme
  targets, per-phoneme excitation (harmonic source, band-shaped noise, or
  both). The profile retune is a bounded warp (at most 25% of the
  log-space distance toward the profile's nearest observed vowel,
  formants clamped to 180-3800 Hz); the pre-V26 behavior, where the
  profile replaced the lyric's vowel outright, is removed and pinned by a
  regression test. Whisper mode renders the whole line on noise excitation
  alone. Web DSP suite: `tests-web/v26.test.mjs`, 80/80. Python engine
  untouched (238/238); its parity port of the phoneme layer is a
  documented follow-up. Measured outcomes and honest limits:
  `RELEASE-NOTES-V26.md`.
- **V27** (web app v8): Word calibration. The owner's design, in his
  framing: upload a sample of his voice for each of the words the
  reading struggles with, and mathematically inverse-render a solution
  for the failed words from that data. New modules
  (`web/js/calibration.js`, the pure data layer, and
  `web/js/calibrate.js`, the renderer-backed solver): for a selected
  voice, the app lists calibration targets (words the rules read
  unaided, words matching known-miss patterns, and every word in the
  current Compose lyrics), takes one recorded or uploaded sample per
  word, and fits it. The fit is differential: candidate vowels are
  rendered in the word's own context at the sample's pitch and measured
  with the same estimator as the sample, so estimator bias cancels;
  per-formant response gains are probed, and per-phoneme log-space
  corrections are solved and aggregated across the voice's samples, so
  a correction learned from one word helps other words sharing the
  phoneme. Two products per accepted sample: a verified exception when
  the produced vowel clearly differs from the read one (the read vowel
  is the null hypothesis; a challenger must beat it clearly), and an
  inverse fit (formant deltas plus duration scalars). The renderer
  applies a ladder: the word's own solved track, then aggregated
  phoneme offsets, then the V26 bounded warp, then canonical. A quality
  gate refuses clipped, too short, too noisy, or nucleus-less takes
  with a plain-language reason and writes no calibration data. The
  calibration layer is JSON inside the voice profile (schema in
  `RELEASE-NOTES-V27.md`), so a future Python port can consume the
  identical data. It is a calibration layer stored as data, not a
  trained model, and the product copy says so. Web DSP suite:
  `tests-web/v27.test.mjs`, 31/31, including a zero-offset negative
  control and exact V26 render pins; V26 suite still 80/80; Python
  engine untouched (238/238). Measured outcomes and honest limits:
  `RELEASE-NOTES-V27.md`.
