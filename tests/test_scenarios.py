import copy
import pytest
from igl.scenarios import extract_scenario
from test_schema import example_frame


def replay():
    frame = example_frame()
    return {"schema_version": 1, "match_id": "demo", "game": "csgo", "map": "de_dust2",
            "rounds": [{"number": 7, "frames": [frame, copy.deepcopy(frame)],
                        "events": [{"type": "future_kill", "tick": 123}]}], "source": {"split": "test"}}


def test_scenario_contains_snapshot_not_recorded_future():
    data = replay()
    scenario = extract_scenario(data, 7, 0)
    assert "events" not in scenario and "rounds" not in scenario
    assert scenario["source"]["split"] == "test"
    scenario["frame"]["players"][0]["hp"] = 1
    assert data["rounds"][0]["frames"][0]["players"][0]["hp"] == 100


def test_wrong_map_and_terminal_states_cannot_branch():
    data = replay()
    data["map"] = "de_mirage"
    with pytest.raises(ValueError, match="Dust II"):
        extract_scenario(data, 7, 0)
    data = replay()
    data["rounds"][0]["frames"][0]["bomb"]["state"] = "defused"
    with pytest.raises(ValueError, match="terminal"):
        extract_scenario(data, 7, 0)
