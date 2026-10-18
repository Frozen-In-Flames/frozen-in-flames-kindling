#!/usr/bin/env python3
"""Phase-gate checker (Part 22): reads git tags, reports which build
phases have their versions shipped.

Usage: python3 tools/check_phase_gates.py
"""

import subprocess
import sys

# Phase -> required versions (tags).
PHASES = {
    "Phase 0 (Decisions)": ["v1"],
    "Phase 1 (Foundations)": ["v2", "v3", "v4", "v15", "v19"],
    "Phase 2 (Representation)": ["v5"],
    "Phase 3 (Vocals)": ["v7"],
    "Phase 4 (Editing)": ["v12"],
    "Phase 5 (Assets)": ["v8", "v9", "v10"],
    "Phase 6 (Artist profile)": ["v11"],
    "Phase 7 (Workflow)": ["v13", "v14"],
    "Phase 8 (Full-song planning)": ["v6"],
    "Phase 9 (Efficiency/deploy)": ["v16", "v18"],
    "Phase 10 (Release)": ["v17", "v20", "v21", "v22", "v23"],
}


def get_tags():
    out = subprocess.run(["git", "tag", "-l"], capture_output=True,
                         text=True, check=True)
    return set(out.stdout.split())


def main():
    tags = get_tags()
    all_ok = True
    for phase, required in PHASES.items():
        missing = [t for t in required if t not in tags]
        if missing:
            print(f"[ ] {phase}: missing {', '.join(missing)}")
            all_ok = False
        else:
            print(f"[x] {phase}: {', '.join(required)} shipped")
    print()
    if all_ok:
        print("All phases gated: every required version is tagged.")
        return 0
    print("Some phases are not yet gated.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
