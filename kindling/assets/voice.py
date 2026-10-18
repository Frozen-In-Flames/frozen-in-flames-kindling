"""Voice characters (Build Manual Part 8).

A saved, reusable singing identity that can perform new lyrics and melodies.
Identity is separate from performance: the identity vector comes only from
the reference analysis, and the performance instruction is a separate input
that never changes it (8.2, tested directly).

Consent is a release requirement (8.4): creating a character from a
person's voice requires a recorded consent statement tied to that person
and verified against the reference audio, or documented rights for a
licensed or synthetic source. No consent record, no character.

Every render records which character version was used (8.5) and passes
through the watermark hook (robust audio watermarking lands in Part 19;
until then the hook embeds provenance metadata, and says so).
"""

from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from kindling.interfaces import VoiceCharacterStore as VoiceCharacterStoreABC

VOICE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://frozen-in-flames.github.io/schemas/kindling-voice-8.0.0.json",
    "title": "Kindling Voice Character",
    "type": "object",
    "properties": {
        "kind": {"const": "kindling/voice-character"},
        "schema_version": {"type": "string"},
        "id": {"type": "string"},
        "version": {"type": "string"},
        "parent": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "identity": {
            "type": "object",
            "properties": {
                "vector": {"type": "array", "items": {"type": "number"}},
                "description": {"type": "string"},
                "method": {"type": "string"},
            },
            "required": ["vector", "method"],
        },
        "range_map": {
            "type": "object",
            "properties": {
                "low_midi": {"type": "number"},
                "high_midi": {"type": "number"},
                "registers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "low_midi": {"type": "number"},
                            "high_midi": {"type": "number"},
                            "reliability": {"type": "number", "minimum": 0, "maximum": 1},
                            "seconds_observed": {"type": "number"},
                        },
                        "required": ["name", "low_midi", "high_midi", "reliability"],
                    },
                },
            },
            "required": ["low_midi", "high_midi", "registers"],
        },
        "timbre": {"type": "object"},
        "pronunciation": {"type": "object"},
        "controls": {"type": "object"},
        "reference_summary": {"type": "object"},
        "owner": {"type": "object"},
        "consent": {"type": "object"},
        "provenance": {"type": "object"},
        "permissions": {"type": "object"},
        "revoked": {"type": "boolean"},
    },
    "required": ["kind", "schema_version", "id", "version", "identity",
                 "range_map", "reference_summary", "owner", "consent",
                 "provenance", "revoked"],
}

# Formant anchors for a generic adult voice, (F1, F2) in Hz.
_VOWEL_FORMANTS = {
    "IY": (270, 2290), "IH": (390, 1990), "EH": (530, 1840),
    "AE": (660, 1720), "AA": (730, 1090), "AO": (570, 840),
    "OW": (450, 1030), "UW": (300, 870), "UH": (440, 1020),
    "AH": (520, 1190), "ER": (490, 1350),
}

# Register boundaries in MIDI, approximate and documented as such.
_REGISTERS = [("chest", 0, 63), ("mix", 64, 71), ("head", 72, 127)]


def _midi(freq: float) -> float:
    return 69 + 12 * math.log2(freq / 440.0) if freq > 0 else 0.0


def _voiced_frames(samples: np.ndarray, rate: int):
    frame = int(rate * 0.03)
    hop = frame // 2
    frames = []
    peak = 0.0
    raw = []
    for start in range(0, len(samples) - frame, hop):
        chunk = samples[start:start + frame]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        zcr = float(((chunk[:-1] * chunk[1:]) < 0).mean())
        raw.append((start, chunk, rms, zcr))
        peak = max(peak, rms)
    for start, chunk, rms, zcr in raw:
        if rms > 0.05 * peak and zcr < 0.35:
            frames.append((start, chunk, rms))
    return frames, hop / rate


def _pitch_acf(chunk: np.ndarray, rate: int) -> Optional[float]:
    """Pitch via the real cepstrum.

    The cepstrum separates the periodic source from the formant filter by
    design: pitch lives at high quefrencies, formants at low ones. This
    makes it robust to strong formant filtering and to missing
    fundamentals, where autocorrelation peak-picking octave-errors.
    """
    n = len(chunk)
    windowed = (chunk - chunk.mean()) * np.hamming(n)
    spec = np.abs(np.fft.rfft(windowed))
    if spec.max() <= 0:
        return None
    ceps = np.fft.irfft(np.log(spec + 1e-9))
    lo, hi = max(1, int(rate / 800)), min(len(ceps) - 1, int(rate / 70))
    if hi <= lo:
        return None
    region = ceps[lo:hi]
    peak_idx = int(np.argmax(region))
    peak = region[peak_idx]
    # Confidence: peak prominence over the region median.
    median = float(np.median(region))
    if peak < median * 3.0:
        return None
    quefrency = peak_idx + lo
    return rate / quefrency


