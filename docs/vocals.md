# Vocals and lyrics (Part 7)

Vocals are the hardest quality challenge, so they are their own system.

## Pronunciation (per-language G2P)

`kindling.vocals.g2p` phonemizes text into syllables with phonemes and
stress. Supported languages, tested separately and listed explicitly:

- **en**: English. Letter-to-sound rules with an exception lexicon,
  syllabification, stress heuristics, and elision ("every" is two
  syllables).
- **es**: Spanish. Near-phonetic mapping with real stress rules, including
  accent-marked stress and diphthong handling.

Any other language raises instead of guessing. Learned G2P models plug into
the `Phonemizer` interface.

## Alignment

`align_line()` aligns syllables to melody notes at syllable level: one
syllable per note normally, melisma when notes outnumber syllables, and
explicit unassigned status (with a warning, never silent) when syllables
outnumber notes. Every alignment carries a confidence.

## Expressive controls

`validate_performance()` covers all required controls: dynamics,
breathiness, vibrato rate and depth, belt, whisper, phrasing legato,
timing push/lay-back, doubles, and harmonies. Unknown or out-of-range
values raise instead of degrading silently.

## Reference vocal renderer

`ReferenceVocalRenderer` renders one lyric line deterministically: vowels
are harmonic tones with vibrato, fricatives are shaped noise, stops are
bursts, and every expressive control audibly changes the output. It is
honest about its limits in its own metadata: prosody and control path
only, not an intelligible singing voice. A learned singing model plugs
into the `VocalRenderer` interface.

## Line-level regeneration

`regenerate_line()` changes one lyric line: re-phonemize, re-align to the
line's notes, re-render only that line. The scene carries the new text and
alignment, the returned audio covers exactly the line's time range, and
every other line is listed as unchanged. Part 12 generalizes this into the
editing engine.

## Intelligibility

- `word_error_rate()` is the real WER computation.
- `TranscriptionModel` is the ASR interface; `wer_report()` runs the true
  acceptance path (transcribe, then score) and refuses to invent a
  transcript without a model.
- `ReferenceIntelligibility` runs deterministic proxy checks (syllable
  onset count, voicing ratio) and flags lines below threshold. Every report
  states it is a proxy. It flags the reference renderer's output, which is
  the system working as intended.

Blinded vocal-quality ratings by trained vocalists follow
`docs/listening-protocol.md`.
