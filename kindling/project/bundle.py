"""Project bundle (15.1): scenes, version graph, pinned assets, seeds,
render settings, cached audio, profile snapshots.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ProjectBundle:
    """A reproducible project: everything needed to re-render later."""

    def __init__(self, name: str):
        self.name = name
        self.scenes: Dict[str, Dict[str, Any]] = {}
        self.version_graph: Dict[str, List[str]] = {}  # child -> parents
        self.pinned_assets: Dict[str, str] = {}  # asset_id -> version/hash
        self.seeds: Dict[str, int] = {}
        self.render_settings: Dict[str, Any] = {}
        self.cached_audio: Dict[str, str] = {}  # scene_version -> path
        self.profile_snapshots: Dict[str, Dict[str, Any]] = {}

    def add_scene(self, version_id: str, scene: Dict[str, Any],
                  parents: List[str] = None):
        self.scenes[version_id] = scene
        self.version_graph[version_id] = parents or []

    def pin_asset(self, asset_id: str, version: str):
        self.pinned_assets[asset_id] = version

    def set_seed(self, scope: str, seed: int):
        self.seeds[scope] = seed

    def cache_audio(self, scene_version: str, path: str):
        """Link cached audio to its EXACT scene version (15.1)."""
        self.cached_audio[scene_version] = path

    def snapshot_profile(self, artist_id: str, profile: Dict[str, Any]):
        self.profile_snapshots[artist_id] = profile

    def save(self, path: str):
        os.makedirs(path, exist_ok=True)
        bundle = {
            "name": self.name,
            "scenes": self.scenes,
            "version_graph": self.version_graph,
            "pinned_assets": self.pinned_assets,
            "seeds": self.seeds,
            "render_settings": self.render_settings,
            "cached_audio": self.cached_audio,
            "profile_snapshots": self.profile_snapshots,
        }
        with open(os.path.join(path, "project.json"), "w") as f:
            json.dump(bundle, f, indent=1, default=str)
        # Integrity manifest.
        manifest_path = os.path.join(path, "project.json")
        with open(os.path.join(path, "SHA256SUM"), "w") as f:
            f.write(f"{_sha256_file(manifest_path)}  project.json\n")

    @classmethod
    def load(cls, path: str) -> "ProjectBundle":
        with open(os.path.join(path, "project.json")) as f:
            data = json.load(f)
        bundle = cls(data["name"])
        bundle.scenes = data["scenes"]
        bundle.version_graph = data["version_graph"]
        bundle.pinned_assets = data["pinned_assets"]
        bundle.seeds = data["seeds"]
        bundle.render_settings = data["render_settings"]
        bundle.cached_audio = data["cached_audio"]
        bundle.profile_snapshots = data["profile_snapshots"]
        return bundle

    def verify_integrity(self, path: str) -> bool:
        """Check the bundle against its SHA256 manifest."""
        manifest = os.path.join(path, "project.json")
        sums = os.path.join(path, "SHA256SUM")
        if not os.path.exists(sums):
            return False
        with open(sums) as f:
            expected = f.read().split()[0]
        return _sha256_file(manifest) == expected
