# V27 (web app v8): Word calibration

## Why

V26 gave the voice real English phonemes and a bounded profile retune,
but the readings still come from rules, and rules misread words in
known ways: "frozen" reads its first vowel short (AA) where the owner
sings it long (OW); "river" doubles its r; "houses" voices its s/z
cluster inconsistently. A profile-level warp cannot fix a wrong
reading, and until now nothing in the system could learn from the one
authority on how this voice actually says a word: the voice itself.

## The design (the owner's)

"Upload a sample of my voice from each of the words it struggles with
to give you data to mathematically inverse render a solution for the
failed words."

V27 implements that literally. For a selected voice character, the
Library gains **Calibrate words**: a target list, one take per word,
and a mathematical fit stored back into the profile. Product honesty,
stated in the app copy as well: **this is a calibration layer stored
as data inside the voice profile. It is not a trained model.**

## What was built

- **Target list** (`buildTargetList` in `web/js/calibration.js`):
  every word in the current Compose lyrics, plus probe words the
  rules read unaided and words matching known-miss patterns (doubled r
  after ER, s/z clusters, a vowel before a final -en). Each entry
  carries the word, its current phoneme reading, why it is listed, and
  its status: uncalibrated, calibrated (with the vowel heard), or
  rejected with the refusal reason.
- **Sample intake**: per word, record in the browser (microphone,
  MediaRecorder) or upload an audio file. The take is stored in the
  library's existing content-addressed IndexedDB audio store, attached
  to the voice with provenance (word, date, source: recorded or
  uploaded) under the same consent framing the library already uses
  for voice assets. One take per word is the design point.
- **Analysis** (`analyzeWordSample` in `web/js/analysis.js`): the
  take is framed and classified voiced by energy and zero-crossing
  rate; the vowel nucleus is the longest voiced segment; its F1/F2/F3
  track is measured with a tilt-compensated band-centroid estimator
  (the same style of spectral measurement the existing analysis code
  uses), alongside segment durations, coda energy presence, and the
  nucleus pitch.
- **Quality gate**: a take is refused, with a plain-language reason
  shown in the UI and stored as the word's status, when any of these
  hold: shorter than 0.2 s; nearly silent (peak below 0.02); clipped
  (more than 0.5% of samples at the rail); noise bed too high (peak
  frame level less than 3.5x the median level outside the word's
  energy extent); less than 0.10 s of voiced material; or no steady
  nucleus (steady core under 0.05 s with no real glide). A refused
  take writes no exception, no offsets, and no track. Never fit
  garbage silently.
- **The fit** (`web/js/calibrate.js` + `fitWordCalibration`): two
  products from one accepted sample.
  1. *Verified exception.* The produced vowel is identified
     differentially: every candidate vowel (10 steady, 5 diphthongs)
     is rendered in the word's own chunk context, at the sample's
     pitch, and measured with the same estimator, so the estimator's
     bias is present on both sides and cancels. The read vowel is the
     null hypothesis: a challenger must score at most 85% of the read
     vowel's distance and at least 0.03 better (weighted log space)
     before an exception is minted, so a near tie never rewrites a
     reading.
  2. *Inverse fit.* The estimator barely moves when a target moves
     (measured response is compressed, roughly a sixth of the target
     shift at sung pitches), so the solver first probes the
     estimator's actual response: the winning candidate is re-rendered
     with a known +0.12 log nudge per formant, and the measured
     movement becomes the gain. The correction is then
     delta = clamp(log(measured / reference) / gain, -0.40, +0.40)
     per formant, for the vowel's steady target or both diphthong
     endpoints, plus duration scalars for consonants adjacent to the
     nucleus. Corrections aggregate per phoneme across all of the
     voice's samples (median), so a correction learned from one word
     helps every other word sharing that phoneme.
- **Renderer application ladder** (`web/js/render.js`, minimal):
  for a note of a calibrated word, its solved track shapes that
  word's nucleus targets directly (track values are stored in target
  space, warped canonical plus solved delta, at the sample's own key
  timing; the raw measurements are kept separately as provenance).
  Beneath that, the aggregated phoneme offsets apply; beneath that,
  the V26 bounded profile warp; the floor is canonical. A voice with
  no calibration renders byte-identically to V26, pinned by exact
  numeric render pins in the test suite.

## Calibration data schema

JSON at `voice.payload.calibration`, designed so a future Python port
consumes the identical data:

