"""Data boundary tests use an attributed excerpt of a real professional round."""
import copy
import json
from pathlib import Path

import pytest

from igl.catalog import fetch_dataset, load_manifest
from igl.data import import_esta, load_replay, normalize_esta, sha256, write_json
from igl.schema import validate_replay

ROOT = Path(__file__).resolve().parents[1]
EXCERPT = ROOT / "tests/fixtures/esta_round_excerpt.json.xz"
MANIFEST = ROOT / "data/manifests/esta-dust2-v1.json"


def test_real_round_continuous_time_across_plant():
    source = load_replay(EXCERPT)
    replay = normalize_esta(EXCERPT)
    assert validate_replay(replay)["frames"] == 10
    frames = replay["rounds"][0]["frames"]
    assert all(a["time"] < b["time"] for a, b in zip(frames, frames[1:]))
    before = [f for f in frames if f["bomb"]["state"] == "carried"][-1]
    planted = next(f for f in frames if f["bomb"]["state"] == "planted")
    assert planted["source_seconds"] < before["source_seconds"]
    assert planted["time"] > before["time"]
    assert planted["round_time_remaining"] is None
    assert planted["bomb"]["time_remaining"] == 40
    assert planted["bomb"]["timer_basis"] == "source_display_clock_quantized_1s"
    assert frames[0]["players"][0]["x"] == source["gameRounds"][0]["frames"][0]["t"]["players"][0]["x"]


def test_precise_ids_and_equipment_preserved():
    raw = load_replay(EXCERPT)["gameRounds"][0]["frames"][0]["t"]["players"][0]
    player = normalize_esta(EXCERPT)["rounds"][0]["frames"][0]["players"][0]
    assert player["id"] == str(raw["steamID"])
    assert int(player["id"]) > 2**53
    assert player["inventory"] == raw["inventory"]
    assert player["helmet"] == raw["hasHelmet"]
    assert player["defuser"] == raw["hasDefuse"]


def test_postround_events_excluded_and_reported(tmp_path):
    raw = load_replay(EXCERPT)
    rnd = raw["gameRounds"][0]
    extra = copy.deepcopy(rnd["bombEvents"][0])
    extra["tick"] = rnd["endTick"] + 1
    rnd["bombEvents"].append(extra)
    replay = normalize_esta(write_json(tmp_path / "postround.json", raw))
    canonical = replay["rounds"][0]
    assert all(canonical["freeze_end_tick"] <= e["tick"] <= canonical["end_tick"] for e in canonical["events"])
    assert replay["source"]["normalization"]["counts"]["outside_round_events"] >= 1
    assert " vs " in replay["source"]["label"]


def test_missing_slots_are_excluded_without_imputing(tmp_path):
    raw = load_replay(EXCERPT)
    raw["gameRounds"][0]["frames"][0]["t"]["players"].pop()
    path = write_json(tmp_path / "damaged.json", raw)
    replay = normalize_esta(path)
    assert len(replay["rounds"][0]["frames"]) == 9
    assert replay["source"]["normalization"]["counts"]["incomplete_roster_frames"] == 1
    validate_replay(replay)


def test_import_roundtrip_and_deterministic_gzip(tmp_path):
    first, second = tmp_path / "a.json.gz", tmp_path / "b.json.gz"
    replay = import_esta(EXCERPT, first, {"license": "CC-BY-SA-4.0"})
    write_json(second, replay)
    assert first.read_bytes() == second.read_bytes()
    assert load_replay(first) == replay


def test_manifest_has_disjoint_source_matches():
    manifest = load_manifest(MANIFEST)
    assert len(manifest["entries"]) == 12
    assert len({e["event"] for e in manifest["entries"]}) >= 3
    assert sum(e["bytes"] for e in manifest["entries"]) < 100_000_000
    groups = {}
    for entry in manifest["entries"]:
        groups.setdefault(entry["match_id"], set()).add(entry["split"])
    assert all(len(splits) == 1 for splits in groups.values())


def test_manifest_rejects_cross_split_leakage(tmp_path):
    manifest = load_manifest(MANIFEST)
    manifest["entries"][8]["match_id"] = manifest["entries"][0]["match_id"]
    path = write_json(tmp_path / "leaking.json", manifest)
    with pytest.raises(ValueError, match="crosses"):
        load_manifest(path)


def test_cache_integrity_verified_before_network(tmp_path, monkeypatch):
    manifest = copy.deepcopy(load_manifest(MANIFEST))
    entry = manifest["entries"][0]
    entry["bytes"] = EXCERPT.stat().st_size
    entry["sha256"] = sha256(EXCERPT)
    manifest["entries"] = [entry]
    manifest_path = write_json(tmp_path / "manifest.json", manifest)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    cache = raw_dir / (entry["demo_id"] + ".json.xz")
    cache.write_bytes(EXCERPT.read_bytes())

    def forbidden_network(*args, **kwargs):
        raise AssertionError("a validated cache must not access network")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_network)
    assert fetch_dataset(manifest_path, raw_dir)[0]["status"] == "cached_verified"
    cache.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Checksum"):
        fetch_dataset(manifest_path, raw_dir)


def test_unsupported_source_rejected(tmp_path):
    raw = load_replay(EXCERPT)
    raw["mapName"] = "de_mirage"
    with pytest.raises(ValueError, match="de_dust2"):
        normalize_esta(write_json(tmp_path / "wrong-map.json", raw))
