# Project State, Versioning, and Reproducibility (Part 15)

## Project bundle (15.1)

`ProjectBundle`: scenes + version graph (child -> parents), pinned
asset versions, seeds, render settings, cached audio linked to exact
scene versions, and profile snapshots. Saves to `project.json` with a
SHA256 integrity manifest; `verify_integrity` checks it on load.

## Pinning (15.2)

`pin_render_inputs()`: SHA256 of the renderer, mixer, preset engine,
and tokenizer source plus the Kindling version, recorded for every
render. A render MUST be reproducible from its recorded inputs.

## Reproducibility levels (15.3)

`check_reproducibility(before, after, rate)`:
- **Level A**: bit-exact (sample-identical).
- **Level B**: perceptually equivalent (< 1 dB gated spectral distance).
- Otherwise: no level claimed, with an explicit note not to claim
  reproducibility.

The reference deterministic renderer achieves Level A on pinned
software; Level B is the honest claim across hardware. Never claim a
level you have not tested.

## Migration (15.4)

Scene schema uses semantic versioning (current 3.0.0).
`migrate_scene` walks 1.0.0 -> 2.0.0 -> 3.0.0 automatically and
returns every lossy step (default meta inserted, estimated lyric
timing, initialized automation/routing). Zero unreported loss: if it
is not in the `lossy` list, it did not happen.
