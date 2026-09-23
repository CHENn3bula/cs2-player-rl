"""Run the complete repeatable verification suite; fail on missing prerequisites."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from igl.paths import DATA, REPORTS, write_json
from igl.bridge import runtime_python, decoy_command
from igl.data import load_replay
from igl.schema import validate_replay
from igl.scenarios import extract_scenario
from igl.validation import audit_data, foundation_report


def run_tests(name, command):
    print(f"Checking {name}...", flush=True)
    began = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    (REPORTS / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{name} failed:\n{result.stdout}\n{result.stderr}")
    report = {"status": "passed", "wall_seconds": time.perf_counter() - began}
    count = re.search(r"^# tests (\d+)\s*$", result.stdout, re.MULTILINE)
    if count:
        report["tests"] = int(count.group(1))
    return report


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    tests = {}
    tests["asset-integrity"] = run_tests("asset-integrity", [sys.executable, "scripts/setup_decoy.py"])
    for name, python, args in [
        ("unit-tests", sys.executable, ["tests", "--ignore=tests/test_decoy_runtime.py"]),
        ("runtime-tests", str(runtime_python()), ["tests/test_decoy_runtime.py"]),
    ]:
        output = REPORTS / f"{name}.xml"
        tests[name] = run_tests(name, [python, "-m", "pytest", *args, "-q", "--junitxml", str(output)])
        suites = ET.parse(output).getroot()
        suite = suites if suites.tag == "testsuite" else suites.find("testsuite")
        tests[name].update({key: int(suite.attrib.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")})
        if tests[name]["skipped"]:
            raise RuntimeError(f"{name} skipped required checks; foundation is not verified")
    tests["viewer-tests"] = run_tests("viewer-tests", ["node", "--test", "web/app.test.cjs", "web/telemetry.test.cjs", "web/effects.test.cjs", "web/motion.test.cjs"])
    write_json(REPORTS / "tests.json", {"status": "passed", "checked_at": datetime.now(timezone.utc).isoformat(),
                                      "total_tests": sum(s.get("tests", 0) for s in tests.values()), "suites": tests})
    print("Checking data integrity and navigation alignment...", flush=True)
    audit_data()
    print("Running actual 5v5 DECOY smoke...", flush=True)
    smoke = DATA / "simulations" / "smoke.json"
    decoy_command(["smoke", "--output", str(smoke), "--seed", "42", "--seconds", "120"])
    replay = load_replay(smoke)
    validate_replay(replay)
    if not replay["report"]["ended"] or replay["report"]["stalled_agents"]:
        raise RuntimeError("5v5 smoke did not finish cleanly")
    write_json(REPORTS / "decoy_smoke_report.json", {"status": "passed", **replay["report"]})
    # Fixed real, no-active-utility 2v2. Exact source identity is pinned in the manifest.
    pro = load_replay(DATA / "processed" / "0520c3de-fdfe-4387-8060-5916549ad991.json.gz")
    scenario = extract_scenario(pro, 6, 217)
    scenario_path = DATA / "scenarios" / "pro_sample.json"
    write_json(scenario_path, scenario)
    branch_path = DATA / "simulations" / "pro_branch.json"
    print("Branching the real professional post-plant snapshot...", flush=True)
    decoy_command(["branch", "--scenario", str(scenario_path), "--output", str(branch_path),
                   "--seed", "42", "--seconds", "30", "--max-snap-units", "80"])
    branch = load_replay(branch_path)
    validate_replay(branch)
    if branch["report"]["restore"]["warnings"] or branch["report"]["stalled_agents"]:
        raise RuntimeError("Verified professional scenario now requires approximation or has stalls")
    write_json(REPORTS / "pro_branch_report.json", {"status": "passed", **branch["report"]})
    foundation_report()
    print(json.dumps({"status": "passed", "reports": str(REPORTS), "tests": tests}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
