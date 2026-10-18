"""Component interfaces (Build Manual Part 2.2).

One abstract base class per component in the architecture registry. These are
the documented contracts: every implementation, reference or learned, honors
them, and any implementation can be replaced by another honoring the same
contract (Part 2.1 principle 6). Later versions implement these interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional


class Component(ABC):
    """Base contract every Kindling component honors."""

    @property
    @abstractmethod
    def component_name(self) -> str:
        """Name matching the architecture registry."""

    @property
    @abstractmethod
    def supported_tiers(self) -> List[str]:
        """Hardware tiers this implementation supports (Part 1.4)."""

    def describe(self) -> Dict[str, Any]:
        return {"name": self.component_name, "tiers": self.supported_tiers}


# ---------------------------------------------------------------- interface
class TimelineEditor(Component):
    @abstractmethod
    def open_scene(self, scene_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def select(self, target: Dict[str, Any]) -> Dict[str, Any]: ...


class LyricEditor(Component):
    @abstractmethod
    def set_lyrics(self, scene_id: str, lines: List[Dict[str, Any]]) -> Dict[str, Any]: ...
    @abstractmethod
    def align_syllables(self, scene_id: str, vocal_part_id: str) -> Dict[str, Any]: ...


class AssetLibrary(Component):
    @abstractmethod
    def list_assets(self, kind: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def get_asset(self, asset_id: str, version: Optional[str] = None) -> Dict[str, Any]: ...


class ProfileBrowser(Component):
    @abstractmethod
    def show_profile(self, profile_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def show_evidence(self, trait_id: str) -> List[Dict[str, Any]]: ...


class VersionCompare(Component):
    @abstractmethod
    def diff(self, old_id: str, new_id: str) -> List[str]: ...
    @abstractmethod
    def compare_audio(self, old_id: str, new_id: str) -> Dict[str, Any]: ...


class CommandLine(Component):
    @abstractmethod
    def run(self, argv: List[str]) -> int: ...


class PublicAPI(Component):
    @abstractmethod
    def openapi(self) -> Dict[str, Any]: ...
    @abstractmethod
    def handle(self, method: str, path: str, body: Dict[str, Any]) -> Dict[str, Any]: ...


class DAWBridge(Component):
    @abstractmethod
    def export_stems(self, project_id: str, destination: str) -> List[str]: ...
    @abstractmethod
    def import_midi(self, path: str) -> Dict[str, Any]: ...
    @abstractmethod
    def import_stems(self, paths: List[str]) -> Dict[str, Any]: ...


# ---------------------------------------------------------------- workflow
class ProjectService(Component):
    @abstractmethod
    def create_project(self, name: str) -> Dict[str, Any]: ...
    @abstractmethod
    def get_project(self, project_id: str) -> Dict[str, Any]: ...


class SceneStore(Component):
    @abstractmethod
    def save_version(self, scene: Dict[str, Any], parent_id: Optional[str] = None) -> str: ...
    @abstractmethod
    def load_version(self, version_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def branch(self, version_id: str, name: str) -> str: ...
    @abstractmethod
    def merge(self, ours_id: str, theirs_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def diff_versions(self, old_id: str, new_id: str) -> List[str]: ...


class VersionGraph(Component):
    @abstractmethod
    def parents(self, version_id: str) -> List[str]: ...
    @abstractmethod
    def children(self, version_id: str) -> List[str]: ...
    @abstractmethod
    def history(self, version_id: str) -> List[str]: ...


class JobQueue(Component):
    @abstractmethod
    def submit(self, job: Dict[str, Any], idempotency_key: Optional[str] = None) -> str: ...
    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...
    @abstractmethod
    def status(self, job_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def wait(self, job_id: str, timeout: Optional[float] = None) -> Dict[str, Any]: ...


class RenderOrchestrator(Component):
    @abstractmethod
    def render(self, scene_version_id: str, tier: str = "draft") -> Dict[str, Any]: ...
    @abstractmethod
    def render_plan(self, scene_version_id: str) -> List[Dict[str, Any]]: ...


# ---------------------------------------------------------------- intelligence
class PromptInterpreter(Component):
    @abstractmethod
    def interpret(self, prompt: str, **controls: Any) -> Dict[str, Any]:
        """Return a draft scene plus an explicit assumptions list."""


class CompositionPlanner(Component):
    @abstractmethod
    def plan(self, scene: Dict[str, Any], profile_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
    @abstractmethod
    def alternatives(self, scene: Dict[str, Any], element: str, count: int = 3) -> List[Dict[str, Any]]: ...


class ArrangementAssistant(Component):
    @abstractmethod
    def suggest(self, scene: Dict[str, Any], section_id: str) -> List[Dict[str, Any]]: ...


class ProfileEngine(Component):
    @abstractmethod
    def ingest_upload(self, profile_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def explain(self, profile_id: str, suggestion_id: str) -> Dict[str, Any]: ...


class ReferenceAnalyzer(Component):
    @abstractmethod
    def analyze(self, audio_ref: Dict[str, Any]) -> Dict[str, Any]:
        """Return a draft scene with confidences, never a quiet guess."""


# ---------------------------------------------------------------- assets
class VoiceCharacterStore(Component):
    @abstractmethod
    def create(self, reference_summary: Dict[str, Any], consent_record: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def revoke(self, voice_id: str) -> None: ...
    @abstractmethod
    def sufficiency_report(self, voice_id: str, performance: Dict[str, Any]) -> Dict[str, Any]: ...


class InstrumentStore(Component):
    @abstractmethod
    def create(self, spec: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def distill(self, teacher_id: str, target_tier: str) -> Dict[str, Any]: ...


class PresetStore(Component):
    @abstractmethod
    def save_preset(self, preset: Dict[str, Any]) -> str: ...
    @abstractmethod
    def infer_from_reference(self, analysis: Dict[str, Any]) -> Dict[str, Any]: ...


# ---------------------------------------------------------------- generation
class AudioCodec(Component):
    @abstractmethod
    def encode(self, audio: Any) -> Any: ...
    @abstractmethod
    def decode(self, tokens: Any) -> Any: ...
    @abstractmethod
    def decode_region(self, tokens: Any, start_s: float, end_s: float) -> Any: ...


class SongRenderer(Component):
    @abstractmethod
    def render_fragment(self, scene_fragment: Dict[str, Any], assets: Dict[str, Any],
                        seed: int, tier: str) -> Dict[str, Any]:
        """Scene fragment in; audio and metadata out. Stable interface."""


class VocalRenderer(Component):
    @abstractmethod
    def render_line(self, voice_id: str, lyric_line: Dict[str, Any],
                    performance: Dict[str, Any], seed: int) -> Dict[str, Any]: ...


class InstrumentRenderer(Component):
    @abstractmethod
    def render_part(self, instrument_id: str, part: Dict[str, Any],
                    context: Dict[str, Any], seed: int) -> Dict[str, Any]: ...


class EditingModels(Component):
    @abstractmethod
    def inpaint(self, audio: Any, mask: Dict[str, Any], instruction: Dict[str, Any]) -> Any: ...
    @abstractmethod
    def continue_audio(self, audio: Any, seconds: float, instruction: Dict[str, Any]) -> Any: ...


# ---------------------------------------------------------------- production
class PresetRenderer(Component):
    @abstractmethod
    def apply(self, preset: Dict[str, Any], parts: Dict[str, Any]) -> Dict[str, Any]: ...


class Mixer(Component):
    @abstractmethod
    def mix(self, parts: Dict[str, Any], production_graph: Dict[str, Any], seed: int) -> Dict[str, Any]:
        """Deterministic given the same inputs. Reports loudness and true peak."""


class MasteringStage(Component):
    @abstractmethod
    def master(self, mix: Dict[str, Any], target: str, bypass: bool = False) -> Dict[str, Any]: ...


class Exporter(Component):
    @abstractmethod
    def export(self, project_id: str, scene_version_id: str, formats: List[str], destination: str) -> List[str]: ...


# ---------------------------------------------------------------- foundation
class DataPipeline(Component):
    @abstractmethod
    def ingest(self, source: Dict[str, Any]) -> str: ...
    @abstractmethod
    def record(self, record_id: str) -> Dict[str, Any]: ...
    @abstractmethod
    def delete(self, record_id: str) -> None: ...


class TrainingStack(Component):
    @abstractmethod
    def run_stage(self, stage: int, config: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def gate(self, stage: int) -> Dict[str, Any]: ...


class EvaluationHarness(Component):
    @abstractmethod
    def run_suite(self, suite_id: str, system: Dict[str, Any]) -> Dict[str, Any]: ...
    @abstractmethod
    def check_gates(self, results: Dict[str, Any]) -> Dict[str, Any]: ...


class ProvenanceRegistry(Component):
    @abstractmethod
    def record_consent(self, consent: Dict[str, Any]) -> str: ...
    @abstractmethod
    def verify_consent(self, subject_id: str, use: str) -> bool: ...
    @abstractmethod
    def revoke_consent(self, consent_id: str) -> None: ...
    @abstractmethod
    def sign_provenance(self, metadata: Dict[str, Any]) -> Dict[str, Any]: ...


__all__ = [
    "Component",
    "TimelineEditor", "LyricEditor", "AssetLibrary", "ProfileBrowser",
    "VersionCompare", "CommandLine", "PublicAPI", "DAWBridge",
    "ProjectService", "SceneStore", "VersionGraph", "JobQueue", "RenderOrchestrator",
    "PromptInterpreter", "CompositionPlanner", "ArrangementAssistant",
    "ProfileEngine", "ReferenceAnalyzer",
    "VoiceCharacterStore", "InstrumentStore", "PresetStore",
    "AudioCodec", "SongRenderer", "VocalRenderer", "InstrumentRenderer", "EditingModels",
    "PresetRenderer", "Mixer", "MasteringStage", "Exporter",
    "DataPipeline", "TrainingStack", "EvaluationHarness", "ProvenanceRegistry",
]
