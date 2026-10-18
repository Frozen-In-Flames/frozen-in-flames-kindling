# Listening test protocol (Part 5 and Part 17)

Automated metrics catch regressions. Professional quality requires
listening. This protocol covers codec reconstruction (Part 5) and, later,
generation quality (Part 17).

## Panel

- Minimum 8 listeners: at least 3 working musicians, producers, or
  engineers, plus ordinary listeners.
- Blind: listeners never know which system or setting produced a sample.
- Calibrated playback: listeners confirm their monitoring chain before
  the session.

## Material

- Drums, vocals, solo piano, dense mixes, and quiet material (Part 5).
- Later: the fixed suite across genres, languages, tempos, vocal types,
  song lengths, and prompt styles (Part 17).

## Method

- ABX for artifact detection: can the listener tell the reconstruction
  from the original?
- MUSHRA-style rating for quality: rate each sample 0 to 100 on
  timbre, transients, stereo image, and overall quality.
- Report inter-rater agreement. Publish the protocol, the results, and
  representative failure cases, not only selected demos.

## Release use

A codec or model release passes only if it clears both the automated
battery (`kindling.codec.eval`, later `kindling.eval`) and this protocol's
thresholds from `targets.yaml`.
