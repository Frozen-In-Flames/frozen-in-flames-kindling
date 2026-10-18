"""Kindling CLI (14.3): render a saved scene reproducibly.

Usage:
  kindling render scene.json --out out.wav --tier draft --seed 0
  kindling api-spec --out openapi.json
  kindling daw-export scene.json stems/ --out daw/
"""

import argparse
import json
import sys

import numpy as np


def cmd_render(args):
    from kindling.api.handlers import scene_create, render_submit, job_status
    with open(args.scene) as f:
        scene = json.load(f)
    created = scene_create(scene)
    sub = render_submit(created["scene_id"], tier=args.tier, seed=args.seed)
    st = job_status(sub["job_id"])
    print(json.dumps({"scene_id": created["scene_id"],
                      "status": st["status"],
                      "result": st["result"]}, indent=1, default=str))
    if args.out and st["status"] == "done":
        # Re-render to WAV via the deterministic renderer.
        from kindling.planning.renderer import ReferenceRenderer
        renderer = ReferenceRenderer()
        out = renderer.render_fragment(scene, {}, args.seed, args.tier)
        from kindling.mix import write_wav
        write_wav(args.out, out["audio"]["samples"].T,
                  out["audio"]["sample_rate"], 16)
        print(f"wrote {args.out}")
    return 0 if st["status"] == "done" else 1


def cmd_api_spec(args):
    from kindling.api.spec import openapi_spec
    spec = openapi_spec()
    with open(args.out, "w") as f:
        json.dump(spec, f, indent=1)
    print(f"wrote {args.out}")
    return 0


def cmd_daw_export(args):
    from kindling.api.daw import export_stems_for_daw
    with open(args.scene) as f:
        scene = json.load(f)
    # Reference: silent stems shaped by the scene length (real stems come
    # from the mixer; this exercises the bridge format).
    rate = 48000
    stems = {p.get("id", f"part{i}"): np.zeros(rate * 4)
             for i, p in enumerate(scene.get("parts", []))}
    result = export_stems_for_daw(stems or {"empty": np.zeros(rate)},
                                  scene, args.out, rate)
    print(json.dumps(result, indent=1))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kindling")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render")
    p.add_argument("scene")
    p.add_argument("--out", default=None)
    p.add_argument("--tier", default="draft")
    p.add_argument("--seed", type=int, default=0)
    p = sub.add_parser("api-spec")
    p.add_argument("--out", required=True)
    p = sub.add_parser("daw-export")
    p.add_argument("scene")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "render":
        return cmd_render(args)
    if args.cmd == "api-spec":
        return cmd_api_spec(args)
    if args.cmd == "daw-export":
        return cmd_daw_export(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
