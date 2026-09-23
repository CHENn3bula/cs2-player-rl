"""Local-only viewer and bounded simulation API. No external service required."""
from __future__ import annotations

from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse

from .paths import ROOT, DATA, DECOY
from .navigation import RADAR
from .scenarios import extract_scenario

PROCESSED_DIR = DATA / "processed"

def replay_paths(kind: str) -> dict[str, Path]:
    directory = DATA / "simulations" if kind == "simulations" else PROCESSED_DIR
    paths = {}
    for path in sorted(directory.glob("*.json*")):
        if path.name in {"summary.json", "scenarios.json"} or not (path.name.endswith(".json") or path.name.endswith(".json.gz")) or path.name.endswith(".report.json"):
            continue
        key = path.name.removesuffix(".gz").removesuffix(".json")
        paths[key] = path
    return paths


@lru_cache(maxsize=4)
def read_replay(path: str, modified: int) -> dict:
    from .data import load_replay
    data = load_replay(Path(path))
    return preserve_effect_ids(data.get("replay", data))


def preserve_effect_ids(replay: dict) -> dict:
    """Preserve exact effect identities in HTTP JSON without changing files.

    Python decodes the recorded 64-bit IDs exactly. Browsers cannot safely
    decode those IDs as JavaScript numbers, so the private loaded view uses
    decimal strings for known identity fields before JSON serialization.
    """
    identity_fields = ("entity_id", "entityId", "entityID", "uniqueID", "grenadeEntityID")

    def convert(record):
        if isinstance(record, dict):
            for field in identity_fields:
                value = record.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    record[field] = str(value)

    for rnd in replay.get("rounds", []):
        for frame in rnd.get("frames", []):
            utility = frame.get("utility") or {}
            for category in ("smokes", "fires", "projectiles"):
                for record in utility.get(category) or []:
                    convert(record)
        for event in rnd.get("events", []):
            convert(event)
    return replay


def get_replay(kind: str, key: str) -> dict:
    path = replay_paths(kind).get(key)
    if path is None:
        raise KeyError("Replay not found")
    return read_replay(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=128)
def replay_metadata(path: str, modified: int) -> dict:
    from .data import load_replay
    replay = load_replay(Path(path))
    replay = replay.get("replay", replay)
    if "rounds" not in replay:
        return {}
    source = replay.get("source", {})
    return {"match_id": replay["match_id"], "map": replay["map"], "game": replay["game"],
            "rounds": len(replay["rounds"]), "source": source,
            "label": replay.get("label", source.get("label", replay["match_id"]))}


def catalog() -> dict:
    result = {}
    for kind in ("matches", "simulations"):
        entries = []
        for key, path in replay_paths(kind).items():
            metadata = replay_metadata(str(path), path.stat().st_mtime_ns)
            if metadata:
                entries.append({**metadata, "id": key, "match_id": key})
        result[kind] = entries
    return result


SIMULATION_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "IGLFoundation/0.1"

    def send_bytes(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: object, status: int = 200):
        self.send_bytes(json.dumps(value, allow_nan=False).encode(), "application/json; charset=utf-8", status)

    def do_GET(self):
        try:
            path = unquote(urlparse(self.path).path)
            if path == "/api/health":
                return self.send_json({"ok": True, "project": "Dust II IGL foundation", "training": False})
            if path == "/api/catalog":
                return self.send_json(catalog())
            if path == "/api/map":
                return self.send_json(RADAR)
            if path == "/api/scenarios":
                sample = DATA / "scenarios" / "pro_sample.json"
                index = PROCESSED_DIR / "scenarios.json"
                verified = []
                if sample.exists():
                    scenario = json.loads(sample.read_text(encoding="utf-8"))
                    verified.append({key: scenario[key] for key in ("match_id", "round_number", "frame_index")})
                    verified[-1]["label"] = "G2 vs ENCE · round 6 · 2v2 post-plant"
                count = len(json.loads(index.read_text(encoding="utf-8"))["candidates"]) if index.exists() else 0
                return self.send_json({"verified": verified, "candidate_count": count})
            if path.startswith("/api/matches/"):
                return self.send_json(get_replay("matches", path.removeprefix("/api/matches/")))
            if path.startswith("/api/simulations/"):
                return self.send_json(get_replay("simulations", path.removeprefix("/api/simulations/")))
            if path == "/api/validation":
                report = ROOT / "reports" / "foundation.json"
                return self.send_json(json.loads(report.read_text()) if report.exists() else {"status": "not_run"})
            allowed = {
                "/": ROOT / "web" / "index.html", "/index.html": ROOT / "web" / "index.html",
                "/app.js": ROOT / "web" / "app.js", "/style.css": ROOT / "web" / "style.css",
                "/telemetry.js": ROOT / "web" / "telemetry.js",
                "/effects.js": ROOT / "web" / "effects.js",
                "/motion.js": ROOT / "web" / "motion.js",
                "/assets/de_dust2.png": DECOY / "env" / "assets" / "de_dust2.png",
            }
            file = allowed.get(path)
            if file is None or not file.is_file():
                return self.send_json({"error": "Not found"}, 404)
            return self.send_bytes(file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        except KeyError as error:
            self.send_json({"error": str(error)}, 404)
        except (ValueError, OSError) as error:
            self.send_json({"error": str(error)}, 400)

    def do_POST(self):
        if urlparse(self.path).path != "/api/simulate":
            return self.send_json({"error": "Not found"}, 404)
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != self.server.server_port:
                return self.send_json({"error": "Local same-origin requests only"}, 403)
        if self.headers.get_content_type() != "application/json":
            return self.send_json({"error": "Expected application/json"}, 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(length))
            replay = get_replay("matches", str(body["match_id"]))
            scenario = extract_scenario(replay, int(body["round_number"]), int(body["frame_index"]))
            if not SIMULATION_LOCK.acquire(blocking=False):
                return self.send_json({"error": "A simulation is already running; try again when it finishes."}, 409)
            try:
                from .bridge import branch
                output = branch(scenario, seed=body.get("seed", 42), seconds=body.get("seconds", 30))
            finally:
                SIMULATION_LOCK.release()
            self.send_json(output)
        except (KeyError, ValueError, RuntimeError) as error:
            self.send_json({"error": str(error)}, 422)
        except Exception as error:
            self.send_json({"error": f"Simulation failed: {error}"}, 500)


def serve(port: int = 8765, corpus: str = "starter"):
    global PROCESSED_DIR
    if corpus not in {"starter", "full"}:
        raise ValueError("corpus must be starter or full")
    PROCESSED_DIR = DATA / ("processed-full" if corpus == "full" else "processed")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dust II tactical viewer: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
