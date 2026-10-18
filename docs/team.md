# Team and Resources (Part 20)

## Roles

| Role | Responsibility | Manual parts |
| --- | --- | --- |
| Audio and music-generation research | Codec, renderers, vocal models, editing models | 5, 6, 7, 9, 12 |
| Music information retrieval and DSP | Analysis, alignment, source separation, preset inference, mixer | 4, 7, 10, 13 |
| Training and inference engineering | Distributed training, efficient inference, deployment tiers | 16, 18 |
| Data engineering and evaluation | Pipeline, data browser, test suites, metrics, listening studies | 4, 17 |
| Music practitioners | Songwriters, producers, vocalists, mixers who judge output and shape the product | 6, 7, 11, 17 |
| Product, frontend, backend, tooling | Interface, scene store, API, CLI, DAW bridge | 3, 14, 15 |
| Trust, safety, and legal | Consent systems, provenance, policy, licensing | 8, 19 |
| Release, documentation, community | Packaging, docs, support, contributor process | 20, 21, 22, 23 |

## Rule of ownership

Every Part of this manual has one named owner who is accountable for
its acceptance tests. The CODEOWNERS file maps each part's paths to
its owner. Currently all roles are held by Frozen In Flames (Aries
Hilton). As the team grows, reassign CODEOWNERS lines to the named
owner; the rule does not change.

## Cost drivers

Sustained expert labor, experimentation, compute, storage, audio
review, and long-term maintenance. A small team can build a compelling
focused system. Broad, polished coverage across genres, languages,
vocals, editing, and hardware is a much larger undertaking, so scope
to the audience chosen in Part 1.

## Current status

Solo build: all 23 parts implemented by the owner with AI assistance.
The architecture (Part 2) keeps every component replaceable, so
specialists can take ownership of parts without rewriting the system.
