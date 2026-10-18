#!/usr/bin/env python3
"""Release checklist verifier (Part 23): every item verified and recorded.

Runs the test suite for each checklist item and reports pass/fail.
A release ships only when every item is verified.
"""

import subprocess
import sys

# Checklist item -> pytest paths that verify it.
CHECKS = {
    "Targets: Part 1 thresholds": ["tools/check_targets.py"],
    "Scene: round-trip, diff, reproducibility": ["tests/test_scene.py"],
    "Data: leakage audit, license ledger": ["tests/test_data.py"],
    "Representation: reconstruction and seams": ["tests/test_codec.py"],
    "Generation: coherence and completeness": ["tests/test_planning.py"],
    "Vocals: intelligibility per language": ["tests/test_vocals.py"],
    "Voice characters: identity, sufficiency, consent": ["tests/test_voice.py"],
    "Instruments: unseen passages, controls, audit": ["tests/test_instruments.py"],
    "Presets: self-fit, transfer, editability": ["tests/test_presets.py"],
    "Artist profile: evidence, correction, deletion": ["tests/test_profile.py"],
    "Editing: locality, seams, instruction success": ["tests/test_editing.py"],
    "Mix/export: loudness, clipping, stem-sum": ["tests/test_mix.py"],
    "Interface/API: sessions, docs match": ["tests/test_api.py"],
    "Project: bundle, pinning, migration": ["tests/test_project.py"],
    "Training: stages, ablations, guards": ["tests/test_training.py"],
    "Evaluation: suite, checks, gates": ["tests/test_eval.py", "tests/test_risks.py"],
    "Operations: recovery, security": ["tests/test_ops.py"],
    "Safety: watermark, consent, deletion": ["tests/test_safety.py"],
}


def run_check(paths):
    if paths[0].endswith(".py") and not paths[0].startswith("tests/"):
        r = subprocess.run([sys.executable, paths[0]], capture_output=True)
        return r.returncode == 0
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"] + paths,
                       capture_output=True)
    return r.returncode == 0


def main():
    results = {}
    for item, paths in CHECKS.items():
        ok = run_check(paths)
        results[item] = ok
        print(f"[{'x' if ok else ' '}] {item}")
    print()
    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"BLOCKED: {len(failed)} checklist items failing.")
        return 1
    print("All release checklist items verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
