# Training Program (Part 16)

Train in stages. Each stage has an exit gate; do not start the next
stage at scale until the gate is met.

## Stages

| # | Stage | Exit gate |
|---|-------|-----------|
| 1 | Audio representation | Codec spectral error < 3 dB on test signals |
| 2 | General music | Reference bakeoff passes (the bar to beat) |
| 3 | Lyrics and vocals | Part 7 acceptance per language |
| 4 | Conditioning | Instruction-following and locality thresholds |
| 5 | Asset models | Parts 8/9/10 acceptance (distillation audit) |
| 6 | Preference tuning | Blinded preference gain, no regressions |
| 7 | Efficiency | Real-time factor <= 1.0 on Draft/Studio tiers |

`check_all_stages` runs gates in order and stops at the first failure,
naming the blocked stage. Instrumental generation, singing, and
editing are evaluated independently before any claim of general
strength.

## Practices (enforced in code)

- **Ablations**: `Ablation` runs small-scale variants and records the
  decision each one informed.
- **Checkpoints**: `Checkpoint` stores config, data manifest, seeds,
  and code revision. `RegressionSuite.evaluate` blocks promotion on
  any regression.
- **Preference data**: versioned and auditable (protocol in Part 17).
- **Never tune on test sets**: `TestSetGuard` hashes test IDs and
  refuses `train` purpose on them.

## Honest status

No models are trained yet. This part builds the program: the stages,
the gates, and the practices as runnable infrastructure. When training
begins, it runs through these gates; until then the gates run against
the reference implementations.
