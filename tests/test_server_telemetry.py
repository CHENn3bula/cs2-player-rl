"""HTTP presentation keeps exact source identities without rewriting the corpus."""
import json

from igl.data import load_replay, write_json
from igl.server import preserve_effect_ids, read_replay


def test_effect_ids_preserve_large_integers_for_javascript():
    identifier = 7955079406183515637
    payload = {"rounds": [{"frames": [{"utility": {
        "smokes": [{"grenadeEntityID": identifier, "startTick": 7899, "x": 1.5}],
        "fires": [{"uniqueID": identifier + 1}],
        "projectiles": [{"entity_id": identifier + 2}],
    }}], "events": [{"type": "grenade_throw", "entityId": identifier + 3}]}]}
    result = preserve_effect_ids(payload)
    restored = json.loads(json.dumps(result))
    utilities = restored["rounds"][0]["frames"][0]["utility"]
    assert utilities["smokes"][0]["grenadeEntityID"] == str(identifier)
    assert utilities["fires"][0]["uniqueID"] == str(identifier + 1)
    assert utilities["projectiles"][0]["entity_id"] == str(identifier + 2)
    assert restored["rounds"][0]["events"][0]["entityId"] == str(identifier + 3)
    assert utilities["smokes"][0]["startTick"] == 7899
    assert utilities["smokes"][0]["x"] == 1.5


def test_read_replay_preserves_file_and_idempotent_cached_presentation(tmp_path):
    identifier = 5074209722772702441
    raw = {"rounds": [{"frames": [{"utility": {"smokes": [
        {"grenadeEntityID": identifier}, {"grenadeEntityID": "already-a-string"},
    ], "fires": None, "projectiles": []}}], "events": []}]}
    path = write_json(tmp_path / "recording.json.gz", raw)
    before = path.read_bytes()
    result = read_replay(str(path), path.stat().st_mtime_ns)
    assert result["rounds"][0]["frames"][0]["utility"]["smokes"][0]["grenadeEntityID"] == str(identifier)
    assert path.read_bytes() == before
    assert load_replay(path)["rounds"][0]["frames"][0]["utility"]["smokes"][0]["grenadeEntityID"] == identifier
    assert preserve_effect_ids(result) == result
    assert result["rounds"][0]["frames"][0]["utility"]["smokes"][1]["grenadeEntityID"] == "already-a-string"


def test_absent_effect_ids_are_not_created():
    payload = {"rounds": [{"frames": [{"utility": {"projectiles": [
        {"projectileType": "Smoke Grenade", "x": 1, "y": 2, "z": 3},
    ]}}], "events": []}]}
    result = preserve_effect_ids(payload)
    projectile = result["rounds"][0]["frames"][0]["utility"]["projectiles"][0]
    assert set(projectile) == {"projectileType", "x", "y", "z"}
