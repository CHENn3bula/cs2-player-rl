/* Run: node --test web/telemetry.test.cjs. The fixture contains attributed real ESTA excerpts. */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fixture = require("./telemetry.fixture.json");
const telemetry = require("./telemetry.js");
const { utilityInventory, buildTelemetry, telemetryAt } = telemetry;

function frame(time = 10) {
  return { time, tick: 1000, players: [], utility: { smokes: [], fires: [], projectiles: [] } };
}
function shot(time = 10, team = "T") {
  return { type: "weapon_fire", time, playerX: 12, playerY: 34, playerZ: 56,
    playerViewX: 90, playerSide: team, playerSteamID: "76561197989423065",
    playerName: "Example", weapon: "AK-47", weaponClass: "Rifle" };
}

test("real double-flash inventory counts two flashes from one entry", () => {
  const result = utilityInventory(fixture.double_flash_player);
  assert.equal(result.known, true);
  assert.equal(result.counts.flash, 2);
  assert.equal(fixture.double_flash_player.inventory.filter((item) => item.weaponName === "Flashbang").length, 1);
});

test("non-flash presence survives unavailable ammo while flash quantity remains unknown", () => {
  const result = utilityInventory({ inventory: [
    { weaponName: "Smoke Grenade", ammoInMagazine: 1, ammoInReserve: -1 },
    { weaponName: "Flashbang", ammoInMagazine: 1, ammoInReserve: -1 },
    { weaponName: "Molotov", ammoInMagazine: 1, ammoInReserve: -1 },
    { weaponName: "Incendiary Grenade", ammoInMagazine: 1, ammoInReserve: 0 },
  ] });
  assert.equal(result.known, true);
  assert.equal(result.counts.smoke, 1);
  assert.equal(result.counts.flash, null);
  assert.equal(result.counts.fire, 2);
  assert.equal(result.total, null);
});

test("absent and simulation inventories are unknown, recorded empty inventory is zero", () => {
  assert.equal(utilityInventory({}).known, false);
  assert.equal(utilityInventory({}).counts.smoke, null);
  assert.equal(utilityInventory({ inventory: [] }).total, 0);
  assert.equal(utilityInventory(fixture.double_flash_player, { simulated: true }).total, null);
  assert.equal(utilityInventory(fixture.double_flash_player, { simulated: true }).known, false);
});

test("inventory totals do not double-count the combined fire alias", () => {
  const result = utilityInventory({ inventory: [{ weaponName: "Molotov" }, { weaponName: "HE Grenade" }] });
  assert.equal(result.counts.fire, 1);
  assert.equal(result.total, 2);
});

test("malformed inventory records do not claim known zero utility", () => {
  const result = utilityInventory({ inventory: [null] });
  assert.equal(result.known, true);
  assert.equal(result.complete, false);
  assert.equal(result.counts.smoke, null);
  assert.equal(result.total, null);
});

test("real firearm shot preserves recorded origin and yaw without invented endpoint", () => {
  const index = buildTelemetry(fixture.round, fixture.source);
  const source = fixture.round.events.find((event) => event.type === "weapon_fire" && event.weaponClass === "Pistols");
  const result = telemetryAt(index, source.time + .1, fixture.round.frames[0]);
  const mark = result.shots.find((event) => event.player_id === source.playerSteamID);
  assert.ok(mark);
  assert.deepEqual([mark.x, mark.y, mark.z, mark.yaw], [source.playerX, source.playerY, source.playerZ, source.playerViewX]);
  assert.equal(mark.age, (source.time + .1) - source.time);
  assert.equal("endpoint" in mark, false);
  assert.equal("target" in mark, false);
});

test("grenade and knife weapon_fire records never produce gunshots", () => {
  const index = buildTelemetry({ events: [shot(), { ...shot(), weapon: "Flashbang", weaponClass: "Grenade" },
    { ...shot(), weapon: "Knife", weaponClass: "Unknown" }] });
  assert.equal(telemetryAt(index, 10, frame()).shots.length, 1);
  assert.equal(index.diagnostics.nongunWeaponFiresExcluded, 2);
});

