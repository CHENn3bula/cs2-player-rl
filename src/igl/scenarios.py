"""Extract recorded starting states without copying their recorded future into a rollout."""
from __future__ import annotations

import copy
import hashlib
import json

from .schema import validate_frame


def extract_scenario(replay: dict, round_number: int, frame_index: int) -> dict:
    if replay.get("game") != "csgo" or replay.get("map") != "de_dust2":
        raise ValueError("The DECOY adapter currently accepts CS:GO Dust II only")
    rnd = next((r for r in replay["rounds"] if r["number"] == round_number), None)
    if rnd is None or not 0 <= frame_index < len(rnd["frames"]):
        raise ValueError("Round or frame does not exist")
    frame = copy.deepcopy(rnd["frames"][frame_index])
    validate_frame(frame)
    if not all(any(p["team"] == team and p["alive"] for p in frame["players"]) for team in ("T", "CT")):
        raise ValueError("A playable scenario needs at least one living player on each team")
    if frame["bomb"]["state"] in {"defused", "exploded", "unknown"}:
        raise ValueError("Cannot branch a terminal or unknown bomb state")
    fingerprint = hashlib.sha256(json.dumps(frame, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {
        "schema_version": 1, "kind": "scenario_snapshot", "map": replay["map"], "game": replay["game"],
        "match_id": replay["match_id"], "round_number": round_number, "frame_index": frame_index,
        "frame": frame, "source": copy.deepcopy(replay.get("source", {})), "frame_sha256": fingerprint,
        "limitations": [
            "Reconstructed from sampled demo state, not a complete Source engine snapshot.",
            "No future enemy positions, events, or recorded actions are included in this scenario.",
            "Bomb timer precision and missing equipment follow source-data limitations.",
        ],
    }
