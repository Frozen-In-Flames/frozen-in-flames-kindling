"""Data browser (Part 4.4).

An internal tool to search by any label, inspect label confidences, and flag
failures. Usable as a library and as a CLI:

    python -m kindling.data.browser --ledger <dir> search source=demo
    python -m kindling.data.browser --ledger <dir> show rec_abc123
    python -m kindling.data.browser --ledger <dir> report rec_abc123 --audio song.wav --out report.html

The HTML report embeds an audio player with the aligned lyrics and section
markers beside it, so a researcher can hear what the labels claim.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from typing import Any, Dict, List

from kindling.data.pipeline import Pipeline


def _load_ledger(ledger_dir: str) -> Pipeline:
    pipeline = Pipeline(ledger_dir)
    return pipeline


def search(pipeline: Pipeline, **filters: str) -> List[Dict[str, Any]]:
    """Search records by top-level fields or label values.

    Filters look like source=demo, split=train, label.key=C major.
    """
    results = []
    for record in pipeline.all_records():
        ok = True
        for key, want in filters.items():
            if key.startswith("label."):
                lab = record.get("labels", {}).get(key[6:], {})
                got = lab.get("value") if isinstance(lab, dict) else None
            else:
                got = record.get(key)
                if isinstance(got, dict):
                    got = got.get("name", got)
            if str(got) != str(want):
                ok = False
                break
        if ok:
            results.append(record)
    return results


def failure_flags(record: Dict[str, Any]) -> List[str]:
    """Checks a researcher would run weekly: missing labels, low confidence,
    silence, no transcript, deleted."""
    flags = list(record.get("flags", []))
    for name, lab in record.get("labels", {}).items():
        if isinstance(lab, dict) and lab.get("confidence", 0.0) < 0.35:
            flags.append(f"low-confidence:{name}")
    return sorted(set(flags))


def show(pipeline: Pipeline, record_id: str) -> Dict[str, Any]:
    record = pipeline.record(record_id)
    return {
        "record_id": record["record_id"],
        "content_hash": record["content_hash"],
        "source": record["source"],
        "license": record["license"],
        "allowed_uses": record["allowed_uses"],
        "split": record["split"],
        "deleted": record["deleted"],
        "quality_score": record["quality_score"],
        "labels": {k: {"value": _short(v.get("value")),
                       "confidence": v.get("confidence"),
                       "method": v.get("method")}
                   for k, v in record.get("labels", {}).items()
                   if isinstance(v, dict)},
        "failure_flags": failure_flags(record),
    }


def _short(value: Any, limit: int = 120) -> Any:
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "..."


def html_report(pipeline: Pipeline, record_id: str, audio_src: str,
                out_path: str) -> str:
    record = pipeline.record(record_id)
    labels = record.get("labels", {})
    rows = []
    for name, lab in labels.items():
        if not isinstance(lab, dict):
            continue
        rows.append(
            f"<tr><td>{html.escape(name)}</td>"
            f"<td>{html.escape(_short(lab.get('value'), 200))}</td>"
            f"<td>{lab.get('confidence')}</td>"
            f"<td>{html.escape(str(lab.get('method')))}</td></tr>")
    sections = (labels.get("sections", {}) or {}).get("value") or []
    section_items = "".join(
        f"<li>{html.escape(s.get('id', '?'))}: {s.get('start_s')}s to {s.get('end_s')}s</li>"
        for s in sections if isinstance(s, dict))
    alignment = (labels.get("lyric_alignment", {}) or {}).get("value") or []
    lyric_items = "".join(
        f"<li>{html.escape(str(a.get('syllable')))} at {a.get('time_s')}s "
        f"({a.get('status')})</li>"
        for a in alignment if isinstance(a, dict))
    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Data record {html.escape(record_id)}</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:2em auto}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}.low{{color:#a00}}</style>
</head><body>
<h1>Data record {html.escape(record_id)}</h1>
<p>Source: {html.escape(str(record['source'].get('name')))} | Split: {record['split']} | License: {record['license']['status']} | Quality: {record['quality_score']}</p>
<audio controls src="{html.escape(audio_src)}"></audio>
<h2>Labels</h2>
<table><tr><th>Label</th><th>Value</th><th>Confidence</th><th>Method</th></tr>
{''.join(rows)}</table>
<h2>Sections</h2><ul>{section_items or '<li>none</li>'}</ul>
<h2>Lyric alignment</h2><ul>{lyric_items or '<li>none</li>'}</ul>
<h2>Failure flags</h2><ul>{''.join(f'<li class="low">{html.escape(f)}</li>' for f in failure_flags(record)) or '<li>none</li>'}</ul>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kindling.data.browser",
                                     description="Kindling data browser (Part 4.4)")
    parser.add_argument("--ledger", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    p_search = sub.add_parser("search")
    p_search.add_argument("filters", nargs="*")
    p_show = sub.add_parser("show")
    p_show.add_argument("record_id")
    p_report = sub.add_parser("report")
    p_report.add_argument("record_id")
    p_report.add_argument("--audio", required=True)
    p_report.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    pipeline = _load_ledger(args.ledger)
    if args.command == "search":
        filters = dict(f.split("=", 1) for f in args.filters)
        for record in search(pipeline, **filters):
            print(f"{record['record_id']}  split={record['split']}  "
                  f"license={record['license']['status']}  quality={record['quality_score']}")
    elif args.command == "show":
        print(json.dumps(show(pipeline, args.record_id), indent=2, sort_keys=True))
    elif args.command == "report":
        print(html_report(pipeline, args.record_id, args.audio, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
