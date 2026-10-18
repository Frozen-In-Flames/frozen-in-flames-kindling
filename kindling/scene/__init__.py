"""The Musical Scene (Build Manual Part 3).

One shared representation connecting intent, symbolic music, performance,
and audio. The scene is the source of truth; rendered audio is derived.
"""

from kindling.scene.model import (
    REALIZATION_LEVELS,
    SECTION_TYPES,
    SOURCES,
    bar_to_seconds,
    beats_per_bar,
    make_element_meta,
    make_scene,
    scene_to_seconds_map,
    validate_scene,
)
from kindling.scene.schema import SCENE_SCHEMA
from kindling.scene.store import SceneStore

__all__ = [
    "REALIZATION_LEVELS",
    "SECTION_TYPES",
    "SOURCES",
    "SCENE_SCHEMA",
    "SceneStore",
    "bar_to_seconds",
    "beats_per_bar",
    "make_element_meta",
    "make_scene",
    "scene_to_seconds_map",
    "validate_scene",
]