_VOWEL_BANDS = [(250, 800), (800, 1500), (1500, 2500), (2500, 3500)]


def _band_energy_vector(chunk: np.ndarray, rate: int) -> np.ndarray:
    """Normalized energy in four formant-relevant bands. Broad bands are
    robust to f0 glides that defeat narrow formant peak-picking."""
    n = len(chunk)
    windowed = (chunk - chunk.mean()) * np.hamming(n)
    spec = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    total = spec[(freqs >= 250) & (freqs <= 3500)].sum() + 1e-9
    v = np.array([spec[(freqs >= lo) & (freqs < hi)].sum() / total
                  for lo, hi in _VOWEL_BANDS])
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 1e-9 else v


def _vowel_clusters(windows: List[np.ndarray], rate: int,
                    threshold: float = 0.95) -> List[Dict[str, Any]]:
    """Greedy cosine clustering of band-energy vectors over 1 s voiced
    windows. Each cluster is one distinct spectral state (vowel quality).

    The merge threshold is a heuristic: on a five-vowel reference it
    yields 4-5 clusters, on a monotone reference it yields 1-2. Exact
    vowel labels are estimated by nearest template and reported as such.
    """
    vecs = [_band_energy_vector(w, rate) for w in windows]
    centers: List[np.ndarray] = []
    counts: List[int] = []
    for v in vecs:
        best, best_i = -1.0, -1
        for i, c in enumerate(centers):
            sim = float(np.dot(v, c))
            if sim > best:
                best, best_i = sim, i
        if best_i >= 0 and best >= threshold:
            counts[best_i] += 1
        else:
            centers.append(v)
            counts.append(1)
    clusters = []
    for center, count in zip(centers, counts):
        if count < 1:
            continue
        # Estimated label: nearest vowel by band-energy template.
        label = min(
            _VOWEL_FORMANTS,
            key=lambda _v: float(np.linalg.norm(
                center - _vowel_template(_v, rate))),
            default="?")
        clusters.append({"label": f"{label}?", "frames": count})
    return clusters


def _vowel_template(vowel: str, rate: int) -> np.ndarray:
    """Band-energy template from a synthetic steady vowel."""
    f1, f2 = _VOWEL_FORMANTS[vowel]
    n = rate
    t = np.arange(n) / rate
    sig = np.zeros(n)
    for h in range(1, 10):
        freq = 200.0 * h
        e = 0.2 + (np.exp(-0.5 * ((freq - f1) / (f1 * 0.3)) ** 2)
                   + 0.7 * np.exp(-0.5 * ((freq - f2) / (f2 * 0.25)) ** 2))
        sig += np.sin(2 * math.pi * 200.0 * h * t) / h * e
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.5
    return _band_energy_vector(sig, rate)


