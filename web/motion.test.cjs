"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const Motion = require("./motion.js");

const p = (x, y = 0, z = 0, type = "Smoke Grenade", extra = {}) => ({ projectileType: type, x, y, z, ...extra });
const frame = (time, projectiles, extra = {}) => ({ time, tick: 1000 + time * 128,
  utility: { projectiles, smokes: [], fires: [], ...extra } });
const markers = (points) => points.map(({ projectileType, ...point }) => ({ ...point,
  kind: { "Smoke Grenade": "smoke", Flashbang: "flash", Molotov: "molotov" }[projectileType] ?? projectileType,
  phase: "projectile", trail: [], source: "sampled_frame", entity_id: point.entity_id ?? null }));
const telemetry = (points) => ({ projectiles: markers(points), known: { projectiles: true, smokes: false },
  smokes: [], fires: [], shots: [], pulses: [] });
const round = (a, b, events = []) => ({ frames: [frame(0, a), frame(.5, b)], events });
const xyz = (point) => [point.x, point.y, point.z];
const mid = (a, b) => a.map((value, index) => (value + b[index]) / 2);
function freeze(value) {
  if (value && typeof value === "object") { Object.freeze(value); for (const child of Object.values(value)) freeze(child); }
  return value;
}
function samplePair(a, b, time = .25, events = []) {
  return Motion.sample(Motion.build(round(a, b, events)), 0, time, telemetry(a));
}

test("anonymous single projectile interpolates all three coordinates and marks its inference", () => {
  const result = samplePair([p(0, 10, 20)], [p(100, 50, 80)]).projectiles[0];
  assert.deepEqual(xyz(result), [50, 30, 50]);
  assert.equal(result.display_motion.mode, "inferred_unique");
  assert.equal(result.display_motion.inferred, true);
  assert.equal(result.display_motion.display_only, true);
  assert.equal(result.entity_id, null);
  assert.deepEqual(result.trail, []);
});

test("endpoints are exact, and times outside an interval never extrapolate", () => {
  const a = [p(10, 30, 50)], b = [p(110, 230, 350)];
  for (const time of [-5, 0]) assert.deepEqual(xyz(samplePair(a, b, time).projectiles[0]), xyz(a[0]));
  for (const time of [.5, 5]) assert.deepEqual(xyz(samplePair(a, b, time).projectiles[0]), xyz(b[0]));
});

test("exact string IDs preserve identity through a crossing and do not infer", () => {
  const a = [p(-100, 0, 0, "Flashbang", { entity_id: "9007199254740993" }), p(100, 0, 0, "Flashbang", { entity_id: "9007199254740995" })];
  const b = [p(-80, 0, 0, "Flashbang", { entity_id: "9007199254740995" }), p(80, 0, 0, "Flashbang", { entity_id: "9007199254740993" })];
  const result = samplePair(a, b).projectiles;
  assert.deepEqual(result.map(xyz), [[-10, 0, 0], [10, 0, 0]]);
  assert.ok(result.every((r) => r.display_motion.mode === "exact_id" && !r.display_motion.inferred));
});

test("different IDs, missing IDs, and changed types are never anonymous fallbacks", () => {
  const a = [p(0, 0, 0, "Flashbang", { entity_id: "a" })];
  for (const b of [[p(100, 0, 0, "Flashbang", { entity_id: "b" })], [p(100, 0, 0, "Flashbang")],
    [p(100, 0, 0, "Smoke Grenade", { entity_id: "a" })]]) {
    const result = samplePair(a, b).projectiles[0];
    assert.deepEqual(xyz(result), [0, 0, 0]);
    assert.equal(result.display_motion.mode, "held");
  }
});

test("duplicate IDs and duplicate anonymous positions cannot create links", () => {
  for (const extra of [{ entity_id: "same" }, {}]) {
    const a = [p(0, 0, 0, "Flashbang", extra), p(0, 0, 0, "Flashbang", extra)];
    const b = [p(100, 0, 0, "Flashbang", extra), p(120, 0, 0, "Flashbang", extra)];
    assert.ok(samplePair(a, b).projectiles.every((r) => r.display_motion.mode === "held"));
  }
});

