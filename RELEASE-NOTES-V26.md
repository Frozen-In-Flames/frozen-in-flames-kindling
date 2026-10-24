# V26 (web app v7): Words you can hear

## What was wrong

The field report was exact: generated tracks had a vocal line with no
audible English in it. The audit found why, in the old `render.js`:

- Every syllable got ONE static formant pair, chosen from its first vowel
  letter and frozen for the whole note. Real vowels in real words are
  trajectories; a frozen vowel is a sung "ahh", not a syllable.
- Only a syllable's first letter could make a consonant, and only two
  existed (a generic fricative tick, a generic stop tick). Ending
  consonants were never rendered at all. Nasals, liquids, and affricates
  did not exist.
- Worst: when the lyric's vowel was outside the voice profile's observed
  vowel set, the profile's first observed vowel REPLACED it. The
  adaptation was eating the words.

## The design (the owner's)

"The words were first generated in white noise then retuned to match the
voice profile, so that a text to speech actually has a base of real
English, but we don't miss the biometric adaption of the user."

That is the classic source-filter split, and V26 implements it literally:

1. **The words exist first, independent of any voice.** A new phoneme
   layer (`web/js/phonemes.js`) turns lyrics into an English phoneme
   score: rule-based grapheme-to-phoneme plus a 130-entry exception
   dictionary, a 39-phoneme inventory (10 vowels, 5 diphthongs, 24
   consonants), aligned to the existing syllable/note timing by letter
   spans, so every note knows its onsets, its nucleus, and its codas.
2. **A whisper substrate.** In whisper mode the whole line renders on
   noise excitation alone, pushed through the same moving formant track:
   words carried by shaped noise, no pitch. This is also physically how
   fricatives work, so the same noise path articulates s, sh, f, th
   inside the sung render.
3. **The retune is a bounded transform.** The sung render swaps in a
   harmonic source at the melody pitch (with the profile's vibrato and
   belt, as before) and warps each formant target at most 25% of the
   log-space distance toward the profile's nearest observed vowel
   centroid, clamped to 180-3800 Hz. The warp moves Hz values. It cannot
   move, drop, or replace a phoneme; the regression test below pins that.

## What the renderer does now

Per note: onsets and codas take their articulation times (scaled together
if the note is short), the nucleus takes the rest and carries the pitch.
F1/F2/F3 interpolate smoothly (log-space, smoothstep) between phoneme
targets across the whole syllable; diphthongs are two-target glides.
Excitation is per phoneme: vowels, liquids, glides, and nasals use the
harmonic source (nasals at murmur gain with their own low formant
targets); fricatives use band-shaped noise, voiced ones with the harmonic
source mixed in; stops are closure (silent, or a low murmur when voiced)
plus a place-shaped burst plus a voice-onset-time gap; affricates flow
from closure into their fricative. Noise shaping uses a double peaking-EQ
cascade tracking the formant targets (one pass leaves white noise too
flat between formants; a whisper's identity lives in the valleys too).

## Measured outcomes

Web DSP suite `tests-web/v26.test.mjs` (**80 passed, 0 failed**;
thresholds are stated in the file ahead of its results):

- **G2P battery:** 54/54 words produce the exact expected phoneme
  sequence, including the exception set, diphthong words (fire, night,
  my), and coda words (heart, world).
- **Chunk parity:** phoneme chunks match `compose.syllabify` exactly on
  all battery lines, and every chunk carries a vowel nucleus.
- **Diphthong trajectory:** "night" (AY) measured F1 falls 587 to 393 Hz
  and F2 rises 985 to 1766 Hz from early to late nucleus (bars: fall
  >= 100, rise >= 200). The old synth could not move at all.
- **Steady vowel:** "ha" (AH) measures F1 436 Hz, F2 904 Hz against
  targets [520, 1190], inside the stated +/-30% bar.
- **Coda presence:** "heart" shows the stop-closure dip (energy ratio
  0.00-0.05 vs the "ha" control, bar <= 0.70) and a tail burst in the
  3.5-7 kHz band where the control has essentially none.
- **Fricative:** "see" onset carries 4-8 kHz band energy; the vowel-only
  control sits at the measurement floor in the same window.
- **VOT:** burst-to-voicing measures 17 ms for "ba" and 64 ms for "pa",
  a 47 ms difference (bar >= 25 ms). This test initially asserted on raw
  vowel-onset difference, which conflates the (by-design) closure
  durations and understated the gap as 20 ms; the assertion was restated
  on VOT itself, the quantity that distinguishes the two stops, with the
  reasoning recorded in the test.
- **Regression (the vowel swap):** with a profile that observed only AA,
  "see" renders with measured F1 264 Hz / F2 1830 Hz, closer in log space
  to the warped IY target [346, 1902] than to AA [730, 1090] on both
  axes. Pre-V26, this render would have sung AA outright.
- **Whisper mode:** pitch strength 0.14 (bar <= 0.35) against the voiced
  render's 0.97, while the per-phoneme formant-band profile still
  correlates with the voiced render at r = 0.77 (bar >= 0.55). The words
  are in the noise; the pitch is not.
- **Melody pitch:** voiced render's dominant pitch is 220.5 Hz for a
  220 Hz note (bar +/-3%).

Full Python suite: **238 passed**, unchanged by this version (baseline
measured on the same tree before these notes were written).

## Honest limits

- This is formant synthesis, not a learned singer. Expect clearly
  articulated, unmistakably synthetic words, closer to a vocoder poet
  than to a studio vocalist. At high sung pitches the harmonics sample
  the formant envelope sparsely and vowels read less distinctly; the
  measurements above already show formant estimates landing somewhat
  inside their targets at pitch (AH's F2 at 904 vs the 1190 target).
- G2P is rules plus exceptions, not a dictionary of English. Known
  misses: the long-vowel-in-open-syllable heuristic is incomplete
  ("frozen" scores F R AA Z EH N, not F R OW Z AH N); a doubled rhotic
  can appear after r-controlled vowels ("river" ends ER R); "houses"
  doubles its final s. The exception dictionary is data, and grows by
  adding lines.
- The whisper's noise shaping is a tracking EQ cascade, not a physical
  resonator bank; intelligibility is at the phoneme-cue level.
- The Python engine does not yet have the phoneme layer. Porting
  `phonemes.js` to the Python renderer with the same battery is the
  documented follow-up, deliberately not folded into this version.

## Follow-up

- Python parity port of the phoneme layer and renderer (same tests).
- Grow the exception dictionary from real lyric sheets.
- Per-phoneme duration modeling (stressed vs unstressed nuclei) once the
  scene layer carries stress marks.
