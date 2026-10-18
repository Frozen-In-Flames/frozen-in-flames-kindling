"""Tests for Part 19: Consent, provenance, privacy, safety."""

import numpy as np
import pytest

from kindling.safety import (
    ConsentVerificationError, DataGovernance, MisuseMonitor,
    RevocationRegistry, UserDataManager, detect_watermark, embed_watermark,
    legal_policy, openness_statement, sign_provenance, survival_report,
    verify_consent, verify_provenance,
)


def _consent():
    return {"subject": "Mara", "rights_basis": "consent",
            "verified": True, "recorded_at": "2026-10-18"}


def test_consent_required():
    with pytest.raises(ConsentVerificationError):
        verify_consent("Mara", None)
    out = verify_consent("Mara", _consent())
    assert out["verified"] is True


def test_named_real_person_blocked():
    with pytest.raises(ConsentVerificationError):
        verify_consent("Famous Singer",
                       {"subject": "Famous Singer",
                        "rights_basis": "licensed",
                        "verified": True},
                       is_named_real_person=True)


def test_revocation_blocks_renders():
    reg = RevocationRegistry()
    reg.revoke("voice-1", "owner1")
    assert reg.is_revoked("voice-1")
    with pytest.raises(ConsentVerificationError):
        reg.check_renderable("voice-1")
    reg.check_renderable("voice-2")  # not revoked, fine


def test_watermark_round_trip():
    rate = 22050
    n = rate * 2
    t = np.arange(n) / rate
    # Signal with energy in the 2-4 kHz band.
    audio = (np.sin(2 * np.pi * 3000 * t) * 0.3 +
             np.sin(2 * np.pi * 440 * t) * 0.3)
    stereo = np.stack([audio, audio])
    payload = 0xDEADBEEF12345678
    marked = embed_watermark(stereo, rate, payload, strength=0.05)
    result = detect_watermark(marked, rate)
    assert result["detected"], result
    assert result["payload"] == payload, \
        f"{result['payload']:x} != {payload:x}"


def test_watermark_survives_resample():
    rate = 48000
    n = rate * 2
    t = np.arange(n) / rate
    audio = np.sin(2 * np.pi * 3000 * t) * 0.4
    marked = embed_watermark(audio, rate, 12345, strength=0.05)
    # Downsample to 44.1k and back (crude).
    from kindling.mix.export import _resample
    down = _resample(marked, rate, 44100)
    back = _resample(down, 44100, rate)
    result = detect_watermark(back, rate)
    assert result["detected"], result


def test_provenance_signature():
    meta = {"system": "kindling", "version": "19.0.0", "project": "song1"}
    signed = sign_provenance(meta)
    assert verify_provenance(signed) is True
    signed["metadata"]["project"] = "tampered"
    assert verify_provenance(signed) is False


def test_survival_report_honest():
    report = survival_report()
    assert report["survives"] and report["does_not_survive"]


def test_governance_opt_in():
    gov = DataGovernance()
    assert gov.may_train_on("upload1", "user1") is False  # default no
    gov.grant_training_opt_in("user1")
    assert gov.may_train_on("upload1", "user1") is True
    gov.opt_out("upload1")
    assert gov.may_train_on("upload1", "user1") is False
    gov.request_deletion("upload1", "user1")
    done = gov.process_deletions()
    assert done[0]["status"] == "deleted"


def test_deletion_cascades():
    mgr = UserDataManager()
    mgr.put("user1", "upload", "u1", b"audio")
    mgr.put("user1", "trait", "t1", {"v": 1})
    out = mgr.delete_owner("user1")
    assert out["cascaded"] is True
    assert len(out["deleted"]) == 2
    assert mgr.export("user1")["data"] == {}


def test_misuse_detection():
    mon = MisuseMonitor()
    for _ in range(3):
        mon.record_consent_failure("bad-actor")
    result = mon.check_abuse("bad-actor")
    assert "repeated_consent_failures" in result["flags"]
    assert result["limited"] is True


def test_openness_statement():
    stmt = openness_statement()
    assert stmt["code"]["open"] is True
    assert stmt["trained_weights"]["open"] is False
    assert legal_policy()["version"] == "1.0.0"