test("unsafe numeric source IDs refuse identity inference", () => {
  const a = [p(0, 0, 0, "Flashbang", { grenadeEntityID: 9007199254740992 })];
  const b = [p(100, 0, 0, "Flashbang", { grenadeEntityID: 9007199254740994 })];
  assert.equal(samplePair(a, b).projectiles[0].display_motion.mode, "held");
});

test("ambiguous crossings and equidistant targets hold their recorded position", () => {
  const a = [p(-100, 0, 0, "Flashbang"), p(100, 0, 0, "Flashbang")];
  const b = [p(-10, 0, 0, "Flashbang"), p(10, 0, 0, "Flashbang")];
  const result = samplePair(a, b).projectiles;
  assert.deepEqual(result.map(xyz), a.map(xyz));
  assert.ok(result.every((r) => r.display_motion.mode === "held"));
});

test("mutual nearest and a clear margin prevent multiple sources choosing one target", () => {
  const a = [p(0), p(100)], b = [p(20), p(1000)];
  const result = samplePair(a, b).projectiles;
  assert.equal(result[0].display_motion.mode, "inferred_unique");
  assert.equal(result[1].display_motion.mode, "held");
  assert.deepEqual(xyz(result[1]), xyz(a[1]));
});

test("stationary canisters pair first and shuffled arrays give the same mapping", () => {
  const a = [p(0), p(100), p(5000)], b = [p(300), p(5000), p(0)];
  const forward = samplePair(a, b).projectiles;
  const shuffled = samplePair([...a].reverse(), [...b].reverse()).projectiles.reverse();
  assert.deepEqual(forward, shuffled);
  assert.deepEqual(forward.map(xyz), [[0, 0, 0], [200, 0, 0], [5000, 0, 0]]);
  assert.deepEqual(forward.map((r) => r.display_motion.mode), ["stationary", "inferred_unique", "stationary"]);
});

test("anonymous births and disappearances are not linked or shown early", () => {
  const a = [p(0)], b = [p(100), p(200)];
  const result = samplePair(a, b).projectiles;
  assert.equal(result.length, 1);
  assert.deepEqual(xyz(result[0]), [0, 0, 0]);
  assert.equal(result[0].display_motion.mode, "held");
  assert.deepEqual(samplePair(a, []).projectiles.map(xyz), [[0, 0, 0]]);
  assert.deepEqual(samplePair([], b).projectiles, []);
});

test("a same-kind throw guards against old-to-new connections while other kinds can move", () => {
  const a = [p(0), p(1000, 0, 0, "Flashbang")], b = [p(100), p(1100, 0, 0, "Flashbang")];
  const result = samplePair(a, b, .25, [{ type: "grenade_throw", time: .3, grenadeType: "Smoke Grenade" }]).projectiles;
  assert.equal(result[0].display_motion.mode, "held");
  assert.equal(result[1].display_motion.mode, "inferred_unique");
});

test("active smoke entities stay pinned, but a future contaminated smoke is ignored", () => {
  const a = [p(0)], b = [p(100)];
  for (const [startTick, expected] of [[900, "held"], [1500, "inferred_unique"]]) {
    const r = round(a, b);
    r.frames[0].utility.smokes = [{ x: 1, y: 0, z: 0, startTick }];
    assert.equal(Motion.sample(Motion.build(r), 0, .25, telemetry(a)).projectiles[0].display_motion.mode, expected);
  }
});

test("long, reversed, and zero-time intervals cannot interpolate", () => {
  for (const time of [.8, -.5, 0]) {
    const r = { frames: [frame(0, [p(0)]), frame(time, [p(100)])] };
    assert.equal(Motion.sample(Motion.build(r), 0, .25, telemetry([p(0)])).projectiles[0].display_motion.mode, "held");
  }
});

test("teleports including vertical jumps cannot interpolate even with exact IDs", () => {
  for (const extra of [{}, { entity_id: "a" }]) {
    const a = [p(0, 0, 0, "Flashbang", extra)], b = [p(0, 0, 5000, "Flashbang", extra)];
    assert.equal(samplePair(a, b).projectiles[0].display_motion.mode, "held");
  }
});