test("event windows are causal, expire, and work when scrubbing backwards", () => {
  const index = buildTelemetry({ events: [shot(20), shot(10)] });
  assert.equal(telemetryAt(index, 9.99, frame(0)).shots.length, 0);
  assert.equal(telemetryAt(index, 10.2, frame()).shots.length, 1);
  assert.equal(telemetryAt(index, 11, frame()).shots.length, 0);
  assert.equal(telemetryAt(index, 20.2, frame()).shots[0].time, 20);
  assert.equal(telemetryAt(index, 10.2, frame()).shots[0].time, 10);
});

test("source seconds resetting at plant is never used as the event timeline", () => {
  const event = { ...shot(), tick: 1400, seconds: 0.1 };
  delete event.time;
  const index = buildTelemetry({ freeze_end_tick: 100, events: [event] }, { tick_rate: 100 });
  assert.equal(index.shots[0].time, 13);
  assert.equal(telemetryAt(index, .1, frame(0)).shots.length, 0);
  assert.equal(telemetryAt(index, 13, frame()).shots.length, 1);
});

test("grenade throw uses its recorded origin, never destroy location or destroy time", () => {
  const event = fixture.round.events.find((event) => event.type === "grenade_throw");
  const index = buildTelemetry({ ...fixture.round, events: [event] }, fixture.source);
  assert.equal(index.pulses.length, 1);
  assert.equal(index.pulses[0].phase, "throw");
  assert.deepEqual([index.pulses[0].x, index.pulses[0].y, index.pulses[0].z], [event.throwerX, event.throwerY, event.throwerZ]);
  const destroyTime = (event.destroyTick - fixture.round.freeze_end_tick) / fixture.source.tick_rate;
  assert.equal(telemetryAt(index, destroyTime, frame()).pulses.length, 0);
});

test("real flash affected marker is at its victim with team derived from first roster", () => {
  const index = buildTelemetry(fixture.round, fixture.source);
  const event = fixture.round.events.find((event) => event.type === "flash");
  const observed = telemetryAt(index, event.time + .1, fixture.round.frames[1]);
  const hit = observed.pulses.find((pulse) => pulse.phase === "affected" && pulse.player_id === event.playerSteamID);
  assert.ok(hit);
  assert.deepEqual([hit.x, hit.y, hit.z], [event.playerX, event.playerY, event.playerZ]);
  assert.ok(["T", "CT"].includes(hit.team));
  assert.equal(hit.duration, event.flashDuration);
  assert.equal(hit.kind, "flash");
});

test("friendly perspective hides enemy shots and all unobserved world effects", () => {
  const index = buildTelemetry({ events: [shot(10, "T"), shot(10, "CT")] });
  const current = frame();
  current.utility.smokes.push({ x: 1, y: 2, z: 3, startTick: 900 });
  const result = telemetryAt(index, 10.1, current, "T");
  assert.equal(result.shots.length, 1);
  assert.equal(result.shots[0].team, "T");
  assert.deepEqual(result.smokes, []);
  assert.equal(result.known.smokes, false);
  assert.equal(result.known.shots, true);
});

test("real recorded effect positions are preserved without radius or trajectories", () => {
  const index = buildTelemetry(fixture.round, fixture.source);
  const current = fixture.round.frames[1];
  const result = telemetryAt(index, current.time, current);
  assert.equal(result.smokes.length, 1);
  assert.equal(result.fires.length, 1);
  assert.equal(result.projectiles.length, 3);
  assert.deepEqual([result.fires[0].x, result.fires[0].y, result.fires[0].z],
    [current.utility.fires[0].x, current.utility.fires[0].y, current.utility.fires[0].z]);
  assert.equal("radius" in result.smokes[0], false);
  assert.equal("trajectory" in result.projectiles[0], false);
});

