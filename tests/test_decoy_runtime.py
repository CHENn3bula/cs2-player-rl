"""Real FBX/Bullet/model integration checks; skipped without optional runtime.

Run using .venv-decoy/Scripts/python -m pytest tests/test_decoy_runtime.py.
No model is trained. No replacement map/engine is used in these checks.
"""
from copy import deepcopy
import importlib.util
import math
from pathlib import Path
import json

import pytest

from igl.decoy_runtime import DecoyRuntime, ROOT, to_engine, to_world


@pytest.fixture(scope="module")
def runtime():
    if importlib.util.find_spec("torch") is None or importlib.util.find_spec("panda3d") is None:
        pytest.skip("Optional DECOY integration requires .venv-decoy")
    if not (ROOT / "vendor/decoy/env/assets/de_dust_2.fbx").is_file():
        pytest.skip("DECOY FBX not downloaded")
    with DecoyRuntime(combat=False) as env:
        yield env


@pytest.fixture
def env(runtime):
    runtime.combat = False
    runtime.round_seconds = 115
    runtime.reset(seed=42)
    return runtime


def scenario(frame):
    return {"schema_version": 1, "map": "de_dust2", "game": "csgo", "frame": deepcopy(frame)}


def plant_state(env, *, seconds=20, kit=False):
    frame = env.frame()
    point = env.engine.waypoints.regions[env.Region.A_BOMBSITE][0]
    xyz = to_world(env.engine.waypoints.get_waypoint_by_id(point)["pos"])
    frame["bomb"] = {"state": "planted", "x": xyz[0], "y": xyz[1], "z": xyz[2], "carrier_id": None, "time_remaining": seconds}
    for p in frame["players"]:
        p["bomb"] = False
        if p["team"] == "T":
            p["hp"], p["alive"] = 0, False
        elif p["id"] == "CT_0":
            p.update(x=xyz[0], y=xyz[1], z=xyz[2], defuser=kit)
    return scenario(frame)


def test_coordinate_roundtrip():
    for point in [(0, 0, 0), (-1800, 2650, 140), (123.45, -678.9, -99)]:
        assert to_world(to_engine(*point)) == pytest.approx(point)


def test_effective_graph_and_ten_agents(env):
    exported = env.export_map()
    assert len(env.frame()["players"]) == 10
    assert len(exported["nodes"]) == 6638
    assert len(exported["edges"]) == 48053
    assert exported["graph_integrity"]
    assert env.engine.world.getNumCharacters() == 10


def test_commands_move_and_ownership(env):
    start = env.frame()["players"][0]
    agent = env.engine.agents[start["id"]]
    target = env.engine.waypoints.get_neighbors(agent.current_waypoint["id"], return_id=True)[0]
    with pytest.raises(ValueError, match="cannot control"):
        env.command({start["id"]: {"type": "move", "waypoint": target}}, team="CT")
    env.command({start["id"]: {"type": "move", "waypoint": target}}, team="T")
    env.step(0.5)
    after = next(p for p in env.frame()["players"] if p["id"] == start["id"])
    assert math.hypot(after["x"] - start["x"], after["y"] - start["y"]) > 5
    with pytest.raises(ValueError, match="Unsupported order"):
        env.command({start["id"]: {"type": "throw_smoke"}})


def test_commander_can_redirect_mid_edge_to_previous_waypoint(env):
    slot = "T_0"
    agent = env.engine.agents[slot]
    start = agent.current_waypoint["id"]
    target = next(n for n in env.engine.waypoints.graph.neighbors(start) if env.engine.waypoints.graph.has_edge(n, start))
    origin = env.Vec3(agent.position)
    env.command({slot: {"type": "move", "waypoint": target}})
    env.step(0.05)
    traveled = (agent.position.xy - origin.xy).length()
    assert traveled > 0.13
    env.command({slot: {"type": "move", "waypoint": start}})
    assert list(env.routes[slot]) == [start]
    env.step(0.5)
    assert (agent.position.xy - origin.xy).length() < traveled


def test_seeded_reset_and_real_combat_deterministic(env):
    env.combat = True
    first = env.run(20)
    assert first["report"]["damage_queries"] > 0
    assert first["report"]["damage_events"] > 0
    assert first["report"]["ended"]
    env.reset(seed=42)
    second = env.run(20)
    assert first["report"]["state_sha256"] == second["report"]["state_sha256"]
    assert first["rounds"][0]["frames"] == second["rounds"][0]["frames"]


def test_round_timeout_is_bounded_and_reset_restores_clock(env):
    env.round_seconds = 1
    env.reset(seed=2)
    env.step(2)
    assert env.engine.game_ended
    assert env.frame()["end_reason"] == "TimeOut"
    assert env.engine.game_time == pytest.approx(1)
    env.round_seconds = 115
    env.reset(seed=2)
    assert env.frame()["round_time_remaining"] == 115
    assert env.engine.world.getNumCharacters() == 10


