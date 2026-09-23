"""Pinned, checksummed public corpus acquisition and reproducible preparation."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from .data import build_scenario_index, import_esta, sha256, summarize_replay, write_json


def load_manifest(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("entries"):
        raise ValueError("invalid dataset manifest")
    ids, groups = set(), {}
    for entry in manifest["entries"]:
        identifier = entry["demo_id"]
        if identifier in ids or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise ValueError("duplicate or unsafe demo_id")
        ids.add(identifier)
        if entry["split"] not in ("train", "validation", "test"):
            raise ValueError("invalid split")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("invalid sha256")
        if not entry["url"].startswith("https://"):
            raise ValueError("downloads require HTTPS")
        group = entry["match_id"]
        if group in groups and groups[group] != entry["split"]:
            raise ValueError("source match crosses data splits")
        groups[group] = entry["split"]
    return manifest


def _entries(manifest: dict, limit: int | None) -> list[dict]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    return manifest["entries"] if limit is None else manifest["entries"][:limit]


def fetch_dataset(manifest_path: str | Path, raw_dir: str | Path, limit: int | None = None) -> list[dict]:
    """Download pinned bytes. Existing corrupt cache is rejected, never trusted."""
    manifest, raw_dir = load_manifest(manifest_path), Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in _entries(manifest, limit):
        target = raw_dir / (entry["demo_id"] + ".json.xz")
        if target.exists():
            if target.stat().st_size != entry["bytes"] or sha256(target) != entry["sha256"]:
                raise ValueError(f"Checksum mismatch for cached file {target}; restore from pinned source")
            status = "cached_verified"
        else:
            part = target.with_suffix(target.suffix + ".part")
            request = urllib.request.Request(entry["url"], headers={"User-Agent": "igl-foundations/0.1 (ESTA research corpus)"})
            try:
                with urllib.request.urlopen(request, timeout=90) as response, open(part, "wb") as out:
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        out.write(block)
                        if out.tell() > entry["bytes"]:
                            raise ValueError(f"Download exceeds manifest length: {target}")
                if part.stat().st_size != entry["bytes"] or sha256(part) != entry["sha256"]:
                    raise ValueError(f"Downloaded checksum mismatch: {target}")
                part.replace(target)
            finally:
                part.unlink(missing_ok=True)
            status = "downloaded_verified"
        results.append({"demo_id": entry["demo_id"], "path": str(target), "status": status,
                        "bytes": entry["bytes"], "sha256": entry["sha256"]})
    return results


def normalize_dataset(manifest_path: str | Path, raw_dir: str | Path, processed_dir: str | Path,
                      limit: int | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    raw_dir, processed_dir = Path(raw_dir), Path(processed_dir)
    matches, scenarios = [], []
    for entry in _entries(manifest, limit):
        source = raw_dir / (entry["demo_id"] + ".json.xz")
        if not source.exists() or sha256(source) != entry["sha256"]:
            raise ValueError(f"Missing or corrupt source {source}; run fetch first")
        output = processed_dir / (entry["demo_id"] + ".json.gz")
        provenance = {key: entry[key] for key in ("url", "sha256", "split")}
        provenance.update({"repository": manifest["repository"], "commit": manifest["commit"],
                           "license": manifest["license"], "attribution": manifest["attribution"]})
        replay = import_esta(source, output, provenance)
        if replay["source"]["match_id"] != entry["match_id"] or replay["match_id"] != entry["demo_id"]:
            raise ValueError("source identity differs from pinned manifest")
        summary = summarize_replay(replay)
        summary.update({"split": entry["split"], "file": output.name, "sha256": sha256(output)})
        matches.append(summary)
        scenarios.extend(build_scenario_index(replay, entry["split"]))
    summary = {"schema_version": 1, "dataset": manifest["name"], "source_commit": manifest["commit"],
               "license": manifest["license"], "matches": matches,
               "totals": {"matches": len(matches), "rounds": sum(m["rounds"] for m in matches),
                          "frames": sum(m["frames"] for m in matches), "events": sum(m["events"] for m in matches),
                          "scenario_candidates": len(scenarios)},
               "split_counts": {split: sum(m["split"] == split for m in matches)
                                for split in ("train", "validation", "test")}}
    write_json(processed_dir / "summary.json", summary, pretty=True)
    write_json(processed_dir / "scenarios.json", {"schema_version": 1, "candidates": scenarios}, pretty=True)
    return summary
