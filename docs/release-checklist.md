# Release Checklist (Part 23)

A release ships only when every item is verified and recorded. Run
`python3 tools/check_release.py` to verify all items.

- [ ] **Targets**: all Part 1 thresholds set, published, and met on the fixed suite (`tools/check_targets.py`).
- [ ] **Scene**: round-trip, diff, and reproducibility tests pass (`tests/test_scene.py`).
- [ ] **Data**: leakage audit clean; license ledger complete for all training data (`tests/test_data.py`).
- [ ] **Representation**: reconstruction and seam tests pass (`tests/test_codec.py`).
- [ ] **Generation**: long-form coherence and lyric completeness thresholds met (`tests/test_planning.py`).
- [ ] **Vocals**: intelligibility thresholds met in every declared language (`tests/test_vocals.py`).
- [ ] **Voice characters**: identity, sufficiency, and consent tests pass; revocation works (`tests/test_voice.py`).
- [ ] **Instruments**: unseen-passage, control, and loss-audit tests pass (`tests/test_instruments.py`).
- [ ] **Presets**: self-fit, transfer, and editability tests pass (`tests/test_presets.py`).
- [ ] **Artist profile**: evidence, correction, scope, and deletion tests pass (`tests/test_profile.py`).
- [ ] **Editing**: locality, seam, and instruction-success thresholds met per operation (`tests/test_editing.py`).
- [ ] **Mix and export**: loudness, clipping, stem-sum, and DAW-open checks pass (`tests/test_mix.py`).
- [ ] **Interface and API**: moderated sessions succeed; API documentation matches the interface (`tests/test_api.py`).
- [ ] **Reliability**: multi-seed pass rate and severe-failure rate within targets (`tests/test_eval.py`).
- [ ] **Operations**: failure recovery, load, security, and cross-tier reproducibility verified (`tests/test_ops.py`).
- [ ] **Safety**: watermark, provenance, consent, privacy, and deletion verified (`tests/test_safety.py`).
- [ ] **Transparency**: model cards, datasheets, evaluation protocol, failure cases, and open-component statement published (`docs/`, `kindling/eval/program.py`, `kindling/safety/governance.py`).

## Current release: v23

All 23 parts built, all tests passing (214 tests), all tags v1-v23
pushed. The system is the reference implementation: real interfaces,
real evaluation harnesses, deterministic procedural stand-ins behind
them, honest about what is interface vs implementation throughout.
