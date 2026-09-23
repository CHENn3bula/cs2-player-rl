"""Validate the public replay/scenario boundary, not an ML feature schema."""
from __future__ import annotations

import math
from typing import Any

BOMB_STATES = {"carried", "dropped", "planted", "defused", "exploded", "unknown"}


class ValidationError(ValueError):
    pass


def _number(value: Any, name: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{name} must be a finite number")


def validate_frame(frame: dict, *, full_roster: bool = True) -> None:
    if not isinstance(frame, dict):
        raise ValidationError("frame must be an object")
    _number(frame.get("time"), "frame.time")
    if isinstance(frame.get("tick"), bool) or not isinstance(frame.get("tick"), int) or frame["tick"] < 0:
        raise ValidationError("frame.tick must be a nonnegative integer")
    _number(frame.get("round_time_remaining"), "round_time_remaining", nullable=True)
    players = frame.get("players")
    if not isinstance(players, list) or not players:
        raise ValidationError("frame.players must be a nonempty list")
    ids = set()
    teams = {"T": 0, "CT": 0}
    for p in players:
        if not isinstance(p.get("id"), str) or not p["id"] or p["id"] in ids:
            raise ValidationError("player ids must be distinct nonempty strings")
        ids.add(p["id"])
        if p.get("team") not in teams:
            raise ValidationError("player team must be T or CT")
        teams[p["team"]] += 1
        for field in ("x", "y", "z", "yaw"):
            _number(p.get(field), f"player.{field}")
        if isinstance(p.get("hp"), bool) or not isinstance(p.get("hp"), int) or not 0 <= p["hp"] <= 100:
            raise ValidationError("player hp must be an integer in [0,100]")
        if not isinstance(p.get("alive"), bool) or p["alive"] != (p["hp"] > 0):
            raise ValidationError("player alive and hp are inconsistent")
    if full_roster and teams != {"T": 5, "CT": 5}:
        raise ValidationError(f"expected five slots per team, got {teams}")
    bomb = frame.get("bomb", {})
    if bomb.get("state") not in BOMB_STATES:
        raise ValidationError("invalid bomb state")
    for field in ("x", "y", "z", "time_remaining"):
        _number(bomb.get(field), f"bomb.{field}", nullable=True)
    carrier = bomb.get("carrier_id")
    if carrier is not None and carrier not in ids:
        raise ValidationError("bomb carrier must refer to a player slot")
    if bomb.get("time_remaining") is not None and bomb["time_remaining"] < 0:
        raise ValidationError("bomb timer must be nonnegative")
    if bomb["state"] == "carried":
        player = next((p for p in players if p["id"] == carrier), None)
        if player is None or player["team"] != "T" or not player["alive"]:
            raise ValidationError("carried bomb must belong to a living T")


def validate_replay(replay: dict, *, full_roster: bool = True) -> dict:
    if replay.get("schema_version") != 1:
        raise ValidationError("unsupported replay schema_version")
    if replay.get("map") != "de_dust2" or replay.get("game") not in {"csgo", "cs2"}:
        raise ValidationError("expected an explicitly versioned Dust II replay")
    if not replay.get("match_id") or not replay.get("rounds"):
        raise ValidationError("match_id and nonempty rounds are required")
    frame_count = 0
    seen_rounds = set()
    for rnd in replay["rounds"]:
        if rnd["number"] in seen_rounds:
            raise ValidationError("duplicate round number")
        seen_rounds.add(rnd["number"])
        frames = rnd.get("frames", [])
        if not frames:
            raise ValidationError("round has no frames")
        previous = (-1, -math.inf)
        roster = None
        for frame in frames:
            validate_frame(frame, full_roster=full_roster)
            if frame["tick"] <= previous[0] or frame["time"] < previous[1]:
                raise ValidationError("frames must have increasing ticks and nondecreasing time")
            previous = (frame["tick"], frame["time"])
            this_roster = {(p["id"], p["team"]) for p in frame["players"]}
            if roster is not None and this_roster != roster:
                raise ValidationError("player slots changed within a round")
            roster = this_roster
            frame_count += 1
    return {"match_id": replay["match_id"], "rounds": len(seen_rounds), "frames": frame_count}
