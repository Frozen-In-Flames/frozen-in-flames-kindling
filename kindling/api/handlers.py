"""API handlers (14.2): scene, render/edit jobs, assets, profile, exports.

Versioned (v1). Behavior stays stable within the major version. These
are the functions the HTTP server and the CLI both call, so a scripted
CLI render matches the interface render (acceptance).
"""

import time
import uuid
from typing import Any, Dict, List

API_VERSION = "v1"

# In-memory job store (reference; production would persist).
_jobs: Dict[str, Dict[str, Any]] = {}
_scenes: Dict[str, Dict[str, Any]] = {}


def _job(job_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    jid = f"job-{uuid.uuid4().hex[:8]}"
    job = {"id": jid, "type": job_type, "status": "queued",
           "params": params, "result": None, "error": None,
           "created_at": time.time()}
    _jobs[jid] = job
    return job


# Scene read/write.
def scene_create(scene: Dict[str, Any]) -> Dict[str, Any]:
    sid = f"scene-{uuid.uuid4().hex[:8]}"
    _scenes[sid] = scene
    return {"scene_id": sid}


def scene_read(scene_id: str) -> Dict[str, Any]:
    if scene_id not in _scenes:
        raise KeyError(f"unknown scene {scene_id}")
    return _scenes[scene_id]


def scene_update(scene_id: str, scene: Dict[str, Any]) -> Dict[str, Any]:
    if scene_id not in _scenes:
        raise KeyError(f"unknown scene {scene_id}")
    _scenes[scene_id] = scene
    return {"scene_id": scene_id, "updated": True}


# Render and edit jobs.
def render_submit(scene_id: str, tier: str = "draft",
                  seed: int = 0) -> Dict[str, Any]:
    scene = scene_read(scene_id)
    job = _job("render", {"scene_id": scene_id, "tier": tier, "seed": seed})
    # Reference: run synchronously via the deterministic renderer.
    from kindling.planning.renderer import ReferenceRenderer
    renderer = ReferenceRenderer()
    try:
        result = renderer.render_fragment(scene, {}, seed, tier)
        job["status"] = "done"
        job["result"] = {"metadata": result["metadata"],
                         "audio_shape": list(
                             result["audio"]["samples"].shape)}
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)
    return {"job_id": job["id"], "status": job["status"]}


def edit_submit(scene_id: str, operation: str, selection: Dict[str, Any],
                instruction: str, seed: int = 0) -> Dict[str, Any]:
    from kindling.editing import EditRequest, Selection
    from kindling.editing.operations import OPERATIONS
    from kindling.scene.store import SceneStore
    scene = scene_read(scene_id)
    if operation not in OPERATIONS:
        raise ValueError(f"unknown operation {operation!r}")
    sel = Selection(start_s=selection.get("start_s"),
                    end_s=selection.get("end_s"),
                    part_id=selection.get("part_id"),
                    element=selection.get("element"))
    req = EditRequest(operation=operation, scene_version_id=scene_id,
                      selection=sel, instruction=instruction, seed=seed)
    job = _job("edit", {"scene_id": scene_id, "operation": operation})
    try:
        new_scene, changed = OPERATIONS[operation](scene, req)
        store = SceneStore()
        new_id = store.save_version(new_scene)
        _scenes[new_id] = new_scene
        job["status"] = "done"
        job["result"] = {"new_scene_id": new_id, "changed": changed}
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)
    return {"job_id": job["id"], "status": job["status"],
            "result": job["result"]}


def job_status(job_id: str) -> Dict[str, Any]:
    if job_id not in _jobs:
        raise KeyError(f"unknown job {job_id}")
    j = _jobs[job_id]
    return {"job_id": j["id"], "type": j["type"], "status": j["status"],
            "result": j["result"], "error": j["error"]}


def job_cancel(job_id: str) -> Dict[str, Any]:
    j = _jobs.get(job_id)
    if not j:
        raise KeyError(f"unknown job {job_id}")
    if j["status"] == "queued":
        j["status"] = "cancelled"
    return {"job_id": job_id, "status": j["status"]}


# Asset operations (voices, instruments, presets).
_assets: Dict[str, Dict[str, Any]] = {}


def asset_register(kind: str, asset: Dict[str, Any]) -> Dict[str, Any]:
    aid = f"{kind}-{uuid.uuid4().hex[:8]}"
    _assets[aid] = {"kind": kind, "asset": asset}
    return {"asset_id": aid}


def asset_list(kind: str = None) -> List[Dict[str, Any]]:
    return [{"asset_id": aid, "kind": a["kind"]}
            for aid, a in _assets.items()
            if kind is None or a["kind"] == kind]


def asset_get(asset_id: str) -> Dict[str, Any]:
    if asset_id not in _assets:
        raise KeyError(f"unknown asset {asset_id}")
    return _assets[asset_id]


# Profile operations.
_profiles: Dict[str, Any] = {}


def profile_get(artist_id: str) -> Dict[str, Any]:
    if artist_id not in _profiles:
        raise KeyError(f"unknown profile {artist_id}")
    return _profiles[artist_id].to_dict()


def profile_register(artist_id: str, profile) -> Dict[str, Any]:
    _profiles[artist_id] = profile
    return {"artist_id": artist_id}


# Export.
def export_submit(scene_id: str, out_dir: str,
                  mix: Any = None, stems: Any = None) -> Dict[str, Any]:
    from kindling.mix import export_all
    scene = scene_read(scene_id)
    job = _job("export", {"scene_id": scene_id})
    try:
        # Reference: export metadata bundle (audio optional).
        manifest = {"scene_id": scene_id, "out_dir": out_dir,
                    "note": "audio export requires rendered mix/stems"}
        if mix is not None and stems is not None:
            from kindling.scene.model import make_scene  # noqa
            manifest = export_all(mix, stems, scene, out_dir)
        job["status"] = "done"
        job["result"] = manifest
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)
    return {"job_id": job["id"], "status": job["status"]}
