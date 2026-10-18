"""Kindling CLI (14.3, Phase A).

Library (upload / save / list / delete):
  kindling library upload <file> --kind voice|instrument|preset --name X \\
      [--owner ID] [--consent-subject NAME | --rights-basis licensed|synthetic] \\
      [--role guitar] [--library DIR]
  kindling library ingest <record.json> [--audio <wav>] [--library DIR]
  kindling library list [--kind voice] [--library DIR]
  kindling library show <id> [--library DIR]
  kindling library rename <id> <new-name> [--library DIR]
  kindling library delete <id> [--library DIR]

Render from the library (prompt + lyrics + saved assets -> song):
  kindling render --prompt "..." --lyrics-file lyrics.txt --voice <id> \\
      [--instrument role=<id>] [--preset <id>] [--profile <id>] \\
      [--seed 7] [--tier draft] [--out outdir] [--library DIR]

Render a saved scene (legacy):
  kindling render scene.json --out out.wav --tier draft --seed 0

Export a render project:
  kindling export <projectdir> --format wav|stems|midi [--out outdir]

  kindling api-spec --out openapi.json
  kindling daw-export scene.json stems/ --out daw/
"""

import argparse
import json
import os
import shutil
import sys

import numpy as np


def _library(args):
    from kindling.library import AssetLibrary
    return AssetLibrary(getattr(args, "library", None))


def _owner(args):
    return {"id": getattr(args, "owner", None) or "owner"}


# ---------------------------------------------------------------- library
def cmd_library_upload(args):
    from kindling.library import load_audio
    from kindling.library.builders import (build_instrument_asset,
                                           build_preset_asset,
                                           build_voice_asset, make_consent)
    from kindling.library.store import _now
    lib = _library(args)
    owner = _owner(args)
    if args.kind == "voice":
        samples, rate = load_audio(args.file, target_rate=44100, mono=True)
        consent = make_consent(subject=args.consent_subject,
                               rights_basis=args.rights_basis,
                               rights_note=args.rights_note,
                               attested_by=owner["id"])
        voice, build_report = build_voice_asset(
            samples, rate, args.name, owner, consent,
            languages=[args.language] if args.language else None,
            reference_note=args.reference_note)
        asset_id = lib._unique_id("voice", args.name)
        sha = lib.store_audio(samples, rate)
        record = {"id": asset_id, "asset_kind": "voice", "name": args.name,
                  "owner": owner, "source_audio_sha256": sha,
                  "provenance": {"uploaded_file": os.path.basename(args.file),
                                 "uploaded_at": _now(),
                                 "analysis": "kindling.library.builders"},
                  "consent": consent,
                  "notes": build_report["warnings"],
                  "payload": voice}
        # The payload id is the library id.
        record["payload"]["id"] = asset_id
        saved = lib.save_record(record)
        print(json.dumps({"id": saved["id"], "kind": "voice",
                          "sufficiency": build_report["sufficiency"],
                          "warnings": build_report["warnings"]}, indent=1))
    elif args.kind == "instrument":
        samples, rate = load_audio(args.file, target_rate=44100, mono=True)
        payload, build_report = build_instrument_asset(
            samples, rate, args.name, owner,
            default_role=args.role or "keys")
        asset_id = lib._unique_id("instrument", args.name)
        sha = lib.store_audio(samples, rate)
        record = {"id": asset_id, "asset_kind": "instrument",
                  "name": args.name, "owner": owner,
                  "source_audio_sha256": sha,
                  "provenance": {"uploaded_file": os.path.basename(args.file),
                                 "uploaded_at": _now()},
                  "notes": build_report["warnings"],
                  "payload": payload}
        saved = lib.save_record(record)
        print(json.dumps({"id": saved["id"], "kind": "instrument",
                          "report": build_report}, indent=1))
    elif args.kind == "preset":
        stereo, rate = load_audio(args.file, target_rate=44100, mono=False)
        payload, build_report = build_preset_asset(stereo, rate, args.name,
                                                  owner)
        asset_id = lib._unique_id("preset", args.name)
        sha = lib.store_audio(stereo.mean(axis=0), rate)
        record = {"id": asset_id, "asset_kind": "preset",
                  "name": args.name, "owner": owner,
                  "source_audio_sha256": sha,
                  "provenance": {"uploaded_file": os.path.basename(args.file),
                                 "uploaded_at": _now()},
                  "notes": [payload["disclaimer"]],
                  "payload": payload}
        saved = lib.save_record(record)
        print(json.dumps({"id": saved["id"], "kind": "preset",
                          "report": build_report}, indent=1))
    else:
        raise ValueError(f"unknown kind {args.kind!r}")
    return 0


