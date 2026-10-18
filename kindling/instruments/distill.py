"""Distillation workflow (9.3): teacher -> student -> loss audit.

1. Choose a teacher (high-detail reference synth).
2. Generate a broad, controlled set of performances across controls and
   contexts (the distillation set).
3. Fit the student's free parameters to the teacher (grid search on the
   reference implementation's parameter space).
4. Run a loss audit: timbre, range, articulation, expression,
   controllability, latency.
5. Record the audit in the asset. Ship only if it clears thresholds.

This is the real workflow with procedural stand-ins. A neural student
would replace the parametric fit in step 3 behind the same interface;
the audit in step 4 is model-agnostic.
"""

import time
from typing import Any, Dict, List, Tuple

import numpy as np

from .synth import StudentBass, StudentGuitar, TeacherBass, TeacherGuitar

# Audit thresholds: ship only if the student clears all of these.
AUDIT_THRESHOLDS = {
    "spectral_distance_db": 6.0,   # mean log-spectral distance
    "attack_ms_diff": 8.0,         # onset attack time mismatch
    "student_realtime_factor": 1.0,  # must render faster than real-time
    "control_monotonic": True,     # brightness control must be monotonic
}


def _spectral_distance(a: np.ndarray, b: np.ndarray, rate: int) -> float:
    n = min(len(a), len(b))
    win = int(rate * 0.05)
    dists = []
    for s in range(0, n - win, win // 2):
        sa = np.abs(np.fft.rfft(a[s:s + win] * np.hanning(win))) + 1e-9
        sb = np.abs(np.fft.rfft(b[s:s + win] * np.hanning(win))) + 1e-9
        dists.append(float(np.mean(np.abs(20 * np.log10(sa / sb)))))
    return float(np.mean(dists)) if dists else 0.0


def _attack_time(sig: np.ndarray, rate: int) -> float:
    # Onset attack: time to the first peak within 100 ms. (Measuring to a
    # late global peak would conflate attack with decay shape.)
    window = sig[:int(rate * 0.1)]
    env = np.abs(window)
    peak = env.max()
    if peak <= 0:
        return 0.0
    idx = int(np.argmax(env))
    return idx / rate * 1000.0


def distillation_set() -> List[Tuple[List[Dict], Dict]]:
    """Broad, controlled performances: notes x controls."""
    cases = []
    note_sets = [
        [{"midi": 45, "start_s": 0.0, "dur_s": 0.5, "vel": 0.8}],
        [{"midi": 40 + i * 2, "start_s": i * 0.25, "dur_s": 0.3, "vel": 0.7}
         for i in range(4)],
        [{"midi": 55, "start_s": 0.0, "dur_s": 1.0, "vel": 1.0},
         {"midi": 60, "start_s": 0.5, "dur_s": 1.0, "vel": 0.6}],
    ]
    controls = [
        {"tone": 0.0, "attack": 0.5, "space": 0.0},
        {"tone": 0.5, "attack": 0.5, "space": 0.2},
        {"tone": 1.0, "attack": 0.9, "space": 0.4},
    ]
    for ns in note_sets:
        for c in controls:
            cases.append((ns, c))
    return cases


def distill_guitar(rate: int = 22050) -> Dict[str, Any]:
    """Fit StudentGuitar to TeacherGuitar; return the audit."""
    teacher = TeacherGuitar()
    cases = distillation_set()
    best, best_loss = None, float("inf")
    for damping_bias in (-0.005, 0.0, 0.005):
        for excite_decay in (0.995, 1.0):
            student = StudentGuitar(damping_bias=damping_bias,
                                    excite_decay=excite_decay)
            loss = 0.0
            for notes, controls in cases:
                t = teacher.render(notes, controls, rate, seed=7)
                s = student.render(notes, controls, rate, seed=7)
                loss += _spectral_distance(t, s, rate)
            loss /= len(cases)
            if loss < best_loss:
                best_loss, best = loss, (damping_bias, excite_decay)
    damping_bias, excite_decay = best
    student = StudentGuitar(damping_bias=damping_bias,
                            excite_decay=excite_decay)

    # Loss audit on held-out material (unseen passages).
    held_out = [
        ([{"midi": 48 + i, "start_s": i * 0.2, "dur_s": 0.25, "vel": 0.75}
          for i in range(6)], {"tone": 0.3, "attack": 0.6, "space": 0.1}),
        ([{"midi": 36, "start_s": 0.0, "dur_s": 2.0, "vel": 0.9}],
         {"tone": 0.8, "attack": 0.2, "space": 0.3}),
    ]
    spec_dists, attack_diffs = [], []
    student_rtf = []
    for notes, controls in held_out:
        t = teacher.render(notes, controls, rate, seed=11)
        t0 = time.perf_counter()
        s = student.render(notes, controls, rate, seed=11)
        elapsed = time.perf_counter() - t0
        audio_s = len(s) / rate
        student_rtf.append(elapsed / audio_s)
        spec_dists.append(_spectral_distance(t, s, rate))
        attack_diffs.append(abs(_attack_time(t, rate) - _attack_time(s, rate)))

    # Controllability: tone control must be monotonic in brightness.
    brightness = []
    notes = [{"midi": 50, "start_s": 0.0, "dur_s": 0.5, "vel": 0.8}]
    for tone in (0.0, 0.5, 1.0):
        sig = student.render(notes, {"tone": tone, "attack": 0.5,
                                     "space": 0.0}, rate, seed=3)
        spec = np.abs(np.fft.rfft(sig * np.hanning(len(sig))))
        freqs = np.fft.rfftfreq(len(sig), 1.0 / rate)
        centroid = float((freqs * spec).sum() / (spec.sum() + 1e-9))
        brightness.append(centroid)
    monotonic = all(b2 > b1 for b1, b2 in zip(brightness, brightness[1:]))

    audit = {
        "student_params": {"damping_bias": damping_bias,
                           "excite_decay": excite_decay},
        "fit_spectral_distance_db": round(best_loss, 2),
        "held_out_spectral_distance_db": round(float(np.mean(spec_dists)), 2),
        "held_out_attack_ms_diff": round(float(np.mean(attack_diffs)), 2),
        "student_realtime_factor": round(float(np.mean(student_rtf)), 3),
        "control_monotonic": bool(monotonic),
        "brightness_by_tone": [round(b, 1) for b in brightness],
        "thresholds": AUDIT_THRESHOLDS,
    }
    audit["passes"] = (
        audit["held_out_spectral_distance_db"]
        <= AUDIT_THRESHOLDS["spectral_distance_db"]
        and audit["held_out_attack_ms_diff"]
        <= AUDIT_THRESHOLDS["attack_ms_diff"]
        and audit["student_realtime_factor"]
        <= AUDIT_THRESHOLDS["student_realtime_factor"]
        and audit["control_monotonic"]
        == AUDIT_THRESHOLDS["control_monotonic"]
    )
    return {"student": student, "audit": audit}


def distill_bass(rate: int = 22050) -> Dict[str, Any]:
    """Fit StudentBass to TeacherBass; return the audit."""
    teacher = TeacherBass()
    cases = distillation_set()
    best, best_loss = None, float("inf")
    for filter_bias in (-0.02, 0.0, 0.02):
        student = StudentBass(filter_bias=filter_bias)
        loss = 0.0
        for notes, controls in cases:
            t = teacher.render(notes, controls, rate, seed=7)
            s = student.render(notes, controls, rate, seed=7)
            loss += _spectral_distance(t, s, rate)
        loss /= len(cases)
        if loss < best_loss:
            best_loss, best = loss, filter_bias
    student = StudentBass(filter_bias=best)
    held_out = [
        ([{"midi": 33 + i, "start_s": i * 0.25, "dur_s": 0.3, "vel": 0.8}
          for i in range(4)], {"tone": 0.6, "attack": 0.7, "space": 0.0}),
    ]
    spec_dists = []
    student_rtf = []
    for notes, controls in held_out:
        t = teacher.render(notes, controls, rate, seed=11)
        t0 = time.perf_counter()
        s = student.render(notes, controls, rate, seed=11)
        elapsed = time.perf_counter() - t0
        student_rtf.append(elapsed / (len(s) / rate))
        spec_dists.append(_spectral_distance(t, s, rate))
    audit = {
        "student_params": {"filter_bias": best},
        "fit_spectral_distance_db": round(best_loss, 2),
        "held_out_spectral_distance_db": round(float(np.mean(spec_dists)), 2),
        "student_realtime_factor": round(float(np.mean(student_rtf)), 3),
        "thresholds": AUDIT_THRESHOLDS,
    }
    audit["passes"] = (
        audit["held_out_spectral_distance_db"]
        <= AUDIT_THRESHOLDS["spectral_distance_db"]
        and audit["student_realtime_factor"]
        <= AUDIT_THRESHOLDS["student_realtime_factor"]
    )
    return {"student": student, "audit": audit}
