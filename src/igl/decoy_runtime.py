"""Headless commander adapter around the real, pinned DECOY Panda3D engine.

This is infrastructure, not an RL policy or CS2 engine replica. Its canonical
frames are privileged replay state. Use team_observation() for policy input.
One engine per process (Panda3D ShowBase is a singleton).
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
REVISION = "6f93b8efe5a778384ccd284c31b2141b6b0ce5da"
SCALE = 0.01905
LIMITATIONS = [
    "CS:GO Dust II geometry, not the current CS2 engine/map; external map version is not specified upstream.",
    "Combat uses unchanged pretrained DECOY inference; it has not been calibrated for CS2 or professional tactical evaluation.",
    "No smoke, flash, HE, incendiary, sound, penetration, ammunition, reload, crouch, economy or movement inertia model.",
    "Waypoint movement uses fixed knife speed (250 Hammer units/s); equipment is descriptive except supported weapon/armor combat features.",
    "Plant/defuse are explicit stationary timed approximations (3.2 s / 10 s or 5 s with kit); use radius and bombsites are approximate.",
    "Scenario restore snaps to the nearest 3D waypoint and starts with zero velocity; unsupported state is rejected unless explicitly permitted.",
    "Canonical replay frames contain privileged state. Team observations use approximate horizontal FOV plus Bullet raycasts and no sound.",
    "Scripted smoke/branch baseline routes using privileged bomb state; it is a systems test, not a fair tactical opponent or evaluation benchmark.",
    "Combat damage at each 0.5-second model boundary is resolved simultaneously among the players alive at that boundary.",
    "Simultaneous kill credit goes to the largest predicted damage contributor (external player ID breaks ties); this is reporting attribution, not a change to combat.",
]


def to_engine(x, y, z):
    return (float(x) * SCALE, float(y) * SCALE, float(z) * SCALE + 3.1)


def to_world(position):
    return (float(position[0]) / SCALE, float(position[1]) / SCALE, (float(position[2]) - 3.1) / SCALE)


def _round(value):
    return round(float(value), 5)


class DecoyRuntime:
    """Synchronous two-team commander API, backed by DECOY map and physics."""

    def __init__(self, *, seed=42, combat=True, round_seconds=115, repo=None):
        self.repo = Path(repo or ROOT / "vendor/decoy").resolve()
        map_path = self.repo / "env/assets/de_dust_2.fbx"
        if not map_path.is_file():
            raise FileNotFoundError("Missing DECOY map. Run Python 3.12 scripts/setup_decoy.py --install first.")
        sys.path.insert(0, str(self.repo))
        # On Windows, loading Panda3D first can make torch's c10.dll fail.
        import torch
        torch.set_num_threads(1)
        import numpy as np
        from panda3d.core import Vec3, Filename, loadPrcFileData
        from env import config
        assets = {"MAP_PATH": "env/assets/de_dust_2.fbx", "WAYPOINT_DATA_PATH": "env/assets/WaypointDust2Verified_p3d_clean_verified.json",
                  "AGENT_MODEL_PATH": "env/assets/agent.glb", "MINIMAP_IMAGE_PATH": "env/assets/de_dust2.png",
                  "MINIMAP_DOT_TEXTURE_PATH": "env/assets/white_dot.png",
                  "DAMAGE_INDICATOR_PREDICTOR_MODEL_PATH": "models/train-di_20250328-183510_y5vpxd",
                  "DAMAGE_OUTCOME_GENERATOR_MODEL_PATH": "models/train-vae_20250321-040316_upf4hz"}
        for name, relative in assets.items():
            path = self.repo / relative
            if name in {"MAP_PATH", "AGENT_MODEL_PATH", "MINIMAP_IMAGE_PATH", "MINIMAP_DOT_TEXTURE_PATH"}:
                value = Filename.fromOsSpecific(str(path)).getFullpath()
            else:
                value = str(path)
            setattr(config, name, value)
        config.ENABLE_LOGGING = False
        # Automatic plant/defuse is replaced below with explicit timed commands.
        config.ENABLE_BOMB_ACTIONS = False
        config.ENABLE_AGENT_SHOOTING = True
        loadPrcFileData("", "notify-level-device fatal\nnotify-level-assimp error\nnotify-level-loader error")
        from env.game_engine import CSGOEngine
        from env.utils import BombStatus, Team, Weapon, Region
        self.torch, self.np, self.Vec3 = torch, np, Vec3
        self.BombStatus, self.Team, self.Weapon, self.Region = BombStatus, Team, Weapon, Region
        self.engine = CSGOEngine(5, render_mode=None)
        self.engine.enable_logging = False
        self.combat = combat
        self.round_seconds = float(round_seconds)
        self.seed = seed
        self.reset(seed=seed)

    def reset(self, *, seed=None, options=None):
        seed = self.seed if seed is None else int(seed)
        self.seed = seed
        random.seed(seed)
        self.np.random.seed(seed)
        self.torch.manual_seed(seed)
        self.rng = random.Random(seed)
        self.engine.game_time_limit = self.round_seconds
        self.engine.reset(options)
        self.engine.agent_action_request_queue.clear()
        self.engine.termination_queue.clear()
        self.routes = {k: deque() for k in self.engine.agents}
        self.edge_targets = {k: None for k in self.engine.agents}
        self.orders = {k: {"type": "hold"} for k in self.engine.agents}
        self.names = {k: k for k in self.engine.agents}
        self.external_ids = {k: k for k in self.engine.agents}
        self.kits = {k: False for k in self.engine.agents}
        self.armor = {k: 0 for k in self.engine.agents}
        self.descriptive_weapons = {}
        self.last_seen = {"T": {}, "CT": {}}
        self.bomb_progress = {}
        self.events = []
        self.restore_report = {"snaps": [], "warnings": []}
        self.source_time = 0.0
        self.damage_queries = 0
        self.damage_events = 0
        self.stall_ticks = {k: 0 for k in self.engine.agents}
        self.stalled = set()
        for agent in self.engine.agents.values():
            self._hold(agent)
        return self.frame()

    def _hold(self, agent):
        agent.target_pos = agent.current_waypoint["pos"]
        agent.target_waypoint = agent.current_waypoint
        agent.is_stopping = False
        # Prevent upstream's 0.5-second stuck teleport; stalls are reported.
        agent.prev_decision_tick = None
        if agent.is_alive:
            agent.node_path.node().setLinearMovement(self.Vec3(0, 0, 0), True)

    def close(self):
        self.engine.destroy()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _slot(self, agent_id):
        if agent_id in self.engine.agents:
            return agent_id
        for slot, external in self.external_ids.items():
            if agent_id == external:
                return slot
        raise ValueError(f"Unknown agent {agent_id}")

    def command(self, orders, *, team=None):
        """Issue hold/move/plant/defuse orders; move accepts waypoint or world xyz.

        `team` enforces ownership for an IGL. Omitted players retain orders.
        hold/plant/defuse accept optional finite `yaw` degrees, normalized to
        [0,360). Repeating a pending plant/defuse preserves its progress; hold
        or move cancels it. Call step(seconds) afterwards. Commands do not
        advance time or position.
        """
        staged = []
        for key, order in orders.items():
            slot = self._slot(key)
            agent = self.engine.agents[slot]
            if team is not None and agent.team.name != team:
                raise ValueError(f"{team} commander cannot control {slot}")
            kind = order.get("type", "hold")
            if kind not in {"hold", "move", "plant", "defuse"}:
                raise ValueError(f"Unsupported order {kind!r}; utility is not implemented")
            if not agent.is_alive:
                raise ValueError(f"Cannot command dead agent {slot}")
            route = []
            normalized = dict(order)
            if "yaw" in order:
                yaw = order["yaw"]
                if kind == "move":
                    raise ValueError("Move facing follows the route; yaw is supported for hold/plant/defuse")
                if isinstance(yaw, bool) or not isinstance(yaw, (int, float)) or not math.isfinite(yaw):
                    raise ValueError("yaw must be a finite number in degrees")
                normalized["yaw"] = float(yaw) % 360.0
            if kind == "move":
                target = order.get("waypoint")
                if target is None:
                    target = self.engine.waypoints.get_nearest_waypoint(self.Vec3(*to_engine(order["x"], order["y"], order["z"])), return_id=True)
                target = int(target)
                start = agent.current_waypoint["id"]
                try:
                    away_from_start = (agent.position.xy - agent.current_waypoint["pos"].xy).length() >= 0.13
                    edge_target = self.edge_targets[slot]
                    if away_from_start and edge_target is not None:
                        # Finish the current directed edge before replanning, except
                        # a return to its start when that edge is legally reversible.
                        reversible = self.engine.waypoints.graph.has_edge(edge_target, start)
                        anchor = start if target == start and reversible else edge_target
                        route = [anchor] + self.engine.waypoints.find_path(anchor, target)[1:]
                    elif away_from_start:
                        route = [start] + self.engine.waypoints.find_path(start, target)[1:]
                    else:
                        route = self.engine.waypoints.find_path(start, target)[1:]
                except Exception as exc:
                    raise ValueError(f"No legal route from {start} to {target}") from exc
                normalized["waypoint"] = target
            if kind == "plant" and (not agent.is_t or not agent.has_bomb or not agent.is_at_bomb_site):
                raise ValueError("Plant requires the living T bomb carrier on a bombsite")
            if kind == "defuse" and (not agent.is_ct or not self.engine.bomb_has_planted or not agent.is_near_bomb):
                raise ValueError("Defuse requires a CT within the bomb use radius")
            staged.append((slot, normalized, route))
        for slot, order, route in staged:
            continuing_bomb_action = order["type"] in {"plant", "defuse"} and self.orders[slot]["type"] == order["type"]
            self.orders[slot] = order
            self.routes[slot] = deque(route)
            if not continuing_bomb_action:
                self.bomb_progress.pop(slot, None)
            self._hold(self.engine.agents[slot])
            if "yaw" in order:
                self.engine.agents[slot].view_angle = order["yaw"]
            self.stall_ticks[slot] = 0

    def _move(self, slot, agent):
        route = self.routes[slot]
        if not route:
            self._hold(agent)
            return
        target = self.engine.waypoints.get_waypoint_by_id(route[0])
        distance = (agent.position.xy - target["pos"].xy).length()
        if distance < 0.13:
            agent.current_waypoint = target
            self.edge_targets[slot] = None
            route.popleft()
            if not route:
                self._hold(agent)
                return
            target = self.engine.waypoints.get_waypoint_by_id(route[0])
        agent.target_waypoint = target
        self.edge_targets[slot] = target["id"]
        agent.target_pos = target["pos"]
        agent.prev_decision_tick = None
        delta = target["pos"] - agent.position
        agent.view_angle = math.degrees(math.atan2(delta.y, delta.x)) % 360
        old = self.Vec3(agent.position)
        agent.update_movement()
        # Compare movement on the previous physics step, not immediately after order.
        previous = getattr(agent, "_adapter_previous", old)
        self.stall_ticks[slot] = self.stall_ticks[slot] + 1 if (old - previous).length() < 0.001 else 0
        agent._adapter_previous = old
        if self.stall_ticks[slot] > 120:
            self.stalled.add(slot)

    def _bomb_tick(self):
        dt = self.engine.physics_step
        # Recovering the dropped bomb is automatic when a T walks near it.
        if self.engine.bomb_status == self.BombStatus.Dropped:
            for agent in self.engine.alive_t_agents:
                if agent.is_near_bomb:
                    self.engine.bomb_carrier = agent.agent_id
                    self.engine.bomb_world_position = None
                    self.engine.bomb_status = self.BombStatus.Carried
                    break
        for slot, agent in self.engine.agents.items():
            kind = self.orders[slot]["type"]
            valid = agent.is_alive and ((kind == "plant" and agent.is_t and agent.has_bomb and agent.is_at_bomb_site)
                                       or (kind == "defuse" and agent.is_ct and self.engine.bomb_has_planted and agent.is_near_bomb))
            if not valid:
                self.bomb_progress.pop(slot, None)
                continue
            self.bomb_progress[slot] = self.bomb_progress.get(slot, 0.0) + dt
            required = 3.2 if kind == "plant" else (5.0 if self.kits[slot] else 10.0)
            if self.bomb_progress[slot] + 1e-8 >= required:
                if kind == "plant":
                    self.engine.plant_bomb(agent.current_waypoint["id"])
                else:
                    self.engine.defuse_bomb()
                self.events.append({"type": "bomb_" + ("planted" if kind == "plant" else "defused"), "tick": self.engine.physics_ticks, "time": _round(self.engine.game_time), "player_id": self.external_ids[slot]})
                self.orders[slot] = {"type": "hold"}
                self.bomb_progress.pop(slot, None)

    def _check_end(self):
        from env.utils import WinReason
        e = self.engine
        if e.time_remaining <= 1e-8:
            e.game_timeout_flag = True
            if e.bomb_has_planted:
                e.bomb_status = self.BombStatus.Detonated
                self.events.append({"type": "bomb_explode", "tick": e.physics_ticks, "time": _round(e.game_time)})
        if e.bomb_status == self.BombStatus.Detonated:
            e.winning_team, e.winning_reason = self.Team.T, WinReason.BombDetonated
        elif e.bomb_status == self.BombStatus.Defused:
            e.winning_team, e.winning_reason = self.Team.CT, WinReason.BombDefused
        elif e.num_alive_ct == 0:
            e.winning_team, e.winning_reason = self.Team.T, WinReason.CounterTerroristEliminated
        elif e.num_alive_t == 0 and not e.bomb_has_planted:
            e.winning_team, e.winning_reason = self.Team.CT, WinReason.TerroristEliminated
        elif e.game_timeout_flag:
            e.winning_team, e.winning_reason = self.Team.CT, WinReason.TimeOut

    def step(self, seconds=0.25):
        if not math.isfinite(seconds) or seconds < 0 or seconds > 120:
            raise ValueError("step seconds must be finite and within [0,120]")
        ticks = max(0, int(round(seconds / self.engine.physics_step)))
        for _ in range(ticks):
            if self.engine.game_ended:
                break
            for slot, agent in self.engine.agents.items():
                if not agent.is_alive:
                    continue
                if self.orders[slot]["type"] == "move":
                    self._move(slot, agent)
                else:
                    self._hold(agent)
            if self.combat and self.engine.physics_ticks % 30 == 0:
                cohort = [agent for agent in self.engine.agents.values() if agent.is_alive]
                boundary_health = {agent.agent_id: agent.health for agent in cohort}
                pending_damage = {agent.agent_id: 0.0 for agent in cohort}
                contributions = {agent.agent_id: [] for agent in cohort}
                for attacker in list(self.engine.agents.values()):
                    if not attacker.is_alive:
                        continue
                    for victim in list(self.engine.agents.values()):
                        if victim.is_alive and victim.team != attacker.team and attacker.has_line_of_sight_to_agent(victim):
                            self.damage_queries += 1
                            will_damage, damage, _ = self.engine.damage_model.predict_damage(
                                attacker.position, victim.position, attacker.view_angle, victim.view_angle,
                                boundary_health[attacker.agent_id], attacker.weapon.value, victim.has_armor, victim.has_helmet)
                            if will_damage and damage is not None:
                                if not math.isfinite(damage):
                                    raise RuntimeError("DECOY damage predictor produced a non-finite value")
                                damage = max(0.0, damage)
                                pending_damage[victim.agent_id] += damage
                            if will_damage and damage is not None and damage > 0:
                                self.damage_events += 1
                                contributions[victim.agent_id].append((attacker.agent_id, damage))
                for agent in cohort:
                    agent.health = boundary_health[agent.agent_id] - pending_damage[agent.agent_id]
                    contributors = contributions[agent.agent_id]
                    actual_health_lost = min(boundary_health[agent.agent_id], pending_damage[agent.agent_id])
                    for attacker_id, predicted_damage in contributors:
                        attacker = self.engine.agents[attacker_id]
                        self.events.append({
                            "type": "damage", "tick": self.engine.physics_ticks, "time": _round(self.engine.game_time),
                            "attacker_id": self.external_ids[attacker_id], "attacker_name": self.names[attacker_id],
                            "victim_id": self.external_ids[agent.agent_id], "victim_name": self.names[agent.agent_id],
                            "weapon": attacker.weapon.name, "damage": predicted_damage,
                            "damage_health": actual_health_lost * predicted_damage / pending_damage[agent.agent_id],
                            "victim_health_before": boundary_health[agent.agent_id], "victim_health_after": max(0.0, agent.health),
                            "resolution": "simultaneous", "health_attribution": "proportional_to_predicted_damage",
                        })
                    if agent.health <= 0 and contributors:
                        attacker_id, _ = min(contributors, key=lambda pair: (-pair[1], self.external_ids[pair[0]]))
                        self.events.append({
                            "type": "kill", "tick": self.engine.physics_ticks, "time": _round(self.engine.game_time),
                            "attacker_id": self.external_ids[attacker_id], "attacker_name": self.names[attacker_id],
                            "victim_id": self.external_ids[agent.agent_id], "victim_name": self.names[agent.agent_id],
                            "weapon": self.engine.agents[attacker_id].weapon.name,
                            "attribution": "largest_boundary_damage_then_external_id",
                            "contributors": [{"attacker_id": self.external_ids[key], "damage": amount} for key, amount in contributors],
                        })
                for agent in list(self.engine.agents.values()):
                    if agent.is_alive and agent.health <= 0:
                        agent.handle_death()
            self.engine.process_physics_step()
            self._bomb_tick()
            self._check_end()
            self.engine.termination_queue.clear()
        return self.frame()

    def frame(self):
        players = []
        for slot, agent in self.engine.agents.items():
            x, y, z = map(_round, to_world(agent.position))
            players.append({"id": self.external_ids[slot], "slot": slot, "name": self.names[slot], "team": agent.team.name,
                            "x": x, "y": y, "z": z, "yaw": _round(agent.view_angle), "hp": int(math.ceil(agent.display_health)),
                            "alive": bool(agent.is_alive), "weapon": self.descriptive_weapons.get(slot, agent.weapon.name), "armor": self.armor[slot],
                            "helmet": bool(agent.has_helmet), "defuser": self.kits[slot], "bomb": bool(agent.has_bomb),
                            "waypoint": agent.current_waypoint["id"], "order": self.orders[slot]})
        x, y, z = map(_round, to_world(self.engine.current_bomb_position))
        statuses = {"Carried": "carried", "Dropped": "dropped", "Planted": "planted", "Defused": "defused", "Detonated": "exploded"}
        bomb = {"state": statuses[self.engine.bomb_status.name], "x": x, "y": y, "z": z,
                "carrier_id": self.external_ids.get(self.engine.bomb_carrier),
                "time_remaining": _round(max(0, self.engine.time_remaining)) if self.engine.bomb_has_planted else None}
        remaining_round = None if self.engine.bomb_status in {self.BombStatus.Planted, self.BombStatus.Defused, self.BombStatus.Detonated} else _round(max(0, self.engine.time_remaining))
        return {"tick": self.engine.physics_ticks, "time": _round(self.engine.game_time), "players": players,
                "bomb": bomb, "round_time_remaining": remaining_round,
                "utility": {"smokes": [], "fires": [], "projectiles": []},
                "winner": self.engine.winning_team.name if self.engine.winning_team else None,
                "end_reason": self.engine.winning_reason.name if self.engine.winning_reason else None}

    def team_observation(self, team, *, fov=100.0):
        if team not in {"T", "CT"}:
            raise ValueError("team must be T or CT")
        frame = self.frame()
        visible = set()
        for friendly in self.engine.agents.values():
            if friendly.team.name != team or not friendly.is_alive:
                continue
            for enemy in self.engine.agents.values():
                if enemy.team.name == team or not enemy.is_alive:
                    continue
                delta = enemy.position - friendly.position
                bearing = math.degrees(math.atan2(delta.y, delta.x))
                angle = abs((bearing - friendly.view_angle + 180) % 360 - 180)
                if angle <= fov / 2 and friendly.has_line_of_sight_to_agent(enemy):
                    visible.add(self.external_ids[enemy.agent_id])
        enemies = []
        for player in frame["players"]:
            if player["id"] in visible:
                # Enemy private health, armor, kit, command and equipment are not exposed.
                observed = {key: player[key] for key in ["id", "team", "x", "y", "z", "yaw", "alive"]}
                self.last_seen[team][player["id"]] = {**observed, "last_seen_time": frame["time"]}
                enemies.append(observed)
        carrier = frame["bomb"]["carrier_id"]
        friendly_ids = {p["id"] for p in frame["players"] if p["team"] == team}
        known_bomb = carrier in friendly_ids
        if frame["bomb"]["state"] in {"planted", "defused", "exploded"}:
            # Global event/time is known, precise plant location requires observation.
            bomb = {"state": frame["bomb"]["state"], "time_remaining": frame["bomb"]["time_remaining"]}
        else:
            bomb = frame["bomb"] if known_bomb else {"state": "unknown"}
        return {"team": team, "time": frame["time"], "round_time_remaining": frame["round_time_remaining"],
                "friends": [p for p in frame["players"] if p["team"] == team], "visible_enemies": enemies,
                "last_seen_enemies": list(self.last_seen[team].values()), "bomb": bomb}

    def restore(self, scenario, *, seed=None, max_snap_units=128, allow_approximate=False):
        from .schema import validate_frame
        if scenario.get("map") not in {"de_dust2", "dust2", "Dust II"}:
            raise ValueError("DECOY backend supports Dust II only")
        frame = scenario.get("frame", scenario)
        validate_frame(frame)
        players = frame["players"]
        if len(players) != 10 or any(sum(p["team"] == t for p in players) != 5 for t in ["T", "CT"]):
            raise ValueError("Scenario must contain exactly five player slots per team, including dead slots")
        warnings = []
        if scenario.get("game") not in {"csgo", "CSGO", "CS:GO", "decoy"}:
            warnings.append("Source game is not CS:GO: geometry/rules compatibility is unverified")
        for field in ["utility", "smokes", "infernos", "grenades", "active_utility"]:
            value = frame.get(field)
            if field == "utility" and (not isinstance(value, dict) or any(not isinstance(value.get(key), list) for key in ["smokes", "fires", "projectiles"])):
                warnings.append("Active utility is unknown; absence cannot be established")
            if (any(value.values()) if isinstance(value, dict) else bool(value)):
                warnings.append(f"Unsupported active {field} would be discarded")
        if any(float(p.get("flash_duration", 0) or 0) > 0 or p.get("blinded") for p in players):
            warnings.append("Unsupported active player blindness would be discarded")
        for state in ["planting", "defusing", "reloading", "airborne"]:
            if any(p["alive"] and p.get(state) for p in players):
                warnings.append(f"Unsupported active player {state} state would be discarded")
        bomb = frame.get("bomb", {})
        if bomb.get("state") not in {"carried", "dropped", "planted"}:
            raise ValueError("Branch requires a known, nonterminal bomb state")
        if bomb.get("state") == "planted" and any(p["team"] == "CT" and p["alive"] and p.get("defuser") is None for p in players):
            warnings.append("Unknown CT defuse kits will be assumed absent (10-second defuse)")
        aliases = {"ak47": "AK_47", "m4a1_silencer": "M4A1", "m4a1": "M4A4", "m4a4": "M4A4", "usp_silencer": "USP_S", "glock": "Glock_18", "deagle": "Desert_Eagle", "galilar": "Galil_AR", "ssg08": "SSG_08", "hkp2000": "P2000", "elite": "Dual_Berettas", "fiveseven": "Five_SeveN", "tec9": "Tec_9", "cz75a": "CZ75_Auto", "revolver": "R8_Revolver", "sg556": "SG_553", "bizon": "PP_Bizon", "ump45": "UMP_45", "mp5sd": "MP5_SD", "sawedoff": "Sawed_Off", "scar20": "SCAR_20", "mac10": "MAC_10", "mag7": "MAG_7"}
        def token(value):
            return re.sub(r"[^a-z0-9]", "", value.lower())
        enum_names = {token(w.name): w for w in self.Weapon}
        aliases.update({"m4a1s": "M4A1", "usps": "USP_S", "ak47": "AK_47", "deserteagle": "Desert_Eagle", "glock18": "Glock_18"})
        aliases = {token(key): token(value) for key, value in aliases.items()}
        options = {"player_spawns": {}, "player_weapons": {}, "player_armor": {}, "player_helmet": {}}
        entries = []
        for team in ["T", "CT"]:
            for index, player in enumerate(p for p in players if p["team"] == team):
                slot = f"{team}_{index}"
                pos = self.Vec3(*to_engine(player["x"], player["y"], player["z"]))
                point = self.engine.waypoints.get_nearest_waypoint(pos)
                error = (pos - point["pos"]).length() / SCALE
                if player["alive"] and error > max_snap_units:
                    raise ValueError(f"Player {player['id']} is {error:.1f} Hammer units from navigation (limit {max_snap_units}); incompatible geometry")
                raw_weapon = str(player.get("weapon", "")).removeprefix("weapon_").lower()
                weapon_token = token(raw_weapon)
                weapon = self.Weapon.__members__.get(str(player.get("weapon", ""))) or enum_names.get(aliases.get(weapon_token, weapon_token))
                if weapon is None:
                    if player["alive"]:
                        warnings.append(f"Player {player['id']} unsupported active weapon {raw_weapon!r}; fallback is team rifle")
                    weapon = self.Weapon.AK_47 if team == "T" else self.Weapon.M4A1
                options["player_spawns"][slot] = {"init_waypoint_id": point["id"]}
                options["player_weapons"][slot] = weapon
                options["player_armor"][slot] = int(player.get("armor", 0)) > 0
                options["player_helmet"][slot] = bool(player.get("helmet", False))
                entries.append((slot, player, error, point["id"]))
        if warnings and not allow_approximate:
            raise ValueError("Scenario needs explicit --allow-approximate: " + "; ".join(warnings))
        self.reset(seed=seed, options=options)
        for slot, player, error, point_id in entries:
            agent = self.engine.agents[slot]
            self.external_ids[slot] = str(player["id"])
            self.names[slot] = player.get("name", str(player["id"]))
            self.kits[slot] = bool(player.get("defuser", False))
            self.armor[slot] = int(player.get("armor", 0))
            if not player["alive"]:
                self.descriptive_weapons[slot] = player.get("weapon", "unknown")
            agent.health = int(player["hp"]) if player["alive"] else 0
            agent.view_angle = float(player.get("yaw", 0))
            if not player["alive"]:
                agent.die()
            self.restore_report["snaps"].append({"id": str(player["id"]), "waypoint": point_id, "error_units": _round(error), "alive": bool(player["alive"])})
        self.restore_report["warnings"] = warnings
        self.source_time = float(frame.get("time", 0))
        self.engine.bomb_carrier = None
        self.engine.bomb_world_position = None
        if bomb["state"] == "carried":
            slot = self._slot(str(bomb["carrier_id"]))
            if not self.engine.agents[slot].is_alive or not self.engine.agents[slot].is_t:
                raise ValueError("Bomb carrier must be a living T")
            self.engine.bomb_carrier = slot
            self.engine.bomb_status = self.BombStatus.Carried
            self.engine.game_time_limit = float(frame["round_time_remaining"])
        else:
            self.engine.bomb_world_position = self.Vec3(*to_engine(bomb["x"], bomb["y"], bomb["z"]))
            self.engine.bomb_status = self.BombStatus.Planted if bomb["state"] == "planted" else self.BombStatus.Dropped
            self.engine.game_time_limit = float(bomb["time_remaining"] if bomb["state"] == "planted" else frame["round_time_remaining"])
        if not 0 < self.engine.game_time_limit <= 120:
            raise ValueError("Remaining clock must be between 0 and 120 seconds")
        self.engine.termination_queue.clear()
        return self.frame()

    def scripted_orders(self):
        """Fixed baseline: both sides route toward A; plant/retake when in range."""
        bomb_pos = self.engine.current_bomb_position
        site = self.engine.waypoints.regions[self.Region.A_BOMBSITE][0]
        for slot, agent in self.engine.agents.items():
            if not agent.is_alive:
                continue
            if self.orders[slot]["type"] in {"plant", "defuse"} or self.routes[slot]:
                continue
            if agent.is_t and agent.has_bomb and agent.is_at_bomb_site:
                self.command({slot: {"type": "plant"}})
            elif agent.is_ct and self.engine.bomb_has_planted and agent.is_near_bomb:
                self.command({slot: {"type": "defuse"}})
            else:
                target = self.engine.waypoints.get_nearest_waypoint(bomb_pos, return_id=True) if self.engine.bomb_has_planted else site
                self.command({slot: {"type": "move", "waypoint": target}})

    def run(self, seconds=30, *, sample_seconds=0.25):
        started = time.perf_counter()
        frames = [self.frame()]
        elapsed = 0.0
        while elapsed + 1e-8 < seconds and not self.engine.game_ended:
            self.scripted_orders()
            duration = min(sample_seconds, seconds - elapsed)
            self.step(duration)
            frames.append(self.frame())
            elapsed += duration
        wall_seconds = time.perf_counter() - started
        report = {"seed": self.seed, "revision": REVISION, "combat": self.combat, "players": 10,
                  "simulated_seconds": self.engine.game_time, "wall_seconds": wall_seconds,
                  "ended": self.engine.game_ended, "winner": frames[-1]["winner"], "end_reason": frames[-1]["end_reason"],
                  "damage_queries": self.damage_queries, "damage_events": self.damage_events,
                  "logged_damage_events": sum(event["type"] == "damage" for event in self.events),
                  "logged_kill_events": sum(event["type"] == "kill" for event in self.events),
                  "stalled_agents": sorted(self.stalled), "restore": self.restore_report,
                  "graph_nodes": self.engine.waypoints.graph.number_of_nodes(), "graph_edges": self.engine.waypoints.graph.number_of_edges(),
                  "graph_integrity": bool(self.engine.waypoints.verify_graph_integrity()),
                  "state_sha256": hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest()}
        return {"schema_version": 1, "map": "de_dust2", "game": "csgo", "tick_rate": 60, "sample_rate": 1/sample_seconds,
                "match_id": "decoy-smoke", "rounds": [{"number": 1, "winner": frames[-1]["winner"], "frames": frames, "events": self.events}],
                "limitations": LIMITATIONS + self.restore_report["warnings"],
                "source": {"kind": "simulation", "engine": "DECOY", "label": "DECOY · scripted 5v5 check",
                           "revision": REVISION, "baseline": "scripted_omniscient_systems_test"}, "report": report}

    def export_map(self):
        graph = self.engine.waypoints.graph
        nodes = []
        for node, attrs in graph.nodes(data=True):
            x, y, z = map(_round, to_world(attrs["pos"]))
            nodes.append({"id": node, "x": x, "y": y, "z": z, "region": attrs["region_type"].name,
                          "region_id": attrs["region_type"].value})
        return {"map": "de_dust2", "game": "csgo", "source_revision": REVISION,
                "transform": {"scale": SCALE, "translation": [0, 0, 3.1], "units": "Hammer"},
                "nodes": nodes,
                "edges": [{"from": u, "to": v, "direction": attrs["direction"].value} for u, v, attrs in graph.edges(data=True)],
                "regions": {key.name: value for key, value in self.engine.waypoints.regions.items()},
                "graph_integrity": bool(self.engine.waypoints.verify_graph_integrity())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    map_parser = sub.add_parser("export-map")
    map_parser.add_argument("--output", type=Path, required=True)
    for name in ["smoke", "branch"]:
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--seconds", type=float, default=30)
        p.add_argument("--no-combat", action="store_true")
        if name == "branch":
            p.add_argument("--scenario", type=Path, required=True)
            p.add_argument("--allow-approximate", action="store_true")
            p.add_argument("--max-snap-units", type=float, default=128)
    args = parser.parse_args()
    if args.command == "export-map":
        with DecoyRuntime(combat=False) as runtime:
            payload = runtime.export_map()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "nodes": len(payload["nodes"]), "edges": len(payload["edges"]), "graph_integrity": payload["graph_integrity"]}))
        return
    with DecoyRuntime(seed=args.seed, combat=not args.no_combat) as runtime:
        if args.command == "branch":
            scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
            runtime.restore(scenario, seed=args.seed, allow_approximate=args.allow_approximate, max_snap_units=args.max_snap_units)
        replay = runtime.run(args.seconds)
        if args.command == "branch":
            replay["source"]["scenario"] = str(args.scenario.resolve())
            replay["source"]["demo_time"] = runtime.source_time
            replay["match_id"] = scenario.get("match_id", "demo-branch")
            replay["rounds"][0]["number"] = scenario.get("round_number", 1)
            scenario_source = scenario.get("source", {})
            replay["source"].update({
                "label": f"DECOY · {scenario_source.get('label', replay['match_id'])} · round {replay['rounds'][0]['number']}",
                "scenario_match_id": scenario.get("match_id"), "scenario_round_number": scenario.get("round_number"),
                "scenario_frame_index": scenario.get("frame_index"), "scenario_tick": scenario["frame"].get("tick"),
                "scenario_source": scenario_source,
            })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(replay, indent=2) + "\n", encoding="utf-8")
        report_path = args.output.with_suffix(".report.json")
        report_path.write_text(json.dumps(replay["report"], indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "report": str(report_path), **replay["report"]}, indent=2))


if __name__ == "__main__":
    main()
