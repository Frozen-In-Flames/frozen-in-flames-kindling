# Virtual Instruments (Part 9)

Instruments that perform parts musically, not just play a sound. Given
a part and context, the instrument makes musical decisions: articulation,
timing, dynamics, phrasing. It renders consistently across the whole song.

## The asset (9.1)

`InstrumentAsset` MUST expose: pitch range, articulations, dynamics,
timing/humanization, phrasing/expression curves, sound-design controls
(tone, attack, space) with min/max/default, and context inputs (harmony,
tempo, density, neighboring parts). `validate()` returns spec violations.

Reference assets: `kindling-guitar` (strummed/fingerpicked/muted/
harmonic), `kindling-bass` (fingered/picked/slap/muted),
`kindling-keys` (sustained/staccato/tremolo).

## Performance behavior (9.2)

`PerformanceEngine.perform(part, context, instrument, seed)`:

- **Guitar**: dense context -> strummed voicings with strum spread;
  sparse context -> fingerpicked. Downbeats accented, phrases shaped
  with a slight crescendo.
- **Bass**: locks note starts to the kick pattern from context
  neighbors (within 0.25 beats). Picks articulation by density.
- **All**: timing humanization (seeded Gaussian jitter), deterministic:
  same part + same seed = same performance, so the song renders
  consistently.

## Distillation workflow (9.3)

`distill_guitar()` / `distill_bass()` implement the five steps:

1. **Teacher**: high-detail reference synth (Karplus-Strong with rich
   excitation; 16-partial filtered saw bass).
2. **Distillation set**: broad, controlled performances across notes
   and controls (tone/attack/space).
3. **Student**: same interface, cheaper (single-period excitation;
   6 partials). Free parameters fitted by grid search.
4. **Loss audit** on held-out (unseen) passages: spectral distance,
   onset attack match, real-time factor, control monotonicity.
5. **Record**: the audit dict goes in the asset; `passes` is True only
   if all thresholds clear.

Thresholds: 6 dB spectral distance, 8 ms attack diff, real-time factor
<= 1.0, monotonic tone->brightness. These are the reference
tolerances; tighten them as the synths improve.

## What is interface vs implementation

- **Real**: the asset spec, the performance engine's musical decisions,
  the distillation workflow, the loss audit, the determinism guarantees.
- **Reference**: teacher and student are procedural DSP, not neural
  networks. A trained student would replace the parametric fit in step
  3 behind the same interface; the audit is model-agnostic.
- **Honest**: the student is simpler by construction; the audit measures
  the gap instead of hiding it.
