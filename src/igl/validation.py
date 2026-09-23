"""Produce machine-readable evidence for the data and simulator foundation."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from .paths import DATA, REPORTS, ROOT, write_json
from .catalog import load_manifest
from .data import load_replay, sha256
from .schema import validate_replay
from .navigation import Navigation


def audit_data(manifest_path=None, *, geometry: bool = True, processed_dir=None, report_path=None) -> dict:
    manifest_path = manifest_path or DATA / "manifests" / "esta-dust2-v1.json"
    manifest = load_manifest(manifest_path)
    processed_dir = processed_dir or DATA / "processed"
    navigation = Navigation() if geometry else None
    results = []
    for entry in manifest["entries"]:
        raw = DATA / "raw" / "esta" / (entry["demo_id"] + ".json.xz")
        processed = processed_dir / (entry["demo_id"] + ".json.gz")
        if not raw.exists() or not processed.exists():
            raise ValueError(f"Missing raw or normalized data for {entry['demo_id']}")
        if sha256(raw) != entry["sha256"]:
            raise ValueError(f"Raw source checksum mismatch for {entry['demo_id']}")
        replay = load_replay(processed)
        result = validate_replay(replay)
        if replay["source"].get("split") != entry["split"]:
            raise ValueError(f"Split metadata differs for {entry['demo_id']}")
        result["raw_sha256_verified"] = True
        result["normalized_sha256"] = sha256(processed)
        result["split"] = entry["split"]
        if navigation:
            result["alignment"] = navigation.audit_replay(replay)
        results.append(result)
    report = {
        "schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed", "corpus": {"matches": len(results),
        "rounds": sum(r["rounds"] for r in results), "frames": sum(r["frames"] for r in results)},
        "checks": {"raw_checksums": True, "canonical_schema": True, "continuous_timelines": True,
                   "five_slots_per_team": True, "match_disjoint_splits": True,
                   "waypoint_alignment_measured": navigation is not None},
        "matches": results,
        "limits": ["Alignment distances are diagnostics, not a physics-fidelity certification.",
                   "Historical CS:GO corpus, not current CS2 data.",
                   "No model training or policy performance claim."],
    }
    write_json(report_path or REPORTS / "data_audit.json", report)
    return report


def foundation_report() -> dict:
    """Aggregate only existing evidence, preserving not-run states."""
    components = {}
    for name, file in (("data", "data_audit.json"), ("full_data", "full_data_audit.json"),
                       ("runtime", "decoy_smoke_report.json"),
                       ("pro_branch", "pro_branch_report.json"),
                       ("tests", "tests.json"), ("browser", "browser.json")):
        path = REPORTS / file
        components[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not_run"}
    report = {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
              "project": "Dust II IGL foundation", "no_training_performed": True,
              "components": components}
    write_json(REPORTS / "foundation.json", report)
    return report