test("real future smoke contamination is suppressed and marked unknown", () => {
  const current = fixture.future_smoke_frame;
  assert.ok(current.utility.smokes.some((smoke) => smoke.startTick > current.tick));
  const result = telemetryAt(buildTelemetry({ events: [] }), current.time, current);
  assert.ok(result.diagnostics.futureSmokesExcluded > 0);
  assert.equal(result.known.smokes, false);
  assert.ok(result.smokes.every((smoke) => smoke.start_tick <= current.tick));
});

test("future frames and invalid coordinates cannot leak effects or become origin zero", () => {
  const current = frame(20);
  current.utility.smokes.push({ x: 1, y: 2, z: 3, startTick: 900 });
  assert.equal(telemetryAt(buildTelemetry({ events: [] }), 10, current).smokes.length, 0);
  current.time = 10;
  current.utility.smokes = [{ x: null, y: 2, z: 3 }, null];
  const result = telemetryAt(buildTelemetry({ events: [] }), 10, current);
  assert.equal(result.smokes.length, 0);
  assert.equal(result.known.smokes, false);
  assert.equal(result.diagnostics.invalidEffectsExcluded, 2);
});

test("simulation cannot present recorded inventory, shots or world effects as supported", () => {
  const index = buildTelemetry(fixture.round, { ...fixture.source, kind: "simulation" });
  const current = fixture.round.frames[1];
  const result = telemetryAt(index, current.time, current);
  assert.ok(Object.values(result.known).every((known) => known === false));
  for (const key of ["smokes", "fires", "projectiles", "shots", "pulses"]) assert.deepEqual(result[key], []);
});

test("malformed event rows are counted and excluded without aborting replay", () => {
  const index = buildTelemetry({ events: [null, 7, [], { ...shot(), time: null }] });
  assert.equal(index.shots.length, 0);
  assert.equal(index.diagnostics.invalidEventsExcluded, 4);
});

function projectileFrame(time, records) {
  return { ...frame(time), tick: 1000 + time * 100, utility: { smokes: [], fires: [], projectiles: records } };
}
function trackedProjectile(id, x) {
  return { entity_id: id, projectileType: "Flashbang", x, y: 20, z: 30 };
}

test("same-entity trails contain only exact past samples within three seconds", () => {
  const frames = [0, 1, 2, 3, 4, 5].map((time) => projectileFrame(time, [trackedProjectile("precise-entity", time * 10)]));
  const index = buildTelemetry({ frames, events: [] }, { tick_rate: 100 });
  const marker = telemetryAt(index, 4.2, frames[4]).projectiles[0];
  assert.equal(marker.entity_id, "precise-entity");
  assert.deepEqual(marker.trail.map((point) => point.time), [2, 3, 4]);
  assert.deepEqual(marker.trail.map((point) => point.x), [20, 30, 40]);
  assert.ok(marker.trail.every((point) => point.time <= 4.2 && point.tick <= frames[4].tick));
  assert.equal(marker.effect_age, null);
  assert.ok(Math.abs(marker.sample_age - .2) < 1e-9);
});

test("scrubbing backwards never reuses a later entity path", () => {
  const frames = [0, 1, 2, 3].map((time) => projectileFrame(time, [trackedProjectile("same", time)]));
  const index = buildTelemetry({ frames, events: [] });
  assert.equal(telemetryAt(index, 3, frames[3]).projectiles[0].trail.length, 4);
  assert.deepEqual(telemetryAt(index, 1, frames[1]).projectiles[0].trail.map((point) => point.time), [0, 1]);
});

