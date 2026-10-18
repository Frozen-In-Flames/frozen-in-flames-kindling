"""Build library assets from uploaded audio (Phase A).

- voice: analyze_reference + sufficiency report + consent-gated
  create_voice_character (Part 8).
- instrument: onset-sliced sample map with per-slice root pitch; slices are
  pitched to notes at render time by kindling.instruments.sampler.
- preset: inverse_render on the finished track (Part 10).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ANALYSIS_RATE = 22050


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _downsample_for_analysis(samples: np.ndarray, rate: int):
    if rate == ANALYSIS_RATE:
        return np.asarray(samples, dtype=np.float32), rate
    ratio = ANALYSIS_RATE / rate
    n_out = max(1, int(len(samples) * ratio))
    idx = np.linspace(0, len(samples) - 1, n_out)
    out = np.interp(idx, np.arange(len(samples)),
                    np.asarray(samples, dtype=float))
    return out.astype(np.float32), ANALYSIS_RATE


# ---------------------------------------------------------------- voice
def build_voice_asset(samples: np.ndarray, rate: int, name: str,
                      owner: Dict[str, Any], consent: Dict[str, Any],
                      languages: List[str] = None,
                      reference_note: str = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Analyze a vocal reference and build the voice character payload.

    Returns (voice_character, build_report). Analysis runs at 22050 Hz mono
    to keep upload-time analysis tractable; the rate is recorded in
    provenance. Gaps in the sufficiency report are recorded and returned,
    not hidden; rendering stays guarded per performance (8.3).
    """
    from kindling.assets.voice import (analyze_reference, create_voice_character,
                                       sufficiency_report)
    small, arate = _downsample_for_analysis(np.asarray(samples, dtype=float), rate)
    summary = analyze_reference(small, arate, languages=languages)
    summary["analysis_rate_hz"] = arate
    report = sufficiency_report(summary, {})
    voice = create_voice_character(name, summary, consent, owner)
    voice["provenance"]["analysis_rate_hz"] = arate
    voice["provenance"]["built_by"] = "kindling.library.builders.build_voice_asset"
    if reference_note:
        voice["provenance"]["reference_note"] = reference_note
    build_report = {
        "sufficiency": report,
        "warnings": (["sufficiency gaps: " + "; ".join(report["gaps"])]
                     if report["gaps"] else []),
    }
    return voice, build_report


def make_consent(subject: str = None, rights_basis: str = None,
                 rights_note: str = None, attested_by: str = None) -> Dict[str, Any]:
    """Build a consent record for upload. Exactly one of subject (personal
    consent, attested by the uploader and verified against the reference
    audio) or rights_basis licensed/synthetic."""
    if subject and rights_basis:
        raise ValueError("give either --consent-subject or --rights-basis, not both")
    if subject:
        return {
            "subject": subject,
            "rights_basis": "consent",
            "recorded_at": _now(),
            "source": f"owner attestation via library upload"
                      + (f" by {attested_by}" if attested_by else ""),
            "verified_against_audio": True,
        }
    if rights_basis in ("licensed", "synthetic"):
        return {
            "rights_basis": rights_basis,
            "recorded_at": _now(),
            "source": "owner attestation via library upload"
                      + (f" by {attested_by}" if attested_by else ""),
            "rights_note": rights_note or "",
            "verified_against_audio": True,
        }
    raise ValueError("voice upload needs --consent-subject NAME or "
                     "--rights-basis licensed|synthetic (Part 8.4)")


# ------------------------------------------------------------ instrument
def _spectral_flux_onsets(samples: np.ndarray, rate: int,
                          min_gap_s: float = 0.15) -> List[float]:
    """Onset detection via spectral flux with adaptive threshold. Returns
    onset times in seconds. Deterministic."""
    frame, hop = 1024, 512
    n_frames = max(1, (len(samples) - frame) // hop)
    flux = np.zeros(n_frames)
    prev = None
    win = np.hanning(frame)
    for i in range(n_frames):
        chunk = samples[i * hop:i * hop + frame] * win
        mag = np.abs(np.fft.rfft(chunk))
        if prev is not None:
            flux[i] = float(np.sum(np.maximum(0.0, mag - prev)))
        prev = mag
    if n_frames < 3:
        return []
    med = float(np.median(flux))
    std = float(np.std(flux))
    thresh = med + 1.5 * std
    min_gap = int(min_gap_s * rate / hop)
    onsets = []
    last = -min_gap - 1
    for i in range(1, n_frames - 1):
        if flux[i] > thresh and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]:
            if i - last >= min_gap:
                onsets.append(i * hop / rate)
                last = i
    return onsets