test("missing or malformed adjacent snapshots and nonfinite query times hold", () => {
  const a = frame(0, [p(0)]);
  for (const b of [null, {}, { ...frame(.5, [p(100)]), tick: NaN }, frame(.5, null), frame(.5, [p(NaN)])]) {
    assert.equal(Motion.sample(Motion.build({ frames: [a, b] }), 0, .25, telemetry([p(0)])).projectiles[0].display_motion.mode, "held");
  }
  assert.equal(samplePair([p(0)], [p(100)], NaN).projectiles[0].display_motion.reason, "invalid_time");
});

test("private filtering, unknown masks, and simulation empty output cannot be rehydrated", () => {
  const index = Motion.build(round([p(0), p(2000)], [p(100), p(2100)]));
  const filtered = { ...telemetry([p(2000)]), known: { projectiles: false }, private: true };
  const result = Motion.sample(index, 0, .25, filtered);
  assert.equal(result.known, filtered.known);
  assert.equal(result.private, true);
  assert.equal(result.projectiles.length, 1);
  assert.deepEqual(xyz(result.projectiles[0]), [2050, 0, 0]);
  assert.deepEqual(Motion.sample(index, 0, .25, { ...filtered, projectiles: [] }).projectiles, []);
});

test("source and telemetry remain unchanged; seeking is stateless", () => {
  const raw = freeze(round([p(0, 10, 30)], [p(100, 30, 50)]));
  const input = freeze(telemetry(raw.frames[0].utility.projectiles));
  const original = JSON.stringify({ raw, input });
  const index = Motion.build(raw);
  const first = Motion.sample(index, 0, .1, input);
  Motion.sample(index, 0, .4, input);
  Motion.sample(index, 1, .6, input);
  assert.deepEqual(Motion.sample(index, 0, .1, input), first);
  assert.equal(JSON.stringify({ raw, input }), original);
  assert.notEqual(first, input);
  assert.notEqual(first.projectiles[0], input.projectiles[0]);
});

// Actual ESTA ENCE/FaZe Dust II demo 00e7fec9-cee0-430f-80f4-6b50443ceacd,
// round 1, frames 105/106; pinned commit 0e81f74d480689a83f6e1e90835c1eb6f7aa0de2.
// CC-BY-SA-4.0, https://github.com/pnxenopoulos/esta (Xenopoulos et al.).
const realPair = {
  frames: [
    { time: 53.1496062992126, tick: 9265, utility: { smokes: [{ grenadeEntityID: "7955079406183515637", startTick: 7899,
      x: -1220.234130859375, y: 2267.44384765625, z: 6.022602081298828 }], fires: [], projectiles: [
      p(-1220.25, 2267.4375, 6), p(322.90625, 1511.125, 121.40625), p(326.4375, 1746.625, 135.9375, "Molotov")] } },
    { time: 53.653543307086615, tick: 9329, utility: { smokes: [{ grenadeEntityID: "7955079406183515637", startTick: 7899,
      x: -1220.234130859375, y: 2267.44384765625, z: 6.022602081298828 }], fires: [], projectiles: [
      p(-1220.25, 2267.4375, 6), p(423.25, 1809.125, 164.03125), p(553.5625, 2178.0625, 138.46875, "Molotov")] } }
  ], events: []
};

test("real samples keep an active smoke anchored while smoothing another smoke and molotov", () => {
  const [a, b] = realPair.frames;
  const result = Motion.sample(Motion.build(realPair), 0, (a.time + b.time) / 2, telemetry(a.utility.projectiles)).projectiles;
  assert.equal(result[0].display_motion.mode, "stationary");
  assert.deepEqual(xyz(result[0]), xyz(a.utility.projectiles[0]));
  for (const i of [1, 2]) {
    assert.equal(result[i].display_motion.mode, "inferred_unique");
    assert.deepEqual(xyz(result[i]), mid(xyz(a.utility.projectiles[i]), xyz(b.utility.projectiles[i])));
    assert.equal(result[i].entity_id, null);
    assert.deepEqual(result[i].trail, []);
  }
});

test("last sample remains factual with no extrapolation beyond observed data", () => {
  const [a, b] = realPair.frames;
  const result = Motion.sample(Motion.build(realPair), 1, b.time + .2, telemetry(b.utility.projectiles));
  assert.deepEqual(result.projectiles.map(xyz), b.utility.projectiles.map(xyz));
  assert.ok(result.projectiles.every((r) => r.display_motion.reason === "last_snapshot"));
});
