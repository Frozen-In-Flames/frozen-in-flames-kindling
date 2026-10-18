"""Kindling architecture registry (Build Manual Part 2).

The component map from Part 2.2 is data, not prose. Every component in the
system is registered here with its layer, its interface, the hardware tiers it
supports (Part 1.4: every feature states its tiers), and a description. Because
the map is data, the test suite can prove the implementation covers the whole
map, and any component can be replaced with a compatible implementation
(Part 2.1 principle 6: open and modular).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

TIERS = ("draft", "studio", "hosted")

PRINCIPLES = [
    {
        "id": "scene-source-of-truth",
        "title": "The scene is the source of truth",
        "statement": (
            "Rendered audio is derived and can always be regenerated from "
            "the scene, assets, seeds, and settings."
        ),
    },
    {
        "id": "inspectable",
        "title": "Everything is inspectable and editable",
        "statement": "No hidden intermediates the user cannot see or change.",
    },
    {
        "id": "locality",
        "title": "Locality over reroll",
        "statement": "A targeted edit changes the target.",
    },
    {
        "id": "uncertainty-shown",
        "title": "Uncertainty is shown",
        "statement": (
            "Inferred things carry confidence and alternatives. Insufficient "
            "input produces a warning, not a quiet guess."
        ),
    },
    {
        "id": "identity-vs-performance",
        "title": "Identity is separate from performance",
        "statement": (
            "A voice or instrument stays itself while its performance changes."
        ),
    },
    {
        "id": "open-modular",
        "title": "Open and modular",
        "statement": (
            "Each component has a documented interface and can be replaced."
        ),
    },
    {
        "id": "consent-provenance",
        "title": "Consent and provenance are built in",
        "statement": "Built in, not bolted on (Part 19).",
    },
]

LAYERS = [
    "interface",
    "workflow",
    "intelligence",
    "assets",
    "generation",
    "production",
    "foundation",
]

# The component map, Part 2.2. interface is the dotted path of the ABC that
# documents the component contract in kindling.interfaces.
_COMPONENT_ROWS = [
    # interface layer
    ("Timeline editor", "interface", "kindling.interfaces.TimelineEditor",
     ["draft", "studio", "hosted"], "Timeline view and editing of the scene: sections, parts, lyrics, automation."),
    ("Lyric editor", "interface", "kindling.interfaces.LyricEditor",
     ["draft", "studio", "hosted"], "Lyric writing with section markers, syllable timing, and phrasing marks."),
    ("Asset library", "interface", "kindling.interfaces.AssetLibrary",
     ["draft", "studio", "hosted"], "Browse, version, and manage voice characters, instruments, and presets."),
    ("Profile browser", "interface", "kindling.interfaces.ProfileBrowser",
     ["draft", "studio", "hosted"], "Inspect the artist profile: dimensions, evidence, modes, corrections."),
    ("A/B and version compare", "interface", "kindling.interfaces.VersionCompare",
     ["draft", "studio", "hosted"], "Compare takes and scene versions side by side, undo, branch."),
    ("CLI", "interface", "kindling.interfaces.CommandLine",
     ["draft", "studio", "hosted"], "Command line tool that renders a saved scene reproducibly."),
    ("API", "interface", "kindling.interfaces.PublicAPI",
     ["draft", "studio", "hosted"], "Versioned, documented API for scenes, renders, edits, assets, profiles, exports."),
    ("DAW bridge", "interface", "kindling.interfaces.DAWBridge",
     ["studio", "hosted"], "Export stems with tempo and meter maps; import MIDI and stems."),
    # workflow layer
    ("Project service", "workflow", "kindling.interfaces.ProjectService",
     ["draft", "studio", "hosted"], "Owns projects: scenes, version graphs, assets, jobs, exports."),
    ("Scene store", "workflow", "kindling.interfaces.SceneStore",
     ["draft", "studio", "hosted"], "Immutable scene versions, branches, diffs, merges, content addressed asset refs."),
    ("Version graph", "workflow", "kindling.interfaces.VersionGraph",
     ["draft", "studio", "hosted"], "Directed graph of scene versions with readable diffs and merge conflicts."),
    ("Job queue", "workflow", "kindling.interfaces.JobQueue",
     ["draft", "studio", "hosted"], "Queues, retries, cancellation, progress, idempotent submission, recovery."),
    ("Render orchestrator", "workflow", "kindling.interfaces.RenderOrchestrator",
     ["draft", "studio", "hosted"], "Turns a scene version into render jobs across parts, then the mix."),
    # intelligence layer
    ("Prompt interpreter", "intelligence", "kindling.interfaces.PromptInterpreter",
     ["draft", "studio", "hosted"], "Converts natural language, tags, lyrics, and controls into a draft scene."),
    ("Composition planner", "intelligence", "kindling.interfaces.CompositionPlanner",
     ["draft", "studio", "hosted"], "Proposes form, harmony, motifs, energy curve, arrangement; offers alternatives."),
    ("Arrangement assistant", "intelligence", "kindling.interfaces.ArrangementAssistant",
     ["draft", "studio", "hosted"], "Suggests what to add, remove, or develop per section from profile context."),
    ("Profile engine", "intelligence", "kindling.interfaces.ProfileEngine",
     ["draft", "studio", "hosted"], "Builds and maintains the explainable artist profile from uploads."),
    ("Reference analyzer", "intelligence", "kindling.interfaces.ReferenceAnalyzer",
     ["draft", "studio", "hosted"], "Analyzes finished audio into a draft scene and into preset proposals."),
    # assets layer
    ("Voice characters", "assets", "kindling.interfaces.VoiceCharacterStore",
     ["draft", "studio", "hosted"], "Saved, versioned singing identities with consent records."),
    ("Virtual instruments", "assets", "kindling.interfaces.InstrumentStore",
     ["draft", "studio", "hosted"], "Reusable instruments that perform parts musically, with distillation audits."),
    ("Production presets", "assets", "kindling.interfaces.PresetStore",
     ["draft", "studio", "hosted"], "Editable production graphs inferred from or applied to audio."),
    # generation layer
    ("Audio codec and latent space", "generation", "kindling.interfaces.AudioCodec",
     ["draft", "studio", "hosted"], "Compressed representation preserving musical detail; supports region decode."),
    ("Song renderer", "generation", "kindling.interfaces.SongRenderer",
     ["draft", "studio", "hosted"], "Renders scene, assets, and preset into audio behind a stable interface."),
    ("Vocal renderer", "generation", "kindling.interfaces.VocalRenderer",
     ["draft", "studio", "hosted"], "Renders vocal parts from voice characters with expressive controls."),
    ("Instrument renderer", "generation", "kindling.interfaces.InstrumentRenderer",
     ["draft", "studio", "hosted"], "Renders parts through virtual instruments with musical controls."),
    ("Editing models", "generation", "kindling.interfaces.EditingModels",
     ["studio", "hosted"], "Continuation, inpainting, replacement, and regeneration of selected regions."),
    # production layer
    ("Preset renderer", "production", "kindling.interfaces.PresetRenderer",
     ["draft", "studio", "hosted"], "Applies a production preset graph to rendered parts."),
    ("Mixer", "production", "kindling.interfaces.Mixer",
     ["draft", "studio", "hosted"], "Deterministic mix from the production graph and scene; reports loudness."),
    ("Mastering stage", "production", "kindling.interfaces.MasteringStage",
     ["studio", "hosted"], "Optional, separable loudness targets and reference matching; never silent."),
    ("Export", "production", "kindling.interfaces.Exporter",
     ["draft", "studio", "hosted"], "Mixed audio, stems, MIDI, lyrics with timing, scene sidecar, provenance."),
    # foundation layer
    ("Data pipeline", "foundation", "kindling.interfaces.DataPipeline",
     ["hosted"], "Reproducible ingestion, labeling, splits, provenance, deletion propagation."),
    ("Training stack", "foundation", "kindling.interfaces.TrainingStack",
     ["hosted"], "Staged training with exit gates, ablations, checkpoint manifests."),
    ("Evaluation harness", "foundation", "kindling.interfaces.EvaluationHarness",
     ["draft", "studio", "hosted"], "Fixed suites, automatic checks, listening protocols, transfer tests, reporting."),
    ("Provenance and consent registry", "foundation", "kindling.interfaces.ProvenanceRegistry",
     ["draft", "studio", "hosted"], "Consent records, provenance metadata, watermark verification, deletion cascade."),
]

DATA_FLOW = [
    {"stage": 1, "name": "input",
     "description": "Input arrives: prompt, lyrics, MIDI, stems, or finished audio."},
    {"stage": 2, "name": "draft-scene",
     "description": "The analyzer and interpreter produce a draft scene with confidences."},
    {"stage": 3, "name": "refine",
     "description": "The user and planner refine it."},
    {"stage": 4, "name": "render",
     "description": "The orchestrator renders parts using assets and presets."},
    {"stage": 5, "name": "mix",
     "description": "The mixer assembles the audio."},
    {"stage": 6, "name": "revise",
     "description": "The user inspects, edits the scene or a region, and re-renders only what changed."},
    {"stage": 7, "name": "version",
     "description": "Every step is saved as a version."},
]


@dataclass
class ComponentSpec:
    name: str
    layer: str
    interface: str
    tiers: List[str] = field(default_factory=list)
    description: str = ""
    implementation: Optional[str] = None

    def supports(self, tier: str) -> bool:
        return tier in self.tiers


def build_component_map() -> List[ComponentSpec]:
    return [ComponentSpec(name=n, layer=l, interface=i, tiers=list(t), description=d)
            for n, l, i, t, d in _COMPONENT_ROWS]


class ComponentRegistry:
    """The live registry. Components are replaceable: register() with the same
    name swaps the implementation while the interface contract stays fixed."""

    def __init__(self, components: Optional[List[ComponentSpec]] = None):
        self._components: Dict[str, ComponentSpec] = {}
        for spec in components if components is not None else build_component_map():
            self._components[spec.name] = spec

    def get(self, name: str) -> ComponentSpec:
        return self._components[name]

    def by_layer(self, layer: str) -> List[ComponentSpec]:
        return [s for s in self._components.values() if s.layer == layer]

    def by_tier(self, tier: str) -> List[ComponentSpec]:
        return [s for s in self._components.values() if s.supports(tier)]

    def names(self) -> List[str]:
        return sorted(self._components.keys())

    def register(self, spec: ComponentSpec) -> None:
        """Register or replace a component implementation. The interface path
        must stay the same so the contract is unchanged."""
        existing = self._components.get(spec.name)
        if existing is not None and existing.interface != spec.interface:
            raise ValueError(
                "Refusing to replace %r: interface contract changed from %s to %s"
                % (spec.name, existing.interface, spec.interface)
            )
        self._components[spec.name] = spec

    def interface_type(self, name: str) -> Type:
        """Resolve the ABC for a component name (lazy import, no cycles)."""
        import importlib
        path = self._components[name].interface
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)


REGISTRY = ComponentRegistry()