def cmd_library_ingest(args):
    lib = _library(args)
    with open(args.record) as f:
        record = json.load(f)
    saved = lib.ingest(record, audio_path=args.audio, notes=args.note)
    print(json.dumps({"id": saved["id"], "kind": saved["asset_kind"],
                      "name": saved["name"]}, indent=1))
    return 0


def cmd_library_list(args):
    lib = _library(args)
    items = lib.list(asset_kind=args.kind)
    for item in items:
        print(f"{item['id']}\t{item['asset_kind']}\t{item['name']}\t"
              f"{item['version']}")
    return 0


def cmd_library_show(args):
    lib = _library(args)
    rec = lib.get(args.id)
    view = {k: v for k, v in rec.items() if k != "payload"}
    payload = rec.get("payload", {})
    if rec.get("asset_kind") == "voice":
        view["voice"] = {
            "name": payload.get("name"),
            "range_midi": [payload.get("range_map", {}).get("low_midi"),
                           payload.get("range_map", {}).get("high_midi")],
            "vowels": (payload.get("reference_summary") or {}).get(
                "vowels_observed"),
            "revoked": payload.get("revoked"),
        }
    elif rec.get("asset_kind") == "instrument":
        view["instrument"] = {
            "default_role": payload.get("default_role"),
            "slices": len(payload.get("slices", [])),
            "unpitched": payload.get("unpitched"),
        }
    elif rec.get("asset_kind") == "preset":
        view["preset"] = {
            "chain": [fx["type"] for fx in
                      payload.get("preset", {}).get("chain", [])],
            "confidence": payload.get("confidence"),
        }
    print(json.dumps(view, indent=1, default=str))
    return 0


def cmd_library_rename(args):
    lib = _library(args)
    saved = lib.rename(args.id, args.new_name)
    print(json.dumps({"id": saved["id"], "name": saved["name"]}, indent=1))
    return 0


def cmd_library_delete(args):
    lib = _library(args)
    report = lib.delete(args.id)
    print(json.dumps(report, indent=1))
    return 0


# ---------------------------------------------------------------- render
def cmd_render(args):
    if args.prompt:
        return cmd_render_compose(args)
    return cmd_render_scene(args)


def cmd_render_scene(args):
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
        from kindling.planning.renderer import ReferenceRenderer
        renderer = ReferenceRenderer()
        out = renderer.render_fragment(scene, {}, args.seed, args.tier)
        from kindling.mix import write_wav
        write_wav(args.out, out["audio"]["samples"].T,
                  out["audio"]["sample_rate"], 16)
        print(f"wrote {args.out}")
    return 0 if st["status"] == "done" else 1


def cmd_render_compose(args):
    from kindling.library.song import compose
    lib = _library(args)
    with open(args.lyrics_file) as f:
        lyrics = f.read()
    instrument_map = {}
    for item in args.instrument or []:
        if "=" in item:
            role, aid = item.split("=", 1)
            instrument_map[role.strip()] = aid.strip()
        else:
            rec = lib.get(item.strip())
            role = (rec.get("payload") or {}).get("default_role", "keys")
            instrument_map[role] = item.strip()
    report = compose(
        prompt=args.prompt, lyrics_text=lyrics, library=lib,
        voice_id=args.voice, instrument_map=instrument_map,
        preset_id=args.preset, profile_id=args.profile,
        seed=args.seed, tier=args.tier, owner=_owner(args),
        out_dir=args.out)
    manifest = report.get("manifest", {})
    summary = {
        "out_dir": report.get("out_dir"),
        "files": {k: v for k, v in manifest.items()
                   if k in ("mix", "midi", "lyrics", "sidecar", "scene",
                            "mix_pre_preset")},
        "stems": len(manifest.get("stems", [])),
        "sections": report["sections"],
        "parts": report["parts"],
        "vocal_lines": report["vocal_lines"],
        "asset_versions": report["asset_versions"],
        "mix_lufs": report["mix_report"]["loudness_lufs"],
        "true_peak_dbfs": report["mix_report"]["true_peak_dbfs"],
        "assumptions": report["assumptions"],
        "warnings": report["warnings"],
    }
    print(json.dumps(summary, indent=1, default=str))
    return 0


