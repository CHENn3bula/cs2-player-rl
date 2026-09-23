import copy
import pytest
from igl.schema import validate_frame, validate_replay, ValidationError
from igl.navigation import world_to_radar, radar_to_world


def example_frame():
    return {"tick": 10, "time": 0.0, "round_time_remaining": 115.0,
            "players": [{"id": f"{team}{i}", "team": team, "name": str(i), "x": float(i),
                         "y": 0.0, "z": 0.0, "yaw": 90.0, "hp": 100, "alive": True,
                         "weapon": "AK-47", "armor": 100, "helmet": True, "defuser": False,
                         "bomb": False} for team in ("T", "CT") for i in range(5)],
            "bomb": {"state": "dropped", "x": 0., "y": 0., "z": 0., "carrier_id": None, "time_remaining": None}}


def test_frame_rejects_hidden_corruption():
    frame = example_frame()
    validate_frame(frame)
    frame["players"][0]["x"] = float("nan")
    with pytest.raises(ValidationError, match="finite"):
        validate_frame(frame)


def test_duplicate_or_missing_slots_rejected():
    frame = example_frame()
    frame["players"][1]["id"] = frame["players"][0]["id"]
    with pytest.raises(ValidationError, match="distinct"):
        validate_frame(frame)
    frame = example_frame()
    frame["players"].pop()
    with pytest.raises(ValidationError, match="five slots"):
        validate_frame(frame)


def test_round_clock_must_not_jump_back_at_plant():
    a = example_frame()
    a["time"] = 30
    b = copy.deepcopy(a)
    b["tick"] += 64
    b["time"] = 0
    replay = {"schema_version": 1, "match_id": "x", "map": "de_dust2", "game": "csgo",
              "rounds": [{"number": 1, "frames": [a, b]}]}
    with pytest.raises(ValidationError, match="increasing"):
        validate_replay(replay)


@pytest.mark.parametrize("point", [(-2476, 3239), (0, 0), (1200.5, 2000.1)])
def test_radar_roundtrip(point):
    assert radar_to_world(*world_to_radar(*point)) == pytest.approx(point)