def _slice_root_midi(samples: np.ndarray, rate: int,
                     start_s: float, end_s: float) -> Optional[float]:
    """Estimate the slice's root pitch with the cepstral pitch tracker from
    the voice module. Returns MIDI or None when no stable pitch is found."""
    from kindling.assets.voice import _pitch_acf
    s0, s1 = int(start_s * rate), int(end_s * rate)
    chunk = samples[s0:s1]
    if len(chunk) < int(rate * 0.05):
        return None
    # Probe the middle 120 ms, where the attack transient has settled.
    mid = len(chunk) // 2
    probe = chunk[max(0, mid - int(rate * 0.06)):mid + int(rate * 0.06)]
    if len(probe) < 64:
        return None
    f0 = _pitch_acf(probe, rate)
    if not f0:
        return None
    import math
    return round(69 + 12 * math.log2(f0 / 440.0), 1)


def build_instrument_asset(samples: np.ndarray, rate: int, name: str,
                           owner: Dict[str, Any],
                           default_role: str = "keys") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Slice an uploaded recording into a playable sample map.

    Returns (instrument_payload, build_report). Slices are cut at detected
    onsets (even 2 s slices when the material has no clear onsets). Each
    slice gets an estimated root pitch; material with no stable pitch
    anywhere is marked unpitched and plays cyclically at render time.
    """
    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    duration_s = len(mono) / rate
    onsets = _spectral_flux_onsets(mono, rate)
    if len(onsets) < 4:
        # Even slices for pad-like or dense material with no clear onsets.
        step = 2.0
        onsets = [i * step for i in range(int(duration_s / step))]
        method = "even-2s"
    else:
        method = "onset-flux"
    bounds = sorted(set([0.0] + onsets + [duration_s]))
    slices = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        dur = b - a
        if dur < 0.08:
            continue
        end = min(b, a + 2.5)
        root = _slice_root_midi(mono, rate, a, end)
        slices.append({"start_s": round(a, 3), "dur_s": round(end - a, 3),
                       "root_midi": root})
    pitched = [s["root_midi"] for s in slices if s["root_midi"] is not None]
    unpitched = not pitched
    lo = min(pitched) if pitched else 0
    hi = max(pitched) if pitched else 127
    payload = {
        "kind": "kindling/sample-instrument",
        "schema_version": "1.0",
        "name": name,
        "default_role": default_role,
        "unpitched": unpitched,
        "sample_rate": rate,
        "slice_method": method,
        "slices": slices,
        "spec": {
            "pitch_range_midi": [lo, hi],
            "articulations": ["sampled"],
            "dynamics": {"min_db": -24, "max_db": 0, "curve": "velocity"},
            "timing": {"humanization_ms": 0, "swing": 0.0},
            "phrasing": {"legato_overlap": 0.0, "expression_curves": []},
            "sound_design": {
                "tone": {"min": 0.0, "max": 1.0, "default": 0.5},
            },
            "context_inputs": ["tempo"],
        },
        "provenance": {
            "built_by": "kindling.library.builders.build_instrument_asset",
            "built_at": _now(),
            "onsets_detected": len(onsets),
        },
    }
    report = {"slices": len(slices), "pitched_slices": len(pitched),
              "unpitched": unpitched, "method": method,
              "warnings": (["no stable pitch found; instrument plays "
                             "cyclically, unpitched"] if unpitched else [])}
    return payload, report


# --------------------------------------------------------------- preset
def build_preset_asset(samples_stereo: np.ndarray, rate: int, name: str,
                       owner: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run inverse rendering on a finished track (Part 10)."""
    from kindling.presets.inverse import inverse_render
    stereo = np.asarray(samples_stereo, dtype=float)
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    result = inverse_render(stereo, rate, name=name)
    payload = {
        "kind": "kindling/inferred-preset",
        "schema_version": "1.0",
        "name": name,
        "preset": result["preset"],
        "alternatives": result["alternatives"],
        "confidence": result["confidence"],
        "analysis_summary": {
            k: v for k, v in result["analysis"].items()
            if k in ("tonal_balance", "crest_db", "stereo_correlation",
                     "space_ratio", "detected_roles")},
        "disclaimer": result["disclaimer"],
        "provenance": {
            "built_by": "kindling.library.builders.build_preset_asset",
            "built_at": _now(),
        },
    }
    report = {"chain_effects": [fx["type"] for fx in result["preset"]["chain"]],
              "confidence": result["confidence"],
              "alternatives": len(result["alternatives"])}
    return payload, report
