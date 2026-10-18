"""Song planning and rendering (Build Manual Part 6).

Prompt interpreter, composition planner, renderer behind a stable interface,
hierarchical generation with overlapping chunks, long-form coherence checks,
preview tiers, and the structured bake-off harness. The reference
implementations here are deterministic and theory-driven; learned models plug
into the same interfaces and are judged by the bake-off against the Part 1
targets, not demos.
"""

from kindling.planning.interpreter import ReferenceInterpreter, interpret
from kindling.planning.planner import ReferencePlanner
from kindling.planning.renderer import ReferenceRenderer
from kindling.planning.hierarchical import HierarchicalRenderer
from kindling.planning.bakeoff import bake_off
from kindling.planning.coherence import coherence_report

from kindling.planning.bakeoff import bake_off, baseline_bake_off

__all__ = [
    "ReferenceInterpreter",
    "interpret",
    "ReferencePlanner",
    "ReferenceRenderer",
    "HierarchicalRenderer",
    "bake_off",
    "baseline_bake_off",
    "coherence_report",
]
