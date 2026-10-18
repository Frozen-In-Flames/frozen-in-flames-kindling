"""Tests for Part 2 (Architecture): the registry covers the manual's component
map exactly, every component states its tiers, and components are replaceable."""

import pytest

from kindling import architecture
from kindling.architecture import (
    DATA_FLOW,
    LAYERS,
    PRINCIPLES,
    TIERS,
    ComponentRegistry,
    ComponentSpec,
    REGISTRY,
    build_component_map,
)

# The component map as written in Build Manual Part 2.2: expected counts.
EXPECTED_COUNTS = {
    "interface": 8,
    "workflow": 5,
    "intelligence": 5,
    "assets": 3,
    "generation": 5,
    "production": 4,
    "foundation": 4,
}


def test_seven_principles():
    assert len(PRINCIPLES) == 7
    ids = [p["id"] for p in PRINCIPLES]
    assert len(set(ids)) == 7
    for p in PRINCIPLES:
        assert p["title"] and p["statement"]


def test_seven_layers_in_order():
    assert LAYERS == [
        "interface", "workflow", "intelligence", "assets",
        "generation", "production", "foundation",
    ]


def test_component_map_matches_manual():
    specs = build_component_map()
    assert len(specs) == sum(EXPECTED_COUNTS.values()) == 34
    names = [s.name for s in specs]
    assert len(set(names)) == len(names), "component names must be unique"
    for layer, count in EXPECTED_COUNTS.items():
        got = [s for s in specs if s.layer == layer]
        assert len(got) == count, f"layer {layer}: expected {count}, got {len(got)}"


def test_every_component_states_tiers():
    for spec in build_component_map():
        assert spec.tiers, f"{spec.name} states no tiers (Part 1.4)"
        for tier in spec.tiers:
            assert tier in TIERS, f"{spec.name} has unknown tier {tier}"


def test_every_interface_resolves_to_abc():
    from kindling.interfaces import Component
    for spec in build_component_map():
        cls = REGISTRY.interface_type(spec.name)
        assert issubclass(cls, Component), f"{spec.name} interface is not a Component"


def test_interfaces_are_abstract():
    for spec in build_component_map():
        cls = REGISTRY.interface_type(spec.name)
        with pytest.raises(TypeError):
            cls()


def test_registry_replace_keeps_contract():
    registry = ComponentRegistry()
    original = registry.get("Mixer")
    replacement = ComponentSpec(
        name="Mixer",
        layer="production",
        interface=original.interface,
        tiers=["draft", "studio", "hosted"],
        description="replacement mixer",
        implementation="my_mixer.MyMixer",
    )
    registry.register(replacement)
    assert registry.get("Mixer").implementation == "my_mixer.MyMixer"


def test_registry_rejects_contract_change():
    registry = ComponentRegistry()
    original = registry.get("Mixer")
    bad = ComponentSpec(
        name="Mixer",
        layer="production",
        interface="other.SomethingElse",
        tiers=["draft"],
    )
    with pytest.raises(ValueError):
        registry.register(bad)
    assert registry.get("Mixer").interface == original.interface


def test_data_flow_is_ordered_and_complete():
    assert len(DATA_FLOW) == 7
    assert [s["stage"] for s in DATA_FLOW] == [1, 2, 3, 4, 5, 6, 7]
    names = [s["name"] for s in DATA_FLOW]
    assert names == ["input", "draft-scene", "refine", "render", "mix", "revise", "version"]
    for s in DATA_FLOW:
        assert s["description"]


def test_tier_coverage_draft_is_usable():
    draft = REGISTRY.by_tier("draft")
    layers_covered = {s.layer for s in draft}
    assert "interface" in layers_covered
    assert "workflow" in layers_covered
    assert "production" in layers_covered
