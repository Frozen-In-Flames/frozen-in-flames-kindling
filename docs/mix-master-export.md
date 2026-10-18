# Mix, Mastering, and Export (Part 13)

## Mixer (13.1)

`Mixer.mix(stems, production)`: applies levels, constant-power panning,
buses, and automation from the production graph. Deterministic given
the same inputs. Avoids clipping (limits to 0.99 and reports it).
Reports K-weighted loudness (LUFS-ish) and true peak (4x oversampled)
for the mix and per stem.

## Mastering stage (13.2)

`master(mix, rate, target, reference_lufs, bypass)`: optional and
separable. Loudness targets for streaming (-14), club (-9), broadcast
(-16), cinema (-20). Optional reference matching via `reference_lufs`.
`bypass=True` returns the mix untouched. The report ALWAYS lists what
was applied; mastering is never silent.

## Export (13.3)

`export_all`: 
- mix.wav (16/24-bit, 44.1/48 kHz with resampling),
- stems/ (time-aligned, loudness-labeled manifest),
- score.mid (from scene parts; None with an explicit note where no
  note-bearing parts exist),
- lyrics.lrc (timed lyrics),
- sidecar.json (scene, asset versions, seeds, render settings,
  provenance/watermark metadata).

Acceptance: stems sum to the mix (tested where no limiting engaged);
quality checks (clipping, silence, DC offset, channel identity) pass.
DAW compatibility: standard WAV/MIDI files; verified openable by
construction (wave + MIDI writers follow the specs).