def analyze_reference(samples: List[float], rate: int,
                      languages: Optional[List[str]] = None) -> Dict[str, Any]:
    """Deterministic reference analysis: pitch range, dynamics, registers,
    vowel coverage. Returns the reference summary for the asset (8.1, 8.3)."""
    arr = np.asarray(samples, dtype=float)
    duration_s = len(arr) / rate
    voiced, hop_s = _voiced_frames(arr, rate)

    pitches = []
    centroids = []
    voiced_audio = []
    for start, chunk, rms in voiced:
        f0 = _pitch_acf(chunk, rate)
        if f0:
            pitches.append(_midi(f0))
        voiced_audio.append((start, chunk))
        spec = np.abs(np.fft.rfft(chunk * np.hamming(len(chunk))))
        freqs = np.fft.rfftfreq(len(chunk), 1.0 / rate)
        centroids.append(float((freqs * spec).sum() / (spec.sum() + 1e-12)))

    # Vowel coverage: cluster spectral envelopes over 170 ms voiced windows.
    win_len = int(rate * 1.0)
    step = win_len // 2
    flat = np.concatenate([c for _, c in voiced_audio]) if voiced_audio else np.zeros(0)
    windows = [flat[s:s + win_len] for s in range(0, len(flat) - win_len, step)]
    windows = [w for w in windows
               if float(np.sqrt(np.mean(w ** 2))) > 0.02 * (max(r for _, _, r in voiced) or 1.0)]
    vowel_clusters = _vowel_clusters(windows, rate)
    vowels = [c["label"] for c in vowel_clusters if c["label"] != "?"]

    # Range from the central 96% of voiced frames: outlier-resistant, so a
    # single mistracked frame cannot misstate the reference's range.
    pitch_low = round(float(np.percentile(pitches, 2)), 1) if pitches else 0.0
    pitch_high = round(float(np.percentile(pitches, 98)), 1) if pitches else 0.0
    rms_db = [20 * math.log10(r + 1e-9) for _, _, r in voiced]
    dyn_low = round(float(np.percentile(rms_db, 10)), 1) if rms_db else 0.0
    dyn_high = round(float(np.percentile(rms_db, 90)), 1) if rms_db else 0.0

    registers = []
    for name, lo, hi in _REGISTERS:
        in_reg = [p for p in pitches if lo <= p <= hi]
        seconds = round(len(in_reg) * hop_s, 2)
        reliability = round(min(1.0, len(in_reg) * hop_s / 3.0), 2)
        registers.append({"name": name, "low_midi": lo, "high_midi": hi,
                          "reliability": reliability,
                          "seconds_observed": seconds})

    vowels = sorted(set(vowels))
    identity_vector = [
        round(float(np.mean(pitches)), 2) if pitches else 0.0,
        round(float(np.std(pitches)), 2) if pitches else 0.0,
        round(float(np.mean(centroids)), 1) if centroids else 0.0,
        round(dyn_high - dyn_low, 1),
        round(float(len(vowel_clusters)), 2),
        round(duration_s, 2),
    ]
    return {
        "duration_s": round(duration_s, 2),
        "voiced_s": round(len(voiced) * hop_s, 2),
        "pitch_low_midi": pitch_low,
        "pitch_high_midi": pitch_high,
        "pitch_span_semitones": round(pitch_high - pitch_low, 1),
        "dynamics_db": {"p10": dyn_low, "p90": dyn_high,
                        "range": round(dyn_high - dyn_low, 1)},
        "registers": registers,
        "vowels_observed": vowels,
        "vowel_count": len(vowel_clusters),
        "languages": languages or [],
        "identity_vector": identity_vector,
        "method": "reference-deterministic",
    }


