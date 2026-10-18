# Vocal separation (classical DSP)

`kindling/assets/separate.py` splits a finished mix into a vocal estimate
and an accompaniment estimate with classical DSP only: numpy and scipy,
no learned models, no downloaded weights, no GPU, deterministic. It exists
for one job: cleaning reference audio before voice analysis, so a voice
character's identity vector carries less bleed from the beat.

## How it works

Two cues, combined per time-frequency bin (STFT, 2048-point Hann, 75%
overlap):

1. **Center channel.** In mastered mixes the lead vocal sits panned
   center. Each bin scores centeredness from the mid/side power ratio,
   softly sharpened. Wide-panned content scores near zero.
2. **Repeating background (REPET-style).** Loop-based accompaniment
   repeats; the vocal does not. The loop period comes from autocorrelation
   of the 40-150 Hz kick-band energy envelope: the kick repeats with the
   beat and the voice lives above it, so the beat's repetition survives
   even when a loud vocal dominates the broadband envelope. The repeating
   spectrogram is the element-wise median across whole periods; bins that
   match it are accompaniment.

A bin must look both centered and non-repeating to count as vocal. That
is the whole trick: kick and bass are centered but they repeat, so the
repetition cue rejects them; wide hats and stereo instruments may not
repeat in place, but the center cue rejects them.

`separate_vocals(audio, sample_rate)` takes mono `(N,)` or stereo
`(2, N)` and returns `(vocal, accompaniment)` in the same layout, with
sample counts preserved exactly. The two estimates sum back to the
mixture.

## Use in voice analysis

`analyze_reference(..., separate_vocals=False)` keeps its default
behavior exactly. With `separate_vocals=True` (and `stereo=...`), the
vocal is isolated first, mixed to mono, conditioned with a 120 Hz
highpass against residual kick and bass rumble, then analyzed. The
summary records the separation under `"separation"` so provenance always
shows how a reference was made.

## Measured performance

On synthetic mixtures with known ground truth (vocal-like harmonic line
with vibrato over a tiled 2 s drum/bass loop, `tests/test_separate.py`):

- Vocal SDR: 7.2 dB (mixture) to 26.0 dB, +18.7 dB
- Vocal SIR: 7.2 dB to 30.9 dB, +23.6 dB
- Accompaniment SDR: -7.2 dB to 19.4 dB, +26.6 dB
- Spectral centroid of the analysis: 1334 Hz mixed, 1132 Hz separated,
  846 Hz true vocal. The bleed is reduced, not gone.

## Honest limits

- Works best on centered vocals over repetitive beats. That is the shape
  of a loop-built catalog, which is why this method was chosen.
- Residual bleed remains on wide-panned ad-libs, heavy vocal reverb
  tails, and anything the accompaniment does once and never repeats.
- Very short clips (under a few loop repetitions) fall back to a global
  median background; quality degrades gracefully, not silently.
- It is a bleed reducer for reference analysis, not a studio stem
  splitter. A learned separator would win on difficult material; this
  one wins on zero cost, zero weights, and running anywhere.

## A note on voice_aries v1

The first voice character (`voice-characters/aries_v1.json`) was built
WITHOUT separation, from the mono mixdown directly, on purpose: it is
the first reference, kept as the honest record of where the work
started, mix bleed included. Separation is opt-in for future characters.
