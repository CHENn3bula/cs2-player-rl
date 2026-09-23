"""Run the actual DECOY adapter in an isolated process/runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import uuid

from .paths import ROOT, DATA, REPORTS, write_json


def runtime_python() -> Path:
    binary = ROOT / ".venv-decoy" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not binary.is_file():
        raise RuntimeError("DECOY runtime is not installed. Run python scripts/setup_decoy.py first.")
    return binary


def decoy_command(args: list[str], timeout: int = 240) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"
    command = [str(runtime_python()), "-m", "igl.decoy_runtime", *args]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if result.returncode:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "decoy-last-error.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else "Runtime exited without a diagnostic"
        detail = detail.removeprefix("ValueError: ").removeprefix("RuntimeError: ")
        raise RuntimeError(detail)
    return result


def branch(scenario: dict, *, seed: int = 42, seconds: float = 30) -> dict:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in [0, 2^32)")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 120:
        raise ValueError("seconds must be in (0,120]")
    job = uuid.uuid4().hex[:12]
    input_path = DATA / "scenarios" / f"branch-{job}.json"
    output_path = DATA / "simulations" / f"branch-{job}.json"
    write_json(input_path, scenario)
    decoy_command(["branch", "--scenario", str(input_path), "--output", str(output_path),
                   "--seed", str(seed), "--seconds", str(seconds)])
    output = json.loads(output_path.read_text(encoding="utf-8"))
    return output.get("replay", output)
