#!/usr/bin/env python3
"""Report which quality targets (targets.yaml) still lack numeric thresholds.

Per Build Manual Part 1.3: every row gets a numeric threshold before training
anything. Thresholds are published and reviewed quarterly. This tool reports the
current state; it is a gate for training, not for building.
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "targets.yaml").read_text())
    targets = data.get("targets", [])

    unset = [t for t in targets if str(t.get("threshold", "TBD")).strip().upper() == "TBD"]
    print(f"Quality targets: {len(targets)} total, {len(targets) - len(unset)} set, {len(unset)} unset.")
    for t in targets:
        mark = "SET  " if str(t.get("threshold", "TBD")).strip().upper() != "TBD" else "UNSET"
        print(f"  [{mark}] {t['dimension']}: threshold={t.get('threshold')}")
    if unset:
        print("\nUnset thresholds block training, not building (Part 1.3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
