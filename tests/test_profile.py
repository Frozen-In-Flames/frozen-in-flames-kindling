"""Tests for Part 11: Artist profile."""

import pytest

from kindling.profile import (
    ArtistProfile, PrivacyRecord, ProfileGraph, apply_correction,
    detect_modes, explain_suggestion, rollback, select_scope,
)


def _track_a():
    return {
        "musical_identity": {
            "tempo": (120.0, {"section": "verse"}),
            "key": ("C", {"section": "verse"}),
        },
        "sound_arrangement": {
            "density": (0.3, {"section": "verse"}),
            "has_808": (True, {"section": "chorus"}),
        },
        "production": {
            "brightness": (0.7, {"section": "chorus"}),
        },
    }


def _track_b():
    return {
        "musical_identity": {
            "tempo": (140.0, {"section": "verse"}),
            "key": ("G", {"section": "verse"}),
        },
        "sound_arrangement": {
            "density": (0.9, {"section": "verse"}),
            "has_808": (True, {"section": "chorus"}),
        },
        "production": {
            "brightness": (0.9, {"section": "chorus"}),
        },
    }


def _profile():
    p = ArtistProfile("artist1")
    p.add_track("track_a", _track_a())
    p.add_track("track_b", _track_b())
    return p


def test_dimensions_stay_separate():
    p = _profile()
    assert set(p.dimensions.keys()) == {
        "musical_identity", "sound_arrangement", "performance",
        "production", "variation"}
    # Tendencies, not recipes.
    t = p.dimensions["musical_identity"].tendency("tempo")
    assert t["min"] == 120.0 and t["max"] == 140.0


def test_graph_answers_shared_and_outlier():
    g = ProfileGraph()
    g.add_track("a", ["verse", "chorus"])
    g.add_track("b", ["verse", "chorus"])
    g.add_trait("808", "sound_arrangement", "a#chorus", {"role": "bass"})
    g.add_trait("808", "sound_arrangement", "b#chorus", {"role": "bass"})
    g.add_trait("choir", "sound_arrangement", "a#verse", {"role": "pad"})
    shared = g.shared_traits("a", "b")
    assert len(shared) == 1 and shared[0]["trait"] == "808"
    assert shared[0]["evidence_a"]
    outliers = g.outlier_traits("a", ["b"])
    assert [o["trait"] for o in outliers] == ["choir"]


def test_chorus_not_verse():
    g = ProfileGraph()
    g.add_track("a", ["verse", "chorus"])
    g.add_trait("lift", "sound_arrangement", "a#chorus", {})
    g.add_trait("groove", "sound_arrangement", "a#verse", {})
    assert g.chorus_not_verse_traits() == ["lift"]


def test_modes_not_blended():
    p = _profile()
    modes = detect_modes(p, trait="density")
    assert "mode_sparse" in modes and "mode_dense" in modes
    assert modes["mode_sparse"] == ["track_a"]
    assert modes["mode_dense"] == ["track_b"]


def test_explanation_cites_evidence():
    p = _profile()
    text = explain_suggestion(p, "Use a sparse verse texture",
                              ["density"], ["track_a"])
    assert "track_a" in text
    assert "Rationale" in text


def test_correction_is_versioned_and_scoped():
    p = _profile()
    v0 = p.version
    apply_correction(p, {"action": "track_specific",
                         "dimension": "sound_arrangement",
                         "trait": "has_808", "track_id": "track_a"})
    assert p.version > v0
    dim = p.dimensions["sound_arrangement"]
    assert dim.is_track_specific("has_808", "track_a")
    assert not dim.is_track_specific("has_808", "track_b")
    # Other traits untouched.
    assert "density" in dim.traits


def test_scope_selection_explicit():
    p = _profile()
    s = select_scope(p, "chosen_references", refs=["track_a"])
    assert s["scope"] == "chosen_references"
    assert s["tracks"] == ["track_a"]
    assert s["default_shown"] is True
    with pytest.raises(ValueError):
        select_scope(p, "bogus")


def test_delete_removes_derived_traits():
    p = _profile()
    assert "tempo" in p.dimensions["musical_identity"].traits
    p.remove_track("track_a")
    p.remove_track("track_b")
    assert "tempo" not in p.dimensions["musical_identity"].traits
    assert p.tracks == {}


def test_profile_on_vs_off_differs():
    # Acceptance: output with profile context differs measurably.
    p = _profile()
    with_profile = p.dimensions["sound_arrangement"].tendency("density")
    empty = ArtistProfile("nobody")
    assert with_profile["mean"] != 0.0
    assert "density" not in empty.dimensions["sound_arrangement"].traits


def test_privacy_defaults():
    priv = PrivacyRecord("artist1")
    assert priv.shared_training_opt_in is False
    assert priv.encrypted is True
    p = _profile()
    exported = priv.export(p)
    assert exported["profile"]["artist_id"] == "artist1"
    priv.grant_training_opt_in()
    assert priv.shared_training_opt_in is True
    priv.revoke_training_opt_in()
    assert priv.shared_training_opt_in is False