def test_planted_bomb_survives_t_elimination_then_explodes(env):
    env.restore(plant_state(env, seconds=2), seed=7)
    env.step(0.5)
    assert not env.engine.game_ended
    assert env.frame()["bomb"]["state"] == "planted"
    assert env.frame()["round_time_remaining"] is None
    env.step(2)
    assert env.frame()["end_reason"] == "BombDetonated"
    assert env.frame()["winner"] == "T"


@pytest.mark.parametrize("kit,required", [(False, 10), (True, 5)])
def test_explicit_timed_defuse(env, kit, required):
    env.restore(plant_state(env, seconds=20, kit=kit))
    env.command({"CT_0": {"type": "defuse"}}, team="CT")
    env.step(required - 0.25)
    assert env.frame()["bomb"]["state"] == "planted"
    env.step(0.25)
    assert env.frame()["end_reason"] == "BombDefused"
    assert env.frame()["winner"] == "CT"


def test_explicit_timed_plant(env):
    point = env.engine.waypoints.regions[env.Region.A_BOMBSITE][0]
    carrier = env.engine.bomb_carrier
    options = {"player_spawns": {carrier: {"init_waypoint_id": point}}, "init_bomb_carrier_id": carrier}
    env.reset(options=options)
    env.step(0.5)
    assert env.frame()["bomb"]["state"] == "carried"
    env.command({carrier: {"type": "plant"}}, team="T")
    env.step(3)
    assert env.frame()["bomb"]["state"] == "carried"
    env.step(0.2)
    assert env.frame()["bomb"]["state"] == "planted"
    assert env.frame()["bomb"]["time_remaining"] == pytest.approx(40)


def test_repeated_plant_preserves_progress_and_hold_cancels(env):
    point = env.engine.waypoints.regions[env.Region.A_BOMBSITE][0]
    carrier = env.engine.bomb_carrier
    env.reset(options={"player_spawns": {carrier: {"init_waypoint_id": point}}, "init_bomb_carrier_id": carrier})
    env.command({carrier: {"type": "plant", "yaw": 10}})
    env.step(1)
    assert env.bomb_progress[carrier] == pytest.approx(1)
    env.command({carrier: {"type": "plant", "yaw": 20}})
    assert env.bomb_progress[carrier] == pytest.approx(1)
    env.command({carrier: {"type": "hold"}})
    assert carrier not in env.bomb_progress
    for _ in range(6):
        env.command({carrier: {"type": "plant"}})
        env.step(0.5)
    assert env.frame()["bomb"]["state"] == "carried"
    env.command({carrier: {"type": "plant", "yaw": -10}})
    env.step(0.2)
    assert env.frame()["bomb"]["state"] == "planted"


def test_repeated_defuse_preserves_progress(env):
    env.restore(plant_state(env, seconds=20, kit=True))
    for _ in range(10):
        env.command({"CT_0": {"type": "defuse", "yaw": 450}})
        env.step(0.5)
    assert env.frame()["end_reason"] == "BombDefused"
    assert env.engine.agents["CT_0"].view_angle == 90


def test_hold_yaw_changes_real_visibility_without_time_or_movement(env):
    # Actual map/Bullet line of sight between neighboring spawn waypoints.
    env.reset(options={"player_spawns": {"T_0": {"init_waypoint_id": 4491}, "CT_0": {"init_waypoint_id": 4611}}})
    env.step(0.1)
    observer = env.engine.agents["T_0"]
    enemy = env.engine.agents["CT_0"]
    assert observer.has_line_of_sight_to_agent(enemy)
    delta = enemy.position - observer.position
    yaw = math.degrees(math.atan2(delta.y, delta.x))
    # Turn the four other observers away so only T_0 controls this visibility.
    for slot, agent in env.engine.agents.items():
        if agent.is_t and slot != "T_0":
            direction = enemy.position - agent.position
            away = math.degrees(math.atan2(direction.y, direction.x)) + 180
            env.command({slot: {"type": "hold", "yaw": away}})
    before = env.frame()
    env.command({"T_0": {"type": "hold", "yaw": yaw + 720}}, team="T")
    assert any(p["id"] == "CT_0" for p in env.team_observation("T")["visible_enemies"])
    env.command({"T_0": {"type": "hold", "yaw": yaw + 180}}, team="T")
    assert not any(p["id"] == "CT_0" for p in env.team_observation("T")["visible_enemies"])
    after = env.frame()
    assert before["tick"] == after["tick"] and before["time"] == after["time"]
    assert [(p["x"], p["y"], p["z"]) for p in before["players"]] == [(p["x"], p["y"], p["z"]) for p in after["players"]]
    assert 0 <= observer.view_angle < 360
    for invalid in [float("nan"), float("inf"), float("-inf"), True, "90"]:
        with pytest.raises(ValueError, match="finite number"):
            env.command({"T_0": {"type": "hold", "yaw": invalid}})


