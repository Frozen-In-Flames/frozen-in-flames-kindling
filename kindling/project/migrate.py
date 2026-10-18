"""Schema migration (15.4): semantic versioning, automated migration,
lossy steps reported. Old projects MUST open in new releases.
"""

import copy
from typing import Any, Dict, List, Tuple

CURRENT_SCHEMA = "3.0.0"


def _migrate_1_to_2(scene: Dict[str, Any]) -> Tuple[Dict, List[str]]:
    """v1 -> v2: parts gained 'meta'; lyrics gained timing."""
    new = copy.deepcopy(scene)
    lossy = []
    for part in new.get("parts", []):
        if "meta" not in part:
            part["meta"] = {"source": "user", "confidence": 1.0,
                            "locked": False, "realization": "intent"}
            lossy.append(f"part {part.get('id')}: default meta inserted")
    for i, line in enumerate(new.get("lyrics", {}).get("lines", [])):
        if "start_s" not in line:
            line["start_s"] = float(i * 2.0)
            lossy.append(f"lyric line {i}: start_s estimated")
    new["schema_version"] = "2.0.0"
    return new, lossy


def _migrate_2_to_3(scene: Dict[str, Any]) -> Tuple[Dict, List[str]]:
    """v2 -> v3: automation list introduced; production.routing added."""
    new = copy.deepcopy(scene)
    lossy = []
    if "automation" not in new:
        new["automation"] = []
        lossy.append("automation: empty list initialized")
    prod = new.setdefault("production", {})
    if "routing" not in prod:
        prod["routing"] = {}
        lossy.append("production.routing: empty initialized")
    new["schema_version"] = "3.0.0"
    return new, lossy


MIGRATIONS = {
    ("1.0.0", "2.0.0"): _migrate_1_to_2,
    ("2.0.0", "3.0.0"): _migrate_2_to_3,
}


def migrate_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate to CURRENT_SCHEMA. Returns {"scene", "migrations", "lossy"}.

    Every lossy step is reported; zero unreported loss (acceptance).
    """
    current = scene.get("schema_version", "1.0.0")
    new = copy.deepcopy(scene)
    applied: List[str] = []
    lossy: List[str] = []
    # Simple linear chain 1.0.0 -> 2.0.0 -> 3.0.0.
    order = ["1.0.0", "2.0.0", "3.0.0"]
    try:
        idx = order.index(current)
    except ValueError:
        idx = 0
    for i in range(idx, len(order) - 1):
        fn = MIGRATIONS[(order[i], order[i + 1])]
        new, step_lossy = fn(new)
        applied.append(f"{order[i]} -> {order[i+1]}")
        lossy.extend(step_lossy)
    return {"scene": new, "migrations": applied, "lossy": lossy,
            "schema_version": new.get("schema_version", CURRENT_SCHEMA)}