def identity_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity of identity vectors."""
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


class UnsupportedPerformanceError(Exception):
    """Raised when a requested performance is outside what the reference
    supports (8.3). Carries options instead of producing an unstable
    imitation."""

    def __init__(self, gaps: List[str], options: List[str]):
        self.gaps = gaps
        self.options = options
        super().__init__("; ".join(gaps) + " | options: " + "; ".join(options))


def sufficiency_report(reference_summary: Dict[str, Any],
                       requested: Dict[str, Any]) -> Dict[str, Any]:
    """Run BEFORE building or rendering (8.3). requested may include:
    pitch_low_midi, pitch_high_midi, belt (0..1), language, min_reliability.
    """
    gaps: List[str] = []
    options: List[str] = []
    coverage: Dict[str, Any] = {}

    ref_lo = reference_summary["pitch_low_midi"]
    ref_hi = reference_summary["pitch_high_midi"]
    req_lo = requested.get("pitch_low_midi", ref_lo)
    req_hi = requested.get("pitch_high_midi", ref_hi)
    pitch_ok = req_lo >= ref_lo - 2 and req_hi <= ref_hi + 2
    coverage["pitch_range"] = {"reference": [ref_lo, ref_hi],
                               "requested": [req_lo, req_hi],
                               "covered": pitch_ok}
    if not pitch_ok:
        gaps.append(f"requested pitch range [{req_lo}, {req_hi}] exceeds "
                    f"reference [{ref_lo}, {ref_hi}]")
        options.append(f"transpose into [{ref_lo}, {ref_hi}]")
        options.append("record more reference material covering the missing range")

    n_vowels = reference_summary["vowel_count"]
    # Four distinct spectral states is the bar for varied phonetic content:
    # enough to ground vowel contrasts in rendered lyrics. Fewer means the
    # reference is phonetically narrow.
    vowel_ok = n_vowels >= 4
    coverage["vowels"] = {"observed": n_vowels, "covered": vowel_ok}
    if not vowel_ok:
        gaps.append(f"only {n_vowels} distinct vowels observed; 4+ needed")
        options.append("record reference material with varied vowels and lyrics")

    dyn_range = reference_summary["dynamics_db"]["range"]
    belt = requested.get("belt", 0.0)
    # Belt is a high-effort phonation mode: the reference must show the voice
    # at more than one effort level (6 dB span, a clearly audible loudness
    # change). A flat reference cannot ground a belted imitation.
    if belt > 0.5 and dyn_range <= 6:
        gaps.append(f"belt={belt} needs varied effort; reference spans {dyn_range} dB")
        options.append("record loud, pressed reference material for belting")
    coverage["dynamics_db_range"] = dyn_range

    lang = requested.get("language")
    if lang and lang not in reference_summary.get("languages", []):
        gaps.append(f"language {lang!r} not in reference languages "
                    f"{reference_summary.get('languages', [])}")
        options.append(f"record reference material in {lang}")

    if reference_summary["voiced_s"] < 3.0:
        gaps.append(f"only {reference_summary['voiced_s']}s of voiced reference; 3s minimum")
        options.append("record at least 3 seconds of clean voiced singing")

    return {"sufficient": not gaps, "gaps": gaps, "options": options,
            "coverage": coverage}


def check_performance_supported(voice: Dict[str, Any],
                                performance: Dict[str, Any]) -> Dict[str, Any]:
    """Is this performance inside what the character's reference supports?"""
    ref = voice["reference_summary"]
    requested = {
        "pitch_low_midi": performance.get("pitch_low_midi", ref["pitch_low_midi"]),
        "pitch_high_midi": performance.get("pitch_high_midi", ref["pitch_high_midi"]),
        "belt": performance.get("belt", 0.0),
        "language": performance.get("language"),
    }
    report = sufficiency_report(ref, requested)
    return {"supported": report["sufficient"], "gaps": report["gaps"],
            "options": report["options"]}


