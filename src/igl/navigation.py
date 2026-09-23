"""Auditable coordinate projection and waypoint alignment, using the real DECOY graph."""
from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from .paths import DATA

RADAR = {
    "image": "/assets/de_dust2.png", "pos_x": -2476, "pos_y": 3239,
    "scale": 4.4, "width": 1024, "height": 1024,
    "map": "de_dust2", "game": "csgo", "coordinate_units": "Hammer units",
    "source": "HATS-ICT/decoy env/utils.py and env/assets/de_dust2.png",
}


def world_to_radar(x: float, y: float) -> tuple[float, float]:
    return (x - RADAR["pos_x"]) / RADAR["scale"], (RADAR["pos_y"] - y) / RADAR["scale"]


def radar_to_world(x: float, y: float) -> tuple[float, float]:
    return x * RADAR["scale"] + RADAR["pos_x"], RADAR["pos_y"] - y * RADAR["scale"]


class Navigation:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA / "assets" / "dust2_waypoints.json"
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.nodes = {int(n["id"]): n for n in data["nodes"]}
        self.ids = list(self.nodes)
        self.points = np.array([[n["x"], n["y"], n["z"]] for n in self.nodes.values()])
        self.tree = cKDTree(self.points)
        self.edges = {n: {} for n in self.nodes}
        for edge in data["edges"]:
            a, b = int(edge["from"]), int(edge["to"])
            pa, pb = self.nodes[a], self.nodes[b]
            self.edges[a][b] = math.dist([pa[k] for k in "xyz"], [pb[k] for k in "xyz"])
        self.metadata = {k: v for k, v in data.items() if k not in {"nodes", "edges"}}

    def nearest(self, points: list[list[float]] | np.ndarray) -> list[dict]:
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        distances, indices = self.tree.query(points)
        results = []
        for original, distance, index in zip(points, distances, indices):
            target = self.points[index]
            results.append({
                "waypoint_id": self.ids[index], "distance": float(distance),
                "horizontal_error": float(np.linalg.norm(target[:2] - original[:2])),
                "vertical_error": float(abs(target[2] - original[2])),
                "position": target.tolist(),
            })
        return results

    def route(self, start: int, goal: int, max_distance: float = math.inf) -> tuple[list[int], float]:
        """Shortest legal directed route. Never invent edges across geometry."""
        if start not in self.nodes or goal not in self.nodes:
            raise ValueError("Unknown waypoint")
        queue = [(0.0, start)]
        distances = {start: 0.0}
        parents = {}
        while queue:
            distance, node = heapq.heappop(queue)
            if distance > distances[node] or distance > max_distance:
                continue
            if node == goal:
                route = [node]
                while node in parents:
                    node = parents[node]
                    route.append(node)
                return list(reversed(route)), distance
            for child, weight in self.edges[node].items():
                candidate = distance + weight
                if candidate < distances.get(child, math.inf):
                    distances[child] = candidate
                    parents[child] = node
                    heapq.heappush(queue, (candidate, child))
        return [], math.inf

    def audit_replay(self, replay: dict, stride: int = 4) -> dict:
        """Position coverage diagnostic. Not a proof of visibility or physics fidelity."""
        points = []
        for rnd in replay["rounds"]:
            for frame in rnd["frames"][::stride]:
                points.extend([[p[k] for k in "xyz"] for p in frame["players"] if p["alive"]])
        results = self.nearest(points)
        if not results:
            return {"match_id": replay["match_id"], "samples": 0}
        output = {"match_id": replay["match_id"], "samples": len(results), "frame_stride": stride}
        for field in ("distance", "horizontal_error", "vertical_error"):
            values = [r[field] for r in results]
            output[field] = {"median": float(np.median(values)), "p95": float(np.percentile(values, 95)), "max": max(values)}
        output["over_80_units"] = sum(r["distance"] > 80 for r in results)
        output["caveat"] = "Nearest-waypoint distance only; same-map name does not establish same map revision."
        return output

    def project_round(self, replay: dict, round_number: int, *, max_snap_units: float = 80,
                      max_speed: float = 300) -> dict:
        """Map a recorded round onto graph routes, retaining rejected segments.

        Paths are candidate waypoint targets, not recorded IGL intent. A speed
        cap and 3D snap bound prevent unconstrained interpolation across gaps.
        """
        rnd = next((r for r in replay["rounds"] if r["number"] == round_number), None)
        if rnd is None:
            raise ValueError("Round not found")
        rows, previous, route_cache = [], {}, {}
        accepted, rejected = 0, 0
        for frame in rnd["frames"]:
            alive = [p for p in frame["players"] if p["alive"]]
            mappings = self.nearest([[p[k] for k in "xyz"] for p in alive])
            for player, mapping in zip(alive, mappings):
                row = {"player_id": player["id"], "team": player["team"], "tick": frame["tick"],
                       "time": frame["time"], **mapping, "route_from_previous": None, "accepted": True}
                if mapping["distance"] > max_snap_units:
                    row.update(accepted=False, reason="outside_snap_tolerance")
                if row["accepted"] and player["id"] in previous:
                    old = previous[player["id"]]
                    dt = frame["time"] - old["time"]
                    budget = max_speed * dt + 2 * max_snap_units
                    key = (old["waypoint_id"], mapping["waypoint_id"], round(budget, 2))
                    if key not in route_cache:
                        route_cache[key] = self.route(key[0], key[1], max_distance=budget)
                    route, length = route_cache[key]
                    if not route or dt <= 0:
                        row.update(accepted=False, reason="no_route_within_time_budget")
                    else:
                        row.update(route_from_previous=route, route_length=length, duration=dt)
                if row["accepted"]:
                    previous[player["id"]] = row
                    accepted += 1
                else:
                    previous.pop(player["id"], None)
                    rejected += 1
                rows.append(row)
        return {"schema_version": 1, "kind": "waypoint_projection", "match_id": replay["match_id"],
                "round_number": round_number, "map": replay["map"], "game": replay["game"],
                "source": replay.get("source", {}), "graph": self.metadata,
                "parameters": {"max_snap_units": max_snap_units, "max_speed": max_speed},
                "summary": {"accepted": accepted, "rejected": rejected}, "samples": rows,
                "limitations": ["Routes are shortest graph paths, not exact recorded micro-movement.",
                                "Snap tolerances do not prove that no thin wall or obstacle separates a point and its node.",
                                "These are geometric behavior targets, not ground-truth IGL calls."]}
