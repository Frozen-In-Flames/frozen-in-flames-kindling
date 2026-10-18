# Architecture (Part 2)

The architecture is data, not prose. `kindling/architecture.py` holds the
seven principles (2.1), the seven layers and 34 components of the component
map (2.2), and the seven data flow stages (2.3). `kindling/interfaces.py`
holds one abstract base class per component: the documented contract.

## Principles

1. The scene is the source of truth.
2. Everything is inspectable and editable.
3. Locality over reroll.
4. Uncertainty is shown.
5. Identity is separate from performance.
6. Open and modular.
7. Consent and provenance are built in.

## Layers

Interface, workflow, intelligence, assets, generation, production, foundation.
Every component declares which hardware tiers (draft, studio, hosted) it
supports, per Part 1.4.

## Replacing a component

Because the map is data and the contracts are ABCs, any component can be
swapped for another implementation honoring the same interface:

```python
from kindling.architecture import REGISTRY, ComponentSpec

REGISTRY.register(ComponentSpec(
    name="Mixer",
    layer="production",
    interface="kindling.interfaces.Mixer",  # contract must not change
    tiers=["draft", "studio", "hosted"],
    description="My mixer",
    implementation="my_package.MyMixer",
))
```

The registry refuses a replacement that changes the interface path, so the
contract stays fixed while implementations come and go.

## Data flow

Input arrives (prompt, lyrics, MIDI, stems, or finished audio). The analyzer
and interpreter produce a draft scene with confidences. The user and planner
refine it. The orchestrator renders parts using assets and presets. The mixer
assembles the audio. The user inspects, edits the scene or a region, and
re-renders only what changed. Every step is saved as a version.

## Status

V2 ships the registry, the principles, the data flow, and the 34 interface
contracts. Implementations land one part at a time from V3 onward. Where the
manual requires trained models that do not exist yet, each version ships the
real interface, the evaluation harness, the extension points, and a
deterministic reference implementation, and documents which is which.