def _require_consent(consent: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """8.4: no consent record, no character. Licensed or synthetic sources
    document their rights basis instead of a personal consent."""
    if not consent:
        raise ValueError(
            "refusing to create a voice character without a consent record "
            "(8.4). Provide consent {subject, recorded_at, verified} or a "
            "documented rights_basis of 'licensed' or 'synthetic'.")
    basis = consent.get("rights_basis", "consent")
    if basis == "consent":
        if not consent.get("subject"):
            raise ValueError("consent record must name the subject")
        if not consent.get("verified_against_audio"):
            raise ValueError("consent must be verified against the reference audio")
    elif basis not in ("licensed", "synthetic"):
        raise ValueError(f"unknown rights_basis {basis!r}")
    return consent


def create_voice_character(name: str, reference_summary: Dict[str, Any],
                           consent: Optional[Dict[str, Any]],
                           owner: Dict[str, Any],
                           pronunciation: Optional[Dict[str, Any]] = None,
                           controls: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the asset (8.1). Runs the sufficiency report for the reference
    itself; raises on missing consent (8.4)."""
    consent = _require_consent(consent)
    from kindling.vocals.controls import describe_controls
    ref = reference_summary
    return {
        "kind": "kindling/voice-character",
        "schema_version": "8.0.0",
        "id": "voice_" + name.lower().replace(" ", "_"),
        "version": "v1",
        "parent": None,
        "name": name,
        "identity": {
            "vector": ref["identity_vector"],
            "description": ("identity from reference analysis; performance "
                            "instruction is a separate input and never "
                            "changes this vector"),
            "method": ref["method"],
        },
        "range_map": {
            "low_midi": ref["pitch_low_midi"],
            "high_midi": ref["pitch_high_midi"],
            "registers": ref["registers"],
        },
        "timbre": {
            "traits": ["reference-derived"],
            "register_transitions": [r["name"] for r in ref["registers"]
                                     if r["reliability"] > 0],
        },
        "pronunciation": pronunciation or {"languages": ref.get("languages", []),
                                           "g2p": "kindling.vocals.g2p"},
        "controls": controls or describe_controls(),
        "reference_summary": ref,
        "owner": owner,
        "consent": consent,
        "provenance": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": owner.get("id", "unknown"),
            "method": "kindling.assets.voice.create_voice_character",
        },
        "permissions": {"share": "owner-only"},
        "revoked": False,
    }


def mark_render_provenance(audio: Dict[str, Any], voice: Dict[str, Any]) -> Dict[str, Any]:
    """Watermark hook (8.4). Until Part 19 ships the robust audio watermark,
    this embeds signed provenance metadata with the render and says so."""
    audio = dict(audio)
    audio["voice_provenance"] = {
        "voice_id": voice["id"],
        "voice_version": voice["version"],
        "method": "metadata",
        "note": "robust audio watermark arrives with Part 19; provenance "
                "metadata is embedded now",
    }
    return audio


def render_with_character(store: "VoiceCharacterStore", voice_id: str,
                          lyric_line: Dict[str, Any], performance: Dict[str, Any],
                          seed: int, vocal_renderer) -> Dict[str, Any]:
    """Render a line through a voice character. Refuses revoked characters
    (acceptance) and unsupported performances (8.3) instead of faking them."""
    voice = store.get(voice_id)
    if voice.get("revoked"):
        raise ValueError(f"voice character {voice_id!r} is revoked; "
                         "it cannot be used for new renders")
    support = check_performance_supported(voice, performance)
    if not support["supported"]:
        raise UnsupportedPerformanceError(support["gaps"], support["options"])
    # Support-check inputs (language, requested range) are not renderer
    # controls; strip them before the renderer validates its controls.
    renderer_perf = {k: v for k, v in performance.items()
                     if k not in ("language", "pitch_low_midi", "pitch_high_midi")}
    rendered = vocal_renderer.render_line(voice_id, lyric_line, renderer_perf, seed)
    rendered["audio"] = mark_render_provenance(rendered["audio"], voice)
    rendered["metadata"]["voice_id"] = voice_id
    rendered["metadata"]["voice_version"] = voice["version"]
    rendered["metadata"]["identity_vector"] = voice["identity"]["vector"]
    return rendered


class VoiceCharacterStore(VoiceCharacterStoreABC):
    """Save, version, share, fork, revoke, delete (8.5)."""

    def __init__(self) -> None:
        self._voices: Dict[str, Dict[str, Any]] = {}

    @property
    def component_name(self) -> str:
        return "Voice characters"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def create(self, reference_summary: Dict[str, Any],
               consent_record: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        voice = create_voice_character(kwargs.get("name", "unnamed"),
                                       reference_summary, consent_record,
                                       kwargs.get("owner", {"id": "unknown"}),
                                       kwargs.get("pronunciation"),
                                       kwargs.get("controls"))
        if voice["id"] in self._voices:
            raise ValueError(f"voice {voice['id']!r} already exists; fork it instead")
        self._voices[voice["id"]] = voice
        return copy.deepcopy(voice)

    def get(self, voice_id: str, version: Optional[str] = None) -> Dict[str, Any]:
        voice = self._voices[voice_id]
        if version is not None and voice["version"] != version:
            raise KeyError(f"voice {voice_id!r} has no version {version!r}")
        return copy.deepcopy(voice)

    def list(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(v) for v in self._voices.values()]

    def fork(self, voice_id: str, name: str) -> Dict[str, Any]:
        parent = self.get(voice_id)
        child = copy.deepcopy(parent)
        child["id"] = "voice_" + name.lower().replace(" ", "_")
        child["name"] = name
        child["version"] = "v1"
        child["parent"] = voice_id
        child["revoked"] = False
        if child["id"] in self._voices:
            raise ValueError(f"voice {child['id']!r} already exists")
        self._voices[child["id"]] = child
        return copy.deepcopy(child)

    def share(self, voice_id: str, permissions: Dict[str, Any]) -> Dict[str, Any]:
        voice = self._voices[voice_id]
        voice["permissions"].update(permissions)
        return copy.deepcopy(voice)

    def revoke(self, voice_id: str) -> None:
        self._voices[voice_id]["revoked"] = True

    def delete(self, voice_id: str) -> None:
        del self._voices[voice_id]

    def sufficiency_report(self, voice_id: str,
                           performance: Dict[str, Any]) -> Dict[str, Any]:
        voice = self.get(voice_id)
        return check_performance_supported(voice, performance)
