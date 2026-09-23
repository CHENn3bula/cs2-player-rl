import json
import math
import pytest
from igl.navigation import Navigation


@pytest.fixture
def nav(tmp_path):
    # Two floors share x/y; directed staircase is the only allowed transition.
    payload = {"nodes": [{"id": 1, "x": 0, "y": 0, "z": 0},
                         {"id": 2, "x": 100, "y": 0, "z": 0},
                         {"id": 3, "x": 100, "y": 0, "z": 100},
                         {"id": 4, "x": 0, "y": 0, "z": 100}],
               "edges": [{"from": 1, "to": 2}, {"from": 2, "to": 3}, {"from": 3, "to": 4}]}
    path = tmp_path / "nav.json"
    path.write_text(json.dumps(payload))
    return Navigation(path)


def test_height_disambiguates_overlapping_map_positions(nav):
    assert nav.nearest([[1, 0, 98]])[0]["waypoint_id"] == 4
    assert nav.nearest([[1, 0, 2]])[0]["waypoint_id"] == 1


def test_route_does_not_teleport_between_floors_or_reverse_drops(nav):
    route, length = nav.route(1, 4)
    assert route == [1, 2, 3, 4]
    assert length == 300
    assert nav.route(4, 1) == ([], math.inf)
    assert nav.route(1, 4, max_distance=250) == ([], math.inf)
