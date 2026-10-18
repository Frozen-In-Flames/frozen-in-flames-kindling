# Risks and Mitigations (Part 21)

| Risk | Early signal | Mitigation | Monitor |
| --- | --- | --- | --- |
| Vocals unintelligible or unstable | High word error rate; identity drift across sections | Treat vocals as a separate system; line-level evaluation; limit the declared language list | `monitor_vocal_risk` |
| Edits change too much | Large outside-mask difference | Local reconstruction in the codec; condition on surrounding audio; dependency-aware re-rendering | `monitor_edit_risk` |
| Long-form incoherence | Rater scores fall as length grows | Hierarchical planning; overlap and continuity conditioning; transition tests | `monitor_coherence_risk` |
| Voice misuse | Impersonation reports; consent failures | Verified consent; watermark and provenance; takedown channel | `MisuseMonitor` (Part 19) |
| Data rights uncertainty | Gaps in the license ledger | Policy owner; license filtering; legal review before large runs | `monitor_data_risk` |
| Profile collapses to generic output | Outputs converge on an average | Separate dimensions and modes; evidence-linked traits; correction tools | `monitor_profile_risk` |
| Preset inference overclaims | Transfer tests fail | Return alternatives with confidence; show fit on the reference | `monitor_preset_risk` |
| Scope creep | Too many genres, languages, features at once | One audience; explicit language list; phase gates | Manual: phase-gate review |
| Compute cost too high | Cost per generation above target | Tiers; distillation; staged previews | `Monitor` (Part 18) |
| Reproducibility drift | Old projects no longer re-render | Pin and hash everything; test at each release | `monitor_reproducibility_risk` |
| Demo bias | Strong demos, weak suite results | Frozen suites; publish failure cases | `monitor_demo_bias` |

Each monitor is a function returning `{"risk": name, "signal": value,
"threshold": t, "tripped": bool}`. Tripped monitors go to the release
gate review (Part 17).