test("two nearby same-type projectiles never borrow each other's history", () => {
  const frames = [0, 1, 2].map((time) => projectileFrame(time, [
    trackedProjectile("A", time), trackedProjectile("B", 10 - time),
  ]));
  const markers = telemetryAt(buildTelemetry({ frames, events: [] }), 2, frames[2]).projectiles;
  assert.deepEqual(markers.find((marker) => marker.entity_id === "A").trail.map((point) => point.x), [0, 1, 2]);
  assert.deepEqual(markers.find((marker) => marker.entity_id === "B").trail.map((point) => point.x), [10, 9, 8]);
});

test("unidentified source projectiles get no fabricated identity or path", () => {
  const current = fixture.round.frames[1];
  const markers = telemetryAt(buildTelemetry(fixture.round, fixture.source), current.time, current).projectiles;
  assert.ok(markers.length > 0);
  assert.ok(markers.every((marker) => marker.entity_id === null && marker.trail.length === 0));
});

test("unsafe numeric IDs are refused while exact HTTP string identities survive", () => {
  const precise = "7955079406183515637";
  const first = projectileFrame(1, [trackedProjectile(Number(precise), 1)]);
  const unsafe = telemetryAt(buildTelemetry({ frames: [first], events: [] }), 1, first).projectiles[0];
  assert.equal(unsafe.entity_id, null);
  assert.deepEqual(unsafe.trail, []);
  const second = projectileFrame(1, [trackedProjectile(precise, 1)]);
  const exact = telemetryAt(buildTelemetry({ frames: [second], events: [] }), 1, second).projectiles[0];
  assert.equal(exact.entity_id, precise);
  assert.equal(exact.trail.length, 1);
});

test("missing or duplicate-identity snapshots break trail continuity", () => {
  const frames = [projectileFrame(0, [trackedProjectile("A", 0)]), projectileFrame(1, []),
    projectileFrame(2, [trackedProjectile("A", 2)]),
    projectileFrame(3, [trackedProjectile("A", 3), trackedProjectile("A", 4)]),
    projectileFrame(4, [trackedProjectile("A", 5)])];
  const index = buildTelemetry({ frames, events: [] });
  assert.deepEqual(telemetryAt(index, 2, frames[2]).projectiles[0].trail.map((point) => point.time), [2]);
  assert.ok(telemetryAt(index, 3, frames[3]).projectiles.every((marker) => marker.trail.length === 0));
  assert.deepEqual(telemetryAt(index, 4, frames[4]).projectiles[0].trail.map((point) => point.time), [4]);
});

test("smoke effect age derives from valid start tick; unknown fire start remains null", () => {
  const current = frame(10);
  current.tick = 2000;
  current.utility.smokes = [{ grenadeEntityID: "7955079406183515637", startTick: 1750, x: 1, y: 2, z: 3 }];
  current.utility.fires = [{ uniqueID: "4990765271833742716", x: 4, y: 5, z: 6 }];
  const result = telemetryAt(buildTelemetry({ events: [], frames: [current] }, { tick_rate: 100 }), 10.5, current);
  assert.equal(result.smokes[0].effect_age, 3);
  assert.equal(result.smokes[0].age, 3);
  assert.equal(result.smokes[0].sample_age, .5);
  assert.equal(result.fires[0].entity_id, "4990765271833742716");
  assert.equal(result.fires[0].effect_age, null);
  assert.equal(result.fires[0].age, .5);
});

test("future contaminated smoke samples never enter an identified trail", () => {
  const old = frame(9), current = frame(10);
  old.tick = 1900; current.tick = 2000;
  old.utility.smokes = [{ grenadeEntityID: "known", startTick: 1950, x: 1, y: 2, z: 3 }];
  current.utility.smokes = [{ grenadeEntityID: "known", startTick: 1950, x: 1, y: 2, z: 3 }];
  const index = buildTelemetry({ events: [], frames: [old, current] }, { tick_rate: 100 });
  assert.deepEqual(telemetryAt(index, 10, current).smokes[0].trail.map((point) => point.time), [10]);
  assert.equal(telemetryAt(index, 9, old).smokes.length, 0);
});
