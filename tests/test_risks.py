"""Tests for Part 21: risk monitors."""

from kindling.eval.risk_monitors import (
    monitor_coherence_risk, monitor_data_risk, monitor_demo_bias,
    monitor_edit_risk, monitor_preset_risk, monitor_profile_risk,
    monitor_reproducibility_risk, monitor_vocal_risk,
)


def test_vocal_risk_trips_on_high_wer():
    assert monitor_vocal_risk(0.4, [0.9, 0.85])["tripped"] is True
    assert monitor_vocal_risk(0.1, [0.9, 0.92])["tripped"] is False


def test_edit_risk():
    assert monitor_edit_risk(5.0)["tripped"] is True
    assert monitor_edit_risk(1.0)["tripped"] is False


def test_coherence_risk():
    tripped = monitor_coherence_risk({"short": 4.5, "long": 3.0})
    assert tripped["tripped"] is True
    ok = monitor_coherence_risk({"short": 4.5, "long": 4.3})
    assert ok["tripped"] is False


def test_data_profile_preset_risks():
    assert monitor_data_risk(3)["tripped"] is True
    assert monitor_data_risk(0)["tripped"] is False
    assert monitor_profile_risk(0.1)["tripped"] is True
    assert monitor_profile_risk(0.8)["tripped"] is False
    assert monitor_preset_risk(0.5)["tripped"] is True
    assert monitor_preset_risk(0.95)["tripped"] is False


def test_reproducibility_and_demo_bias():
    assert monitor_reproducibility_risk(2, 10)["tripped"] is True
    assert monitor_reproducibility_risk(0, 10)["tripped"] is False
    assert monitor_demo_bias(0.6, 0.95)["tripped"] is True
    assert monitor_demo_bias(0.85, 0.9)["tripped"] is False
