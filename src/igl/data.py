"""Loss-aware ESTA/Awpy-1.x import. No learned policy or inferred IGL calls."""
from __future__ import annotations

import gzip
import hashlib
import json
import lzma
import math
from collections import Counter
from pathlib import Path
from typing import Any


def load_replay(path: str | Path) -> dict:
    """Read a canonical replay or source JSON, optionally gzip/xz compressed."""
    path = Path(path)
    opener = lzma.open if path.suffix == ".xz" else gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("replay must contain a JSON object")
    return value


def write_json(path: str | Path, value: Any, *, pretty: bool = False) -> Path:
    """Atomically write JSON; deterministic gzip has no timestamp or filename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False,
                      indent=2 if pretty else None, separators=None if pretty else (",", ":"))
    payload = text.encode("utf-8")
    if path.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return path


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clock_seconds(clock: str | None) -> float | None:
    if not isinstance(clock, str):
        return None
    try:
        minutes, seconds = clock.split(":")
        return float(60 * int(minutes) + int(seconds))
    except (ValueError, TypeError):
        return None


def _player(player: dict, side: str) -> dict:
    aliases = {"id": "steamID", "name": "name", "x": "x", "y": "y", "z": "z",
               "yaw": "viewX", "pitch": "viewY", "hp": "hp", "alive": "isAlive",
               "weapon": "activeWeapon", "armor": "armor", "helmet": "hasHelmet",
               "defuser": "hasDefuse", "bomb": "hasBomb", "inventory": "inventory",
               "blinded": "isBlinded", "airborne": "isAirborne", "ducking": "isDucking",
               "defusing": "isDefusing", "planting": "isPlanting", "reloading": "isReloading",
               "scoped": "isScoped", "walking": "isWalking", "cash": "cash",
               "team_name": "team", "equipment_value": "equipmentValue"}
    result = {key: player.get(original) for key, original in aliases.items()}
    result["id"] = str(result["id"]) if result["id"] is not None else ""
    result["team"] = side
    result["spotters"] = [str(x) for x in player.get("spotters", [])]
    result["velocity"] = {axis: player.get("velocity" + axis.upper()) for axis in ("x", "y", "z")}
    return result


def _bomb(frame: dict, players: list[dict], events: list[dict], tick_rate: float,
          plant_tick: int | None, server_timer: float | None) -> dict:
    tick = frame["tick"]
    carrier = next((p for p in players if p.get("bomb") and p.get("alive")), None)
    position = frame.get("bomb") or next((x for x in frame.get("world", [])
                                          if x.get("objectType") == "bomb"), {})
    happened = [e for e in events if e["tick"] <= tick and e["type"] in ("bomb_defuse", "bomb_explode")]
    if happened:
        state = "defused" if happened[-1]["type"] == "bomb_defuse" else "exploded"
    elif frame.get("bombPlanted"):
        state = "planted"
    elif carrier:
        state = "carried"
        position = carrier
    elif position:
        state = "dropped"
    else:
        state = "unknown"
    remaining = None
    basis = None
    if state == "planted":
        if server_timer and plant_tick is not None:
            remaining = max(0.0, server_timer - (tick - plant_tick) / tick_rate)
            basis = "server_cvar_and_reported_tick_rate"
        else:
            remaining = _clock_seconds(frame.get("clockTime"))
            basis = "source_display_clock_quantized_1s" if remaining is not None else None
    return {"state": state, **{axis: position.get(axis) for axis in ("x", "y", "z")},
            "carrier_id": carrier["id"] if state == "carried" else None,
            "time_remaining": remaining, "timer_basis": basis, "site": frame.get("bombsite") or None}


def normalize_esta(path: str | Path, source: dict | None = None) -> dict:
    """Convert ESTA JSON/.xz into schema v1 with continuous time since freeze end.

    Frames lacking a complete recorded 5v5 roster are excluded and counted.
    Outcomes and omniscient coordinates are replay data, never policy inputs.
    """
    raw = load_replay(path)
    if raw.get("mapName") != "de_dust2" or not isinstance(raw.get("gameRounds"), list):
        raise ValueError("expected an ESTA/Awpy-1.x de_dust2 JSON (not a .dem or CS2 replay)")
    rate = raw.get("tickRate")
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("source tickRate must be positive")
    provenance = dict(source or {})
    provenance.update({"format": "ESTA/Awpy-1.x", "demo_id": raw.get("demoId"),
                       "match_id": raw.get("matchId"), "event": raw.get("competitionName"),
                       "match_name": raw.get("matchName"), "match_url": raw.get("hltvUrl"),
                       "date": raw.get("matchDate"), "tick_rate": rate,
                       "parser": raw.get("parserParameters"), "server_vars": raw.get("serverVars"),
                       "raw_sha256": sha256(path)})
    first_round = next((rnd for rnd in raw["gameRounds"] if not rnd.get("isWarmup")), {})
    team_label = " vs ".join(str(first_round.get(key) or "Unknown team") for key in ("tTeam", "ctTeam"))
    provenance["label"] = team_label + " · " + str(raw.get("competitionName") or "Unknown event")
    counts: Counter = Counter()
    rounds = []
    for raw_round in raw["gameRounds"]:
        if raw_round.get("isWarmup"):
            counts["warmup_rounds"] += 1
            continue
        freeze_end = raw_round.get("freezeTimeEndTick")
        end = raw_round.get("endTick")
        if not isinstance(freeze_end, int) or not isinstance(end, int):
            raise ValueError("missing round boundary tick")
        events = []
        for collection, kind in (("kills", "kill"), ("damages", "damage"),
                                 ("weaponFires", "weapon_fire"), ("flashes", "flash"),
                                 ("bombEvents", "bomb"), ("grenades", "grenade_throw")):
            for event in raw_round.get(collection) or []:
                counts["source_events"] += 1
                tick = event.get("throwTick") if collection == "grenades" else event.get("tick")
                if tick is None:
                    counts["events_missing_tick"] += 1
                    continue
                if tick < freeze_end or tick > end:
                    counts["outside_round_events"] += 1
                    continue
                converted = dict(event)
                for key, value in list(converted.items()):
                    if key.endswith("SteamID") and value is not None:
                        converted[key] = str(value)
                converted.update({"type": "bomb_" + event["bombAction"] if kind == "bomb" else kind,
                                  "tick": tick, "time": (tick - freeze_end) / rate,
                                  "source_seconds": event.get("seconds", event.get("throwSeconds"))})
                events.append(converted)
        events.sort(key=lambda event: (event["tick"], event["type"]))
        frames = []
        last_tick = -1
        roster = None
        for frame in raw_round.get("frames") or []:
            counts["source_frames"] += 1
            tick = frame["tick"]
            if tick < freeze_end or tick > end:
                counts["outside_round_frames"] += 1
                continue
            players = [_player(p, side.upper()) for side in ("t", "ct")
                       for p in ((frame.get(side) or {}).get("players") or [])]
            teams = Counter(p["team"] for p in players)
            ids = {(p["id"], p["team"]) for p in players}
            if teams != {"T": 5, "CT": 5} or len(ids) != 10 or any(not p["id"] for p in players):
                counts["incomplete_roster_frames"] += 1
                continue
            if roster is not None and ids != roster:
                counts["changed_roster_frames"] += 1
                continue
            roster = ids
            if tick <= last_tick:
                raise ValueError(f"nonincreasing frame ticks in round {raw_round['roundNum']}")
            last_tick = tick
            bomb = _bomb(frame, players, events, rate, raw_round.get("bombPlantTick"),
                         (raw.get("serverVars") or {}).get("bombTimer"))
            frames.append({"tick": tick, "time": (tick - freeze_end) / rate,
                           "source_seconds": frame.get("seconds"), "source_clock_time": frame.get("clockTime"),
                           "players": players, "bomb": bomb,
                           "round_time_remaining": None if bomb["state"] in ("planted", "defused", "exploded")
                           else _clock_seconds(frame.get("clockTime")),
                           "round_timer_basis": "source_display_clock_quantized_1s",
                           "utility": {key: frame.get(key) for key in ("smokes", "fires", "projectiles")}})
        if not frames:
            counts["empty_rounds"] += 1
            continue
        rounds.append({"number": raw_round["roundNum"], "winner": raw_round.get("winningSide"),
                       "start_tick": raw_round.get("startTick"), "freeze_end_tick": freeze_end,
                       "end_tick": end, "plant_tick": raw_round.get("bombPlantTick"),
                       "end_reason": raw_round.get("roundEndReason"),
                       "teams": {"T": raw_round.get("tTeam"), "CT": raw_round.get("ctTeam")},
                       "score_start": {"T": raw_round.get("tScore"), "CT": raw_round.get("ctScore")},
                       "frames": frames, "events": events})
    provenance["normalization"] = {"version": 1, "counts": dict(counts),
                                    "continuous_time": "(tick - freezeTimeEndTick) / source.tickRate",
                                    "missing_player_policy": "exclude_frame; never impute dead or disconnected players"}
    return {"schema_version": 1, "match_id": str(raw.get("demoId") or Path(path).name.split(".")[0]),
            "map": "de_dust2", "game": "csgo", "source": provenance, "rounds": rounds,
            "limitations": ["Historical CS:GO geometry/rules, not current CS2.",
                            "Nominal 2 Hz snapshots; event ticks are finer resolution.",
                            "Source seconds reset at plant; canonical time uses reported tick rate (often 127).",
                            "Missing timer cvars: displayed clocks have one-second quantization.",
                            "Omniscient replay data; spotters do not reconstruct all team knowledge or sound.",
                            "No IGL voice calls, intended strategy labels, or exact engine snapshots."]}


def import_esta(source_path: str | Path, output_path: str | Path, provenance: dict | None = None) -> dict:
    from .schema import validate_replay
    replay = normalize_esta(source_path, provenance)
    validate_replay(replay)
    write_json(output_path, replay)
    return replay


def summarize_replay(replay: dict) -> dict:
    frames = [frame for rnd in replay["rounds"] for frame in rnd["frames"]]
    return {"match_id": replay["match_id"], "event": replay["source"].get("event"),
            "rounds": len(replay["rounds"]), "frames": len(frames),
            "events": sum(len(rnd["events"]) for rnd in replay["rounds"]),
            "postplant_frames": sum(f["bomb"]["state"] == "planted" for f in frames),
            "player_ids": sorted({p["id"] for f in frames for p in f["players"]}),
            "exclusions": replay["source"]["normalization"]["counts"]}


def build_scenario_index(replay: dict, split: str | None = None) -> list[dict]:
    """Index conservative candidate frames, not yet geometry-certified scenarios."""
    candidates = []
    for rnd in replay["rounds"]:
        selected = set()
        for index, frame in enumerate(rnd["frames"]):
            players = frame["players"]
            alive = {team: sum(p["alive"] for p in players if p["team"] == team) for team in ("T", "CT")}
            if not all(alive.values()) or len(players) != 10:
                continue
            if any(frame["utility"].get(key) is None or frame["utility"][key] for key in ("smokes", "fires", "projectiles")):
                continue
            if any(p.get(key) is not False for p in players if p["alive"]
                   for key in ("blinded", "airborne", "defusing", "planting", "reloading")):
                continue
            if frame["bomb"]["state"] == "planted" and (frame["bomb"]["time_remaining"] or 0) >= 12:
                kind = "postplant"
            elif frame["bomb"]["state"] in ("carried", "dropped") and frame["time"] >= 45:
                kind = "midround"
            else:
                continue
            if kind in selected:
                continue
            selected.add(kind)
            candidates.append({"match_id": replay["match_id"], "round": rnd["number"],
                               "frame_index": index, "tick": frame["tick"], "time": frame["time"],
                               "kind": kind, "alive": alive, "split": split,
                               "geometry_validated": False, "active_utility": False,
                               "bomb_timer_basis": frame["bomb"].get("timer_basis"),
                               "limitations": ["Inventory utility requires simulator support or explicit exclusion.",
                                               "Observations must be reconstructed without hidden enemy coordinates."]})
    return candidates
