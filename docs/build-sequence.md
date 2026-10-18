# Build Sequence (Part 22)

Phases overlap where dependencies allow. After Phase 1, run structured
listening tests every cycle, find the biggest user-visible failure, and
improve that capability rather than scaling everything at once.

| Phase | Work | Versions | Exit |
|-------|------|----------|------|
| 0, Decisions | Audience, thresholds, tiers, languages, licensing, policy owner | V1 | Published targets document |
| 1, Foundations | Scene format, renderer, data pipeline, eval harness, consent registry | V2, V3, V4, V15, V19 | Prompt to scene to audio end to end; reproducibility passes; suite v0 |
| 2, Representation | Codec, renderer bake-off, baseline instrumental | V5 | Part 5 tests pass; bake-off published |
| 3, Vocals | Alignment, vocal renderer, controls, line regen | V7 | Part 7 tests per language |
| 4, Editing | Inpainting, continuation, section regen, locality | V12 | Part 12 tests pass |
| 5, Assets | Voice characters, instruments, preset inference | V8, V9, V10 | Parts 8/9/10 tests pass |
| 6, Artist profile | Profile, graph, explanations, corrections, scope | V11 | Part 11 tests pass |
| 7, Workflow | Timeline, takes, API, CLI, DAW export | V13, V14 | Part 14 tests pass |
| 8, Full-song planning | Song planning, coherence, richer controls | V6 | Part 6 coherence thresholds |
| 9, Efficiency/deploy | Tiers, job system, monitoring, security | V16, V18 | Part 18 tests pass |
| 10, Release | Gates, cards, datasheets, docs, open statement | V17, V20, V21, V22, V23 | Release checklist complete |
| 11, Expansion | Genres, languages, workflows by evaluation order | Future | Evaluation-driven |

Note: version numbers follow manual part order (V1=Part 1...V23=Part 23);
phases group them by dependency. Use `check_phase_gates.py` to verify
which phases have their versions shipped (reads git tags).
