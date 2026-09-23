"""Discover and acquire every Dust II LAN map in a pinned ESTA repository.

Only compressed headers are read for map discovery. Matching full files are
verified against the upstream Git blob ID, then recorded with SHA-256. The
starter manifest and data/processed directory are never modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from igl.catalog import load_manifest
from igl.data import build_scenario_index, import_esta, sha256, summarize_replay, write_json

COMMIT = "0e81f74d480689a83f6e1e90835c1eb6f7aa0de2"
REPOSITORY = "https://github.com/pnxenopoulos/esta"
RAW_BASE = f"https://raw.githubusercontent.com/pnxenopoulos/esta/{COMMIT}/"
MANIFEST = ROOT / "data/manifests/esta-dust2-lan-full-v1.json"
DISCOVERY = ROOT / "data/manifests/esta-lan-discovery-v1.json"
RAW = ROOT / "data/raw/esta"
PROCESSED = ROOT / "data/processed-full"
MAX_RAW_BYTES = 1_000_000_000
HEADERS = {"User-Agent": "igl-foundations/0.1 (ESTA public research dataset)"}


def request_bytes(url, *, prefix_bytes=None):
    """Finite retries; header reads stop early and do not download entire maps."""
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read() if prefix_bytes is None else response.read(prefix_bytes)
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def source_tree():
    url = f"https://api.github.com/repos/pnxenopoulos/esta/git/trees/{COMMIT}?recursive=1"
    result = json.loads(request_bytes(url))
    if result.get("truncated"):
        raise ValueError("GitHub tree was truncated; cannot claim complete discovery")
    return [entry for entry in result["tree"]
            if entry["path"].startswith("data/lan/") and entry["path"].endswith(".json.xz")]


def inspect_header(entry):
    prefix = request_bytes(RAW_BASE + entry["path"], prefix_bytes=8192)
    decoded = lzma.LZMADecompressor().decompress(prefix).decode("utf-8", errors="ignore")
    match = re.search(r'"mapName"\s*:\s*"([^"]+)"', decoded)
    if not match:
        raise ValueError(f"No mapName in compressed prefix: {entry['path']}")
    return {"path": entry["path"], "map": match.group(1),
            "bytes": entry["size"], "git_blob_sha1": entry["sha"]}


def discover(workers):
    tree = source_tree()
    cache = {}
    if DISCOVERY.exists():
        saved = json.loads(DISCOVERY.read_text(encoding="utf-8"))
        if saved.get("commit") == COMMIT:
            cache = {entry["path"]: entry for entry in saved.get("entries", [])}
    rows, pending = [], []
    for entry in tree:
        cached = cache.get(entry["path"])
        if cached and cached["git_blob_sha1"] == entry["sha"] and cached["bytes"] == entry["size"]:
            rows.append(cached)
        else:
            pending.append(entry)
    print(f"Discovery: {len(tree)} LAN files, {len(rows)} cached headers, {len(pending)} to inspect", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(inspect_header, entry): entry["path"] for entry in pending}
        for job in as_completed(jobs):
            rows.append(job.result())
            if len(rows) % 40 == 0 or len(rows) == len(tree):
                write_json(DISCOVERY, {"schema_version": 1, "repository": REPOSITORY, "commit": COMMIT,
                                      "discovery_method": "First 8192 compressed bytes, LZMA prefix, mapName field",
                                      "complete": len(rows) == len(tree), "source_lan_files": len(tree),
                                      "entries": sorted(rows, key=lambda row: row["path"])}, pretty=True)
                print(f"Discovery: {len(rows)}/{len(tree)} inspected; {sum(row['map'] == 'de_dust2' for row in rows)} Dust II", flush=True)
    selected = [row for row in rows if row["map"] == "de_dust2"]
    total_bytes = sum(row["bytes"] for row in selected)
    if total_bytes > MAX_RAW_BYTES:
        raise ValueError(f"Dust II acquisition would exceed safety budget: {total_bytes} bytes")
    print(f"Discovery complete: {len(selected)} Dust II LAN maps, {total_bytes:,} raw bytes", flush=True)
    return sorted(selected, key=lambda row: row["path"])


def git_blob_hash(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()


def acquire(entry):
    path = RAW / Path(entry["path"]).name
    if path.exists():
        payload = path.read_bytes()
        status = "cached_verified"
    else:
        payload = request_bytes(RAW_BASE + entry["path"])
        status = "downloaded_verified"
    if len(payload) != entry["bytes"] or git_blob_hash(payload) != entry["git_blob_sha1"]:
        raise ValueError(f"Blob does not match pinned Git tree: {path}")
    digest = hashlib.sha256(payload).hexdigest()
    raw = json.loads(lzma.decompress(payload))
    if raw.get("mapName") != "de_dust2":
        raise ValueError("Full JSON disagrees with discovered mapName")
    if not path.exists():
        part = path.with_suffix(path.suffix + ".part")
        part.write_bytes(payload)
        part.replace(path)
    date = datetime.fromtimestamp(raw["matchDate"] / 1000, timezone.utc).isoformat()
    return {"demo_id": raw["demoId"], "match_id": raw["matchId"], "name": raw.get("matchName"),
            "event": raw.get("competitionName"), "match_url": raw.get("hltvUrl"), "date": date,
            "map": "de_dust2", "game": "csgo", "subset": "lan", "url": RAW_BASE + entry["path"],
            "sha256": digest, "git_blob_sha1": entry["git_blob_sha1"], "bytes": len(payload),
            "acquisition_status": status}


def assign_splits(entries):
    groups = {}
    for entry in entries:
        groups.setdefault(entry["match_id"], []).append(entry)
    ordered = sorted(groups, key=lambda group: (min(row["date"] for row in groups[group]), group))
    train_end = int(len(ordered) * .8)
    validation_end = int(len(ordered) * .9)
    for index, group in enumerate(ordered):
        split = "train" if index < train_end else "validation" if index < validation_end else "test"
        for entry in groups[group]:
            entry["split"] = split
    return sorted(entries, key=lambda entry: (entry["date"], entry["match_id"], entry["demo_id"]))


def save_manifest(entries):
    for entry in entries:
        entry.pop("acquisition_status", None)
    manifest = {"schema_version": 1, "name": "esta-dust2-lan-full-v1", "repository": REPOSITORY,
                "commit": COMMIT, "license": "CC-BY-SA-4.0",
                "license_url": f"{REPOSITORY}/blob/{COMMIT}/LICENSE",
                "attribution": "Esports Trajectories and Actions (ESTA), Peter Xenopoulos and contributors. Source data parsed using Awpy. Normalized and filtered by this project; original compressed files are unchanged.",
                "selection": "All data/lan/*.json.xz entries with mapName=de_dust2 at the pinned commit. Complete recursive Git tree, streaming LZMA headers, full matching blobs verified against Git blob SHA-1 and stored with SHA-256. No outcome filtering.",
                "split_policy": "Chronological 80/10/10 by source match group, flooring the 80% and 90% group boundaries. All demos/rounds/frames from a match stay together. Repeated players/teams/events across splits remain possible. Full-corpus split assignments are independent of the starter engineering fixture; do not mix the two manifests as a benchmark.",
                "entries": assign_splits(entries)}
    write_json(MANIFEST, manifest, pretty=True)
    return load_manifest(MANIFEST)


def prepare(manifest):
    matches, candidates, failures = [], [], []
    for index, entry in enumerate(manifest["entries"], 1):
        raw_path = RAW / (entry["demo_id"] + ".json.xz")
        output = PROCESSED / (entry["demo_id"] + ".json.gz")
        try:
            if sha256(raw_path) != entry["sha256"]:
                raise ValueError("Raw SHA-256 mismatch")
            provenance = {key: entry[key] for key in ("url", "sha256", "split")}
            provenance.update({key: manifest[key] for key in ("repository", "commit", "license", "attribution")})
            replay = import_esta(raw_path, output, provenance)
            if replay["match_id"] != entry["demo_id"] or replay["source"]["match_id"] != entry["match_id"]:
                raise ValueError("Normalized source identity disagrees with manifest")
            row = summarize_replay(replay)
            row.update({"split": entry["split"], "file": output.name, "sha256": sha256(output)})
            matches.append(row)
            candidates.extend(build_scenario_index(replay, entry["split"]))
        except (ValueError, KeyError, OSError, TypeError) as error:
            failures.append({"demo_id": entry["demo_id"], "error": str(error)})
            print(f"Validation failed for {entry['demo_id']}: {error}", flush=True)
        if index % 10 == 0 or index == len(manifest["entries"]):
            print(f"Normalize/validate: {index}/{len(manifest['entries'])}; {len(failures)} failures", flush=True)
    summary = {"schema_version": 1, "dataset": manifest["name"], "source_commit": COMMIT,
               "license": manifest["license"], "status": "passed" if not failures else "partial",
               "matches": matches, "failures": failures,
               "totals": {"acquired_maps": len(manifest["entries"]), "matches": len(matches),
                          "source_match_groups": len({entry["match_id"] for entry in manifest["entries"]}),
                          "events": sum(row["events"] for row in matches),
                          "rounds": sum(row["rounds"] for row in matches),
                          "frames": sum(row["frames"] for row in matches), "scenario_candidates": len(candidates),
                          "raw_compressed_bytes": sum(entry["bytes"] for entry in manifest["entries"]),
                          "processed_compressed_bytes": sum((PROCESSED / row["file"]).stat().st_size for row in matches)},
               "split_counts": {split: sum(entry["split"] == split for entry in manifest["entries"])
                                for split in ("train", "validation", "test")},
               "checks": {"complete_pinned_tree_discovery": True, "git_blob_sha1": True, "raw_sha256": True,
                          "match_disjoint_splits": True, "canonical_schema": not failures,
                          "waypoint_geometry": "not audited for full corpus"}}
    write_json(PROCESSED / "summary.json", summary, pretty=True)
    write_json(PROCESSED / "scenarios.json", {"schema_version": 1, "candidates": candidates}, pretty=True)
    print(json.dumps({"status": summary["status"], **summary["totals"], "splits": summary["split_counts"]}, indent=2), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4,
                        help="header concurrency; full-file parsing uses at most two workers")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--skip-normalize", action="store_true")
    parser.add_argument("--prepare-existing", action="store_true")
    args = parser.parse_args()
    if args.prepare_existing:
        manifest = load_manifest(MANIFEST)
    else:
        selected = discover(args.workers)
        if args.discover_only:
            return 0
        RAW.mkdir(parents=True, exist_ok=True)
        entries = []
        with ThreadPoolExecutor(max_workers=min(2, args.workers)) as pool:
            jobs = [pool.submit(acquire, entry) for entry in selected]
            for job in as_completed(jobs):
                entry = job.result()
                entries.append(entry)
                print(f"Acquire: {len(entries)}/{len(selected)} {entry['demo_id']} {entry['acquisition_status']}", flush=True)
        manifest = save_manifest(entries)
    if args.skip_normalize:
        return 0
    return 0 if prepare(manifest)["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