def test_restore_rejects_unknown_utility_kit_bad_geometry(env):
    snap = plant_state(env)
    snap["frame"]["players"][1]["defuser"] = None  # CT_0 in engine's interleaved ordering
    with pytest.raises(ValueError, match="Unknown CT defuse kits"):
        env.restore(snap)
    snap["frame"]["players"][1]["defuser"] = False
    snap["frame"]["utility"] = {"smokes": None}
    with pytest.raises(ValueError, match="utility is unknown"):
        env.restore(snap)
    snap["frame"]["utility"] = {"smokes": [{"x": 0}]}
    with pytest.raises(ValueError, match="Unsupported active"):
        env.restore(snap)
    snap["frame"]["utility"] = {"smokes": [], "fires": [], "projectiles": []}
    snap["frame"]["players"][1]["z"] += 10000
    with pytest.raises(ValueError, match="incompatible geometry"):
        env.restore(snap)


@pytest.mark.parametrize("utility", [{}, {"smokes": []}, {"smokes": [], "fires": [], "projectiles": None}])
def test_restore_unknown_utility_fields_fail_closed(env, utility):
    snap = scenario(env.frame())
    snap["frame"]["utility"] = utility
    with pytest.raises(ValueError, match="utility is unknown"):
        env.restore(snap)


def test_restore_preserves_identity_health_and_weapon_aliases(env):
    snap = scenario(env.frame())
    p = snap["frame"]["players"][0]
    p.update(id="steam123", hp=37, weapon="AK-47", armor=73, helmet=True)
    if snap["frame"]["bomb"]["carrier_id"] == "T_0":
        snap["frame"]["bomb"]["carrier_id"] = "steam123"
    snap["frame"]["players"][1]["weapon"] = "M4A1-S"
    restored = env.restore(snap)
    p = next(p for p in restored["players"] if p["id"] == "steam123")
    assert (p["hp"], p["armor"], p["helmet"], p["weapon"]) == (37, 73, True, "AK_47")
    assert len(env.restore_report["snaps"]) == 10


def test_team_observation_masks_unseen_enemies(env):
    ct = env.team_observation("CT", fov=0)
    assert len(ct["friends"]) == 5
    assert not ct["visible_enemies"]
    assert not ct["last_seen_enemies"]
    assert ct["bomb"] == {"state": "unknown"}


def test_invalid_step_fails(env):
    for duration in [-1, 999, float("nan")]:
        with pytest.raises(ValueError):
            env.step(duration)


def test_simultaneous_combat_inputs_use_boundary_health(env, monkeypatch):
    model_health_inputs = []
    def predict(*args):
        model_health_inputs.append(args[4])
        return True, 5, 0
    monkeypatch.setattr(env.engine.damage_model, "predict_damage", predict)
    for agent in env.engine.agents.values():
        agent.health = 1
        monkeypatch.setattr(agent, "has_line_of_sight_to_agent", lambda other: True)
    env.combat = True
    env.step(1 / 60)
    assert len(model_health_inputs) == 50
    assert set(model_health_inputs) == {1}
    damage_events = [event for event in env.events if event["type"] == "damage"]
    kill_events = [event for event in env.events if event["type"] == "kill"]
    assert len(damage_events) == 50
    assert len(kill_events) == 10
    for player in env.frame()["players"]:
        assert not player["alive"] and player["hp"] == 0
        received = [event for event in damage_events if event["victim_id"] == player["id"]]
        assert sum(event["damage_health"] for event in received) == pytest.approx(1)
        assert all(event["victim_health_before"] == 1 and event["victim_health_after"] == 0 for event in received)
        kill = next(event for event in kill_events if event["victim_id"] == player["id"])
        assert kill["attacker_id"] == min(event["attacker_id"] for event in received)
        assert kill["victim_name"] == player["name"]
        assert kill["tick"] == 0 and kill["time"] == 0


def test_real_professional_postplant_branch_and_repeatability(env):
    from igl.schema import validate_replay
    path = ROOT / "data/scenarios/pro_sample.json"
    if not path.exists():
        pytest.skip("Professional sample data has not been prepared")
    snap = json.loads(path.read_text(encoding="utf-8"))
    env.combat = True
    env.restore(snap, seed=42, max_snap_units=80)
    first = env.run(45)
    assert validate_replay(first)["frames"] > 2
    assert first["report"]["ended"]
    assert first["report"]["damage_queries"] > 0
    assert not first["report"]["restore"]["warnings"]
    assert not first["report"]["stalled_agents"]
    kills = [event for event in first["rounds"][0]["events"] if event["type"] == "kill"]
    damages = [event for event in first["rounds"][0]["events"] if event["type"] == "damage"]
    assert len(damages) == first["report"]["damage_events"]
    for player in first["rounds"][0]["frames"][0]["players"]:
        final = next(p for p in first["rounds"][0]["frames"][-1]["players"] if p["id"] == player["id"])
        victim_kills = [event for event in kills if event["victim_id"] == player["id"]]
        assert len(victim_kills) == int(player["alive"] and not final["alive"])
    env.restore(snap, seed=42, max_snap_units=80)
    second = env.run(45)
    assert first["report"]["state_sha256"] == second["report"]["state_sha256"]
    assert first["rounds"][0]["events"] == second["rounds"][0]["events"]
