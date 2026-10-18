# Functional milestone A: upload / save / use loop (V24)

Phase A wires the end-to-end loop in Python: upload your own audio, save it
as a versioned asset in an on-disk library, render a song from a prompt and
lyrics using those saved assets, download the results. Proven with real
audio, not fixtures.

## The loop

```
kindling library upload track.wav --kind voice --name "Aries" \
    --consent-subject "Aries Hilton"
kindling library upload groove.wav --kind instrument --name "My Groove" \
    --role guitar
kindling library upload finished.wav --kind preset --name "My Chain"
kindling library list
kindling render --prompt "dark driving verse and chorus, 100 bpm" \
    --lyrics-file lyrics.txt --voice voice_aries \
    --instrument guitar=inst_my_groove --preset preset_my_chain \
    --seed 7 --out song/
kindling export song/ --format stems --out song-stems/
```

The library lives at `~/.kindling/library` by default (`--library` overrides
it). Assets are JSON records; source audio is stored content-addressed
(sha256) under `audio/`. Deleting an asset removes its record and its audio
when no other asset references it.

## What each kind does

- **voice**: the reference is analyzed (pitch range, dynamics, registers,
  vowel states, sufficiency report) and saved as a voice character.
  Creating one requires a consent record: `--consent-subject NAME` for a
  personal voice, or `--rights-basis licensed|synthetic`. Rendering through
  the character checks consent, revocation, and per-performance sufficiency
  before any audio is made.
- **instrument**: the recording is sliced at detected onsets into a sample
  map with per-slice root pitch. At render time slices are pitched to the
  part's notes. Material with no stable pitch is marked unpitched and plays
  cyclically.
- **preset**: inverse rendering infers an editable effect graph from the
  finished track, with alternatives and confidence. The preset applies to
  the mix bus at render time.

## Honest boundaries of this milestone

- The vocal renderer is the reference procedural renderer: prosody and
  expressive-control path only, not an intelligible singing voice. A
  learned vocal model plugs into the same interface.
- Uploaded instruments are sample maps, not learned instruments.
- The preset chain is real DSP (shelves, compressor, delay, widener)
  inferred from measurements, with stated confidence and alternatives.
- Voice character `voice_aries` was built from a mastered full mix, not an
  isolated vocal, so its identity vector includes mix bleed. An a cappella
  reference would sharpen it later. This is recorded on the asset.

## Proven run (2026-10-17)

- Voice: `voice_aries` ingested from `voice-characters/aries_v1.json` with
  the reference WAV.
- Instrument: `inst_guitar_bassline_mix` from the owner's
  `Guitar___Bassline_Direct_Mix.wav` (130 pitched slices).
- Preset: `preset_gbm_production` from the same mix (highshelf, delay,
  widener; confidence 0.73).
- Render: 2 sections (verse, chorus), 4 lyric lines, seed 7. Outputs:
  `mix.wav` (non-silent, -17.3 LUFS, -0.4 dBFS true peak), 6 stems,
  `score.mid`, `lyrics.lrc`, `sidecar.json` with asset versions, seed,
  and provenance. Stems sum to the pre-preset mix within 2e-4.
  Same seed renders byte-identical audio.
