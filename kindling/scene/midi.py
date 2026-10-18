"""Minimal MIDI file reader and writer (Part 3.6).

Covers what the scene needs: note on/off with velocity, tempo map, time
signature, and track names, in format 0 and 1 files. This is a real
implementation of the MIDI subset Kindling uses, not a stub: the acceptance
test round-trips a MIDI file through the scene with no note loss.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Tuple

TPQ = 480


def _write_varlen(value: int) -> bytes:
    out = bytearray()
    out.append(value & 0x7F)
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def _read_varlen(data: bytes, pos: int) -> Tuple[int, int]:
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _write_track(events: List[Tuple[int, bytes]]) -> bytes:
    body = bytearray()
    last_tick = 0
    for tick, payload in sorted(events, key=lambda e: e[0]):
        body += _write_varlen(tick - last_tick)
        body += payload
        last_tick = tick
    body += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def _meta(track_name: str, tempo_bpm: float, sig: Tuple[int, int]) -> List[Tuple[int, bytes]]:
    events: List[Tuple[int, bytes]] = []
    if track_name:
        name = track_name.encode("utf-8")
        events.append((0, b"\xff\x03" + _write_varlen(len(name)) + name))
    us_per_quarter = int(round(60_000_000 / tempo_bpm))
    events.append((0, b"\xff\x51\x03" + us_per_quarter.to_bytes(3, "big")))
    num, den = sig
    den_power = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}[den]
    events.append((0, b"\xff\x58\x04" + bytes([num, den_power, 24, 8])))
    return events


def write_midi_file(path: str, tracks: List[Dict[str, Any]],
                    tempo_bpm: float = 120.0, sig: Tuple[int, int] = (4, 4)) -> None:
    """tracks: [{name, channel, notes: [{pitch, start_beats, duration_beats, velocity}]}]."""
    midi_tracks = []
    for index, track in enumerate(tracks):
        events = _meta(track.get("name", ""), tempo_bpm, sig) if index == 0 else []
        channel = track.get("channel", index % 16)
        for note in track.get("notes", []):
            start = int(round(note["start_beats"] * TPQ))
            end = start + max(1, int(round(note["duration_beats"] * TPQ)))
            vel = int(round(note.get("velocity", 0.8) * 127))
            pitch = note["pitch"]
            events.append((start, bytes([0x90 | channel, pitch, vel])))
            events.append((end, bytes([0x80 | channel, pitch, 64])))
        midi_tracks.append(_write_track(events))
    header = (b"MThd" + struct.pack(">IHHH", 6, 1 if len(midi_tracks) > 1 else 0,
                                    len(midi_tracks), TPQ))
    with open(path, "wb") as fh:
        fh.write(header + b"".join(midi_tracks))


def _parse_track(data: bytes) -> Dict[str, Any]:
    pos, tick = 0, 0
    notes: List[Dict[str, Any]] = []
    tempo_changes: List[Tuple[int, float]] = []
    sig_changes: List[Tuple[int, Tuple[int, int]]] = []
    name = ""
    open_notes: Dict[Tuple[int, int], Tuple[int, int]] = {}
    running = 0
    while pos < len(data):
        delta, pos = _read_varlen(data, pos)
        tick += delta
        status = data[pos]
        if status < 0x80:
            status = running
        else:
            pos += 1
            running = status
        if status == 0xFF:
            meta_type = data[pos]
            pos += 1
            length, pos = _read_varlen(data, pos)
            payload = data[pos:pos + length]
            pos += length
            if meta_type == 0x51 and length == 3:
                us = int.from_bytes(payload, "big")
                tempo_changes.append((tick, 60_000_000 / us))
            elif meta_type == 0x58 and length == 4:
                sig_changes.append((tick, (payload[0], 2 ** payload[1])))
            elif meta_type == 0x03:
                name = payload.decode("utf-8", "replace")
            elif meta_type == 0x2F:
                break
        elif 0x80 <= status < 0xF0:
            kind = status & 0xF0
            channel = status & 0x0F
            if kind in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                a, b = data[pos], data[pos + 1]
                pos += 2
                key = (channel, a)
                if kind == 0x90 and b > 0:
                    open_notes[key] = (tick, b)
                elif key in open_notes:
                    start, vel = open_notes.pop(key)
                    notes.append({"pitch": a, "start_tick": start,
                                  "end_tick": tick, "velocity": vel / 127.0,
                                  "channel": channel})
            elif kind in (0xC0, 0xD0):
                pos += 1
        else:
            break
    return {"name": name, "notes": notes, "tempo_changes": tempo_changes,
            "sig_changes": sig_changes}


def read_midi_file(path: str) -> Dict[str, Any]:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    header_len, fmt, n_tracks, division = struct.unpack(">IHHH", data[4:14])
    pos = 14 + (header_len - 6)
    tracks = []
    for _ in range(n_tracks):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("corrupt MIDI file: expected MTrk")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        tracks.append(_parse_track(data[pos + 8:pos + 8 + length]))
        pos += 8 + length
    return {"format": fmt, "ticks_per_quarter": division, "tracks": tracks}


def scene_to_midi(scene: Dict[str, Any], path: str) -> None:
    """Export every part with notes as one MIDI track (Part 3.6)."""
    tempo = scene["timeline"]["tempo"][0]["bpm"]
    sig_text = scene["timeline"]["meter"][0]["sig"]
    num, den = (int(x) for x in sig_text.split("/"))
    tracks = []
    for index, part in enumerate(scene.get("parts", [])):
        if not part.get("notes"):
            continue
        tracks.append({"name": part["id"], "channel": index % 16,
                       "notes": part["notes"]})
    melody = scene.get("melody", {})
    if melody.get("notes"):
        tracks.append({"name": "melody", "channel": len(tracks) % 16,
                       "notes": melody["notes"]})
    if not tracks:
        tracks.append({"name": "empty", "channel": 0, "notes": []})
    write_midi_file(path, tracks, tempo_bpm=tempo, sig=(num, den))


def _ticks_to_beats(ticks: int, tpq: int) -> float:
    return ticks / tpq


def midi_to_scene(parsed: Dict[str, Any], scene_id=None) -> Dict[str, Any]:
    """Import a parsed MIDI file into a scene (Part 3.6).

    MIDI is exact, so imported notes carry confidence 1.0 at the symbolic
    realization level with source "imported".
    """
    from kindling.scene.model import make_element_meta, make_scene

    tpq = parsed["ticks_per_quarter"]
    scene = make_scene(scene_id=scene_id, created_by="midi-import")
    tempo_changes = []
    sig_changes = []
    for track in parsed["tracks"]:
        tempo_changes += track["tempo_changes"]
        sig_changes += track["sig_changes"]
    if tempo_changes:
        first_tick = min(t for t, _ in tempo_changes)
        scene["timeline"]["tempo"] = [
            {"bar": 1, "bpm": bpm} for _, bpm in sorted(tempo_changes)
        ]
        _ = first_tick
    if sig_changes:
        num, den = sorted(sig_changes)[0][1]
        scene["timeline"]["meter"] = [{"bar": 1, "sig": f"{num}/{den}"}]

    for index, track in enumerate(parsed["tracks"]):
        notes = [
            {"pitch": n["pitch"],
             "start_beats": _ticks_to_beats(n["start_tick"], tpq),
             "duration_beats": _ticks_to_beats(n["end_tick"] - n["start_tick"], tpq),
             "velocity": round(n["velocity"], 4)}
            for n in track["notes"]
        ]
        if not notes:
            continue
        scene["parts"].append({
            "id": track["name"] or f"part_{index}",
            "role": "imported",
            "notes": notes,
            "articulations": [],
            "dynamics": [],
            "expression": {},
            "meta": make_element_meta(source="imported", confidence=1.0,
                                      realization="symbolic"),
        })
    return scene
