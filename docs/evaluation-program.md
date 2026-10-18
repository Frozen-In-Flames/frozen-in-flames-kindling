# Evaluation Program (Part 17)

Automatic metrics catch regressions. Professional quality requires
listening.

## Fixed suite (17.1)

`build_suite()`: frozen prompts across genres, languages, tempos,
vocal types, lengths, and prompt styles. `build_held_out()`: hard set
(jazz/scat, metal/growl, ambient) never used in training. Versioned
(`SUITE_VERSION`), refresh on a published quarterly schedule; the
Part 16 `TestSetGuard` prevents leakage into training.

## Human evaluation (17.2)

`HUMAN_PROTOCOL`: blinded A/B, raters (musicians, producers,
vocalists, listeners), six dimensions (prompt adherence, composition,
vocal quality, coherence, production, edit success), 1-5 scale.
`inter_rater_agreement`: mean pairwise rater correlation.

## Automatic checks (17.3)

`check_tempo_key` (onset autocorrelation), `check_audio_quality`
(clipping/silence/DC/clicks/channels), `check_identity_similarity`,
`check_edit_locality` (outside-mask distance + seams),
`check_reproducibility_declared` (achieved vs declared level).

## Transfer tests (17.4)

Voice on new lyrics, preset on a different song, distilled
instrument on unseen passages, asset-change stability, edit
predictability. Each returns pass/fail with evidence.

## Reliability (17.5)

`reliability_report`: render across seeds, report pass rate and
severe-failure rate. A system that impresses once but fails
unpredictably is not shippable.

## Reporting (17.6) and release gates (17.7)

`model_card`, `datasheet`, and `check_release_gates` (quality,
vocals, editing, assets, reliability, reproducibility, safety,
documentation). All eight must pass; blockers are named.