# ---------------------------------------------------------------- export
def cmd_export(args):
    sidecar_path = os.path.join(args.project, "sidecar.json")
    with open(sidecar_path) as f:
        sidecar = json.load(f)
    scene = sidecar["scene"]
    out = args.out or os.path.join(args.project, f"export-{args.format}")
    os.makedirs(out, exist_ok=True)
    if args.format == "wav":
        shutil.copy(os.path.join(args.project, "mix.wav"),
                    os.path.join(out, "mix.wav"))
        print(f"wrote {out}/mix.wav")
    elif args.format == "stems":
        stems_dir = os.path.join(args.project, "stems")
        for name in sorted(os.listdir(stems_dir)):
            if name.endswith(".wav"):
                shutil.copy(os.path.join(stems_dir, name),
                            os.path.join(out, name))
        print(f"wrote {len(os.listdir(out))} stems to {out}/")
    elif args.format == "midi":
        from kindling.mix.export import export_midi
        midi_path = os.path.join(out, "score.mid")
        ok = export_midi(scene, midi_path)
        if not ok:
            print("no note-bearing parts; MIDI not produced")
            return 1
        print(f"wrote {midi_path}")
    else:
        raise ValueError(f"unknown format {args.format!r}")
    return 0


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
    rate = 48000
    stems = {p.get("id", f"part{i}"): np.zeros(rate * 4)
             for i, p in enumerate(scene.get("parts", []))}
    result = export_stems_for_daw(stems or {"empty": np.zeros(rate)},
                                  scene, args.out, rate)
    print(json.dumps(result, indent=1))
    return 0


def _add_library_args(p):
    p.add_argument("--library", default=None,
                   help="library root (default ~/.kindling/library)")
    p.add_argument("--owner", default=None)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kindling")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render")
    p.add_argument("scene", nargs="?",
                   help="scene JSON (legacy) or omit with --prompt")
    p.add_argument("--prompt", default=None)
    p.add_argument("--lyrics-file", default=None)
    p.add_argument("--voice", default=None)
    p.add_argument("--instrument", action="append", default=None,
                   help="asset id or role=asset-id; repeatable")
    p.add_argument("--preset", default=None)
    p.add_argument("--profile", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--tier", default="draft")
    p.add_argument("--seed", type=int, default=0)
    _add_library_args(p)

    p = sub.add_parser("export")
    p.add_argument("project")
    p.add_argument("--format", required=True, choices=["wav", "stems", "midi"])
    p.add_argument("--out", default=None)

    lp = sub.add_parser("library")
    lsub = lp.add_subparsers(dest="lcmd", required=True)

    p = lsub.add_parser("upload")
    p.add_argument("file")
    p.add_argument("--kind", required=True,
                   choices=["voice", "instrument", "preset"])
    p.add_argument("--name", required=True)
    p.add_argument("--consent-subject", default=None)
    p.add_argument("--rights-basis", default=None,
                   choices=["licensed", "synthetic"])
    p.add_argument("--rights-note", default=None)
    p.add_argument("--role", default=None,
                   help="default role for instrument assets")
    p.add_argument("--language", default=None)
    p.add_argument("--reference-note", default=None)
    _add_library_args(p)

    p = lsub.add_parser("ingest")
    p.add_argument("record")
    p.add_argument("--audio", default=None)
    p.add_argument("--note", action="append", default=None,
                   help="annotation stored on the record; repeatable")
    _add_library_args(p)

    p = lsub.add_parser("list")
    p.add_argument("--kind", default=None,
                   choices=["voice", "instrument", "preset", "profile"])
    _add_library_args(p)

    p = lsub.add_parser("show")
    p.add_argument("id")
    _add_library_args(p)

    p = lsub.add_parser("rename")
    p.add_argument("id")
    p.add_argument("new_name")
    _add_library_args(p)

    p = lsub.add_parser("delete")
    p.add_argument("id")
    _add_library_args(p)

    p = sub.add_parser("api-spec")
    p.add_argument("--out", required=True)
    p = sub.add_parser("daw-export")
    p.add_argument("scene")
    p.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "render":
        if args.prompt and not args.lyrics_file:
            parser.error("--prompt needs --lyrics-file")
        if not args.prompt and not args.scene:
            parser.error("give a scene JSON or --prompt/--lyrics-file")
        return cmd_render(args)
    if args.cmd == "export":
        return cmd_export(args)
    if args.cmd == "library":
        return {"upload": cmd_library_upload,
                "ingest": cmd_library_ingest,
                "list": cmd_library_list,
                "show": cmd_library_show,
                "rename": cmd_library_rename,
                "delete": cmd_library_delete}[args.lcmd](args)
    if args.cmd == "api-spec":
        return cmd_api_spec(args)
    if args.cmd == "daw-export":
        return cmd_daw_export(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
