"""Dependency-aware re-rendering (12.4).

Keep a dependency graph from scene elements to rendered audio. After an
edit, re-render only nodes whose inputs changed, then re-run the mix.
preview() shows what will be re-rendered before an expensive operation.
"""

from typing import Any, Dict, List, Set


class DependencyGraph:
    """scene element -> audio nodes. Nodes: part renders, vocal renders,
    section mixes, master."""

    def __init__(self):
        self.deps: Dict[str, Set[str]] = {}  # element -> nodes
        self.node_inputs: Dict[str, Set[str]] = {}  # node -> elements

    def register(self, element: str, node: str):
        self.deps.setdefault(element, set()).add(node)
        self.node_inputs.setdefault(node, set()).add(element)

    def build_from_scene(self, scene: Dict[str, Any]):
        """Build the graph from a scene: parts -> part nodes, vocals ->
        vocal nodes, sections -> section mixes."""
        self.deps.clear()
        self.node_inputs.clear()
        for part in scene.get("parts", []):
            pid = part.get("id", "part")
            node = f"render:{pid}"
            self.register(f"part:{pid}", node)
            self.register("timeline", node)
        for i, vocal in enumerate(scene.get("vocals", [])):
            vid = vocal.get("id", f"vocal{i}")
            node = f"render:{vid}"
            self.register(f"vocal:{vid}", node)
            self.register("timeline", node)
        for sec in scene.get("sections", []):
            sid = sec.get("id", sec.get("name", "section"))
            node = f"mix:{sid}"
            self.register(f"section:{sid}", node)
            # Section mix depends on all part/vocal renders.
            for n in list(self.node_inputs.keys()):
                if n.startswith("render:"):
                    self.node_inputs[node] = \
                        self.node_inputs.get(node, set()) | {n}
        self.register("master", "mix:master")

    def affected_nodes(self, changed_elements: List[str]) -> List[str]:
        """Nodes whose inputs changed (transitive)."""
        affected: Set[str] = set()
        queue = list(changed_elements)
        # Direct: elements -> nodes.
        for el in changed_elements:
            affected |= self.deps.get(el, set())
        # Transitive: nodes that consume affected nodes.
        changed = True
        while changed:
            changed = False
            for node, inputs in self.node_inputs.items():
                if node not in affected and inputs & affected:
                    # inputs contains element names AND node names;
                    # check node-name inputs.
                    node_inputs = {i for i in inputs
                                   if i in self.node_inputs}
                    if node_inputs & affected:
                        affected.add(node)
                        changed = True
        return sorted(affected)

    def preview(self, changed_elements: List[str]) -> Dict[str, Any]:
        """Show what will be re-rendered before an expensive op (12.4)."""
        nodes = self.affected_nodes(changed_elements)
        return {"changed_elements": changed_elements,
                "nodes_to_rerender": nodes,
                "count": len(nodes)}