```json
{
  "kind": "kindling/voice-calibration",
  "version": 1,
  "words": {
    "<word>": {
      "status": "calibrated | rejected",
      "reason": "refusal reason, when rejected",
      "date": "ISO timestamp",
      "source": "recorded | uploaded",
      "audioSha": "sha-256 of the stored take (audio store key)",
      "readingBefore": ["F", "R", "AA", "Z"],
      "producedVowel": "OW",
      "producedScore": 0.002,
      "heldByMargin": false,
      "fitMethod": "differential | centroid",
      "measured": {
        "median": [576, 1101, 1513], "early": [...], "late": [...],
        "glide": 0.05, "onsetDur": 0.14, "codaDur": 0.0,
        "codaPresent": false, "codaRatio": 0.0, "voicedSeconds": 0.56
      },
      "fit": {
        "phoneme": "OW",
        "dFrom": [0.13, -0.14, -0.01], "dTo": [0.17, -0.15, 0.03],
        "durScales": { "T": 0.94 }
      },
      "track": {
        "chunkIndex": 0, "nucleusPh": "OW",
        "keys": [{ "u": 0.2, "f": [673, 739, 2410] }]
      }
    }
  },
  "exceptions": {
    "<word>": {
      "phonemesByChunk": [["F", "R", "OW", "Z"], ["EH", "N"]],
      "measuredVowel": "OW", "from": "AA", "date": "ISO timestamp"
    }
  },
  "phonemeOffsets": {
    "OW": {
      "dFrom": [0.13, -0.14, -0.01], "dTo": [0.17, -0.15, 0.03],
      "samples": 1
    }
  }
}
```

Deltas (`d`, `dFrom`, `dTo`) are log-space formant corrections;
`dur` and `durScales` are duration multipliers. For steady vowels the
fit carries `d` instead of `dFrom`/`dTo`.

## Measured outcomes

From `tests-web/v27.test.mjs` (31/31; thresholds stated in the suite
before the results; mock samples fabricated with the synth itself
under known injected offsets; end-to-end distances average three
renders per variant to beat single-render segmentation jitter):

- **Solver recovery.** "goat" rendered with OW shifted by
  [ln 1.18, ln 0.88, 0]: recovered dFrom within [0.036, 0.014, 0.014]
  and dTo within [0.007, 0.020, 0.032] of the injected values
  (thresholds 0.06 for F1/F2, 0.08 for F3).
- **End-to-end.** The corrected "goat" render measures 0.16-0.20x as
  far from the mock sample as the plain render (threshold 0.5).
- **Negative control.** A zero-offset mock yields all deltas within
  0.041 of zero (bound 0.08) and mints no exception: no phantom
  calibration.
- **Exception minting.** The fabricated "frozen" (sung OW over a long
  stressed first syllable) is identified as OW with score 0.002
  against the next candidate's 0.028; the exception rewrites chunk 0
  from AA to OW, and the calibrated render's nucleus measures
  0.05-0.11x as far from the sample as the uncalibrated render
  (threshold 0.5).
- **Transfer.** The OW correction learned from "goat" alone, applied
  to "stone" (no sample of its own), cuts its distance to a
  same-voice "stone" mock to 0.24x of plain (threshold 0.6).
- **Quality gate.** Clipped (9.7% of samples at the rail),
  noise-only, and 0.15 s takes are each refused with their reason;
  the stored rejection leaves exceptions and offsets empty.
- **Regressions.** Five exact V26 render pins (voiced, whisper,
  profile-warped) reproduce to 1e-3 or better; the V26 suite stays
  80/80; the Python suite stays 238/238.

## Limits, stated plainly

- **One take per word is the design point, and one take has
  variance.** A sloppy take that passes the gate still fits its own
  noise. Retaking a word replaces its entry; aggregating more words
  that share a phoneme steadies the shared corrections (medians).
- **Spoken vs sung.** Formants do not depend on pitch, so speaking a
  word calibrates the same targets as singing it; the fit renders its
  references at the take's own pitch. Very high sung takes give the
  estimator fewer harmonics to read, so identification margins widen
  and borderline challenges are held to the read vowel more often.
- **Analysis confidence.** Identification is differential and
  margin-gated, but near vowels at low pitch sit close together in
  measured space; when the evidence is a near tie the system keeps
  the read vowel and fits offsets instead of minting an exception.
  That is the honest behavior for a single ambiguous take, and the
  stored record shows which happened (`heldByMargin`,
  `producedScore`).
- **Anchor assumption.** The fit anchors on the word's first
  vowel-bearing chunk and expects the sample's longest steady nucleus
  to be that chunk's vowel, as in a stressed first syllable. A take
  that dwells on a later syllable can anchor wrong; the produced
  vowel and score are stored so a bad fit is visible, and Clear
  removes it.
- **F3 is weakly observed** at pitches where the synth's spectrum
  caps early, so F3 corrections carry a wider tolerance in the tests
  and should be read as approximate.
- The Python engine does not yet consume the calibration layer; the
  schema is the contract for that port, as the phoneme-layer port was
  for V26.
