"""Reproducible commands for data preparation, scenario export and verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .paths import DATA, REPORTS, ROOT, write_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dust II data and simulation foundation (no ML training)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "prepare", "audit"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", type=Path, default=DATA / "manifests" / "esta-dust2-v1.json")
        if name in {"prepare", "audit"}:
            p.add_argument("--processed-dir", type=Path, default=DATA / "processed")
        if name in {"fetch", "prepare"}:
            p.add_argument("--limit", type=int)
        else:
            p.add_argument("--no-geometry", action="store_true")
            p.add_argument("--report", type=Path, default=REPORTS / "data_audit.json")
    p = sub.add_parser("scenario")
    p.add_argument("replay", type=Path)
    p.add_argument("--round", type=int, required=True, dest="round_number")
    p.add_argument("--frame", type=int, required=True, dest="frame_index")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("project")
    p.add_argument("replay", type=Path)
    p.add_argument("--round", type=int, required=True, dest="round_number")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("simulate")
    p.add_argument("scenario", type=Path)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("smoke")
    p.add_argument("--output", type=Path, default=DATA / "simulations" / "smoke.json")
    p = sub.add_parser("export-map")
    p.add_argument("--output", type=Path, default=DATA / "assets" / "dust2_waypoints.json")
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--corpus", choices=["starter", "full"], default="starter")
    sub.add_parser("report")
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            from .catalog import fetch_dataset
            result = fetch_dataset(args.manifest, DATA / "raw" / "esta", args.limit)
            print(json.dumps(result, indent=2))
        elif args.command == "prepare":
            from .catalog import normalize_dataset
            result = normalize_dataset(args.manifest, DATA / "raw" / "esta", args.processed_dir, args.limit)
            print(json.dumps(result["totals"], indent=2))
        elif args.command == "audit":
            from .validation import audit_data
            result = audit_data(args.manifest, geometry=not args.no_geometry,
                                processed_dir=args.processed_dir, report_path=args.report)
            print(json.dumps({"status": result["status"], **result["corpus"]}, indent=2))
        elif args.command == "scenario":
            from .data import load_replay
            from .scenarios import extract_scenario
            result = extract_scenario(load_replay(args.replay), args.round_number, args.frame_index)
            write_json(args.output, result)
            print(args.output)
        elif args.command == "simulate":
            from .bridge import branch
            from .data import load_replay
            result = branch(load_replay(args.scenario), seed=args.seed, seconds=args.seconds)
            if args.output:
                write_json(args.output, result)
            print(json.dumps({"match_id": result["match_id"], "rounds": len(result["rounds"])}, indent=2))
        elif args.command == "project":
            from .navigation import Navigation
            from .data import load_replay
            result = Navigation().project_round(load_replay(args.replay), args.round_number)
            write_json(args.output, result)
            print(json.dumps(result["summary"], indent=2))
        elif args.command in {"smoke", "export-map"}:
            from .bridge import decoy_command
            result = decoy_command([args.command, "--output", str(args.output)])
            print(result.stdout)
        elif args.command == "serve":
            from .server import serve
            serve(args.port, args.corpus)
        elif args.command == "report":
            from .validation import foundation_report
            foundation_report()
            print(REPORTS / "foundation.json")
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
