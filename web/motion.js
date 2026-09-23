/* Display-only interpolation. Anonymous links are visual guesses, never RL data. */
(function installMotion(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IGLMotion = api;
})(typeof globalThis === "object" ? globalThis : this, function createMotion() {
  "use strict";

  const MAX_GAP = .75;
  const MAX_SPEED = 2000;
  const DISTANCE_MARGIN = 24;
  const UNIQUENESS_MARGIN = 48;
  const SMOKE_PIN_DISTANCE = 18;
  const numeric = (value) => typeof value === "number" && Number.isFinite(value);
  const token = (value) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "").replace(/^weapon/, "");

  function kind(value) {
    switch (token(value)) {
      case "smoke": case "smokegrenade": return "smoke";
      case "flash": case "flashbang": return "flash";
      case "he": case "hegrenade": case "highexplosivegrenade": return "he";
      case "molotov": return "molotov";
      case "incendiary": case "incendiarygrenade": case "incgrenade": return "incendiary";
      case "decoy": case "decoygrenade": return "decoy";
      default: return null;
    }
  }

  function identity(record) {
    for (const field of ["entity_id", "grenadeEntityID", "uniqueID", "entityId", "entityID"]) {
      const value = record?.[field];
      if (typeof value === "string" && value.trim() && value !== "-1") return value;
      if (typeof value === "bigint" && value >= 0n) return String(value);
      if (Number.isSafeInteger(value) && value >= 0) return String(value);
    }
    return null;
  }

  function point(record) {
    if (![record?.x, record?.y, record?.z].every(numeric)) return null;
    return { x: record.x, y: record.y, z: record.z };
  }

  function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z); }
  function signature(record) {
    return JSON.stringify([record.kind, record.id, record.x, record.y, record.z]);
  }

  function describe(record, ordinal = 0) {
    const xyz = point(record);
    const type = kind(record?.projectileType ?? record?.kind ?? record?.weapon);
    if (!xyz || !type) return null;
    const id = identity(record);
    // An unusable supplied ID is not evidence that a projectile is anonymous.
    // In particular, unsafe JS integers have already lost identity precision.
    const invalidIdentity = id === null && ["entity_id", "grenadeEntityID", "uniqueID", "entityId", "entityID"]
      .some((field) => record?.[field] != null && record[field] !== "" && record[field] !== -1 && record[field] !== "-1");
    const result = { ...xyz, kind: type, id, invalidIdentity, ordinal };
    result.signature = signature(result);
    return result;
  }

  function snapshot(frame) {
    if (!frame || !numeric(frame.time) || !numeric(frame.tick) || !Array.isArray(frame.utility?.projectiles)) return null;
    const records = frame.utility.projectiles.map(describe).filter(Boolean);
    const idCounts = new Map(), pointCounts = new Map();
    for (const record of records) {
      if (record.id !== null) idCounts.set(record.id, (idCounts.get(record.id) ?? 0) + 1);
      pointCounts.set(record.signature, (pointCounts.get(record.signature) ?? 0) + 1);
    }
    for (const record of records) {
      record.blocked = record.invalidIdentity || pointCounts.get(record.signature) !== 1
        || (record.id !== null && idCounts.get(record.id) !== 1);
    }
    const smokes = (Array.isArray(frame.utility?.smokes) ? frame.utility.smokes : [])
      .filter((smoke) => point(smoke) && (!numeric(smoke.startTick) || smoke.startTick <= frame.tick));
    return { time: frame.time, tick: frame.tick, records, smokes };
  }

  function nearActiveSmoke(record, frame) {
    return record.kind === "smoke" && frame.smokes.some((smoke) => distance(record, smoke) <= SMOKE_PIN_DISTANCE);
  }

  function uniqueBest(record, alternatives, budget) {
    const candidates = alternatives.map((other) => ({ other, distance: distance(record, other) }))
      .filter((candidate) => candidate.distance <= budget)
      .sort((a, b) => a.distance - b.distance);
    if (!candidates.length) return null;
    if (candidates.length > 1) {
      const margin = Math.max(UNIQUENESS_MARGIN, candidates[0].distance * .25);
      if (candidates[1].distance - candidates[0].distance < margin) return null;
    }
    return candidates[0].other;
  }

  function intervalLinks(before, after, throws) {
    const links = new Map();
    if (!before || !after) return { links, reason: "missing_snapshot" };
    const gap = after.time - before.time;
    if (!(gap > 0 && gap <= MAX_GAP) || !(after.tick > before.tick)) return { links, reason: "invalid_or_long_gap" };
    const budget = MAX_SPEED * gap + DISTANCE_MARGIN;
    const usedBefore = new Set(), usedAfter = new Set();
    const add = (a, b, mode) => {
      links.set(a.signature, { from: a, to: b, mode, source_time: before.time, target_time: after.time });
      usedBefore.add(a); usedAfter.add(b);
    };

    // True identities take precedence; duplicate/recycled-in-frame IDs are refused.
    for (const a of before.records) {
      if (a.blocked || a.id === null) continue;
      const b = after.records.find((record) => !record.blocked && record.id === a.id);
      if (!b || b.kind !== a.kind || distance(a, b) > budget) continue;
      if (nearActiveSmoke(a, before) && distance(a, b) > SMOKE_PIN_DISTANCE) continue;
      add(a, b, "exact_id");
    }

    // Persistent stationary canisters must be paired before moving objects.
    // This remains order independent even when Go reorders projectile arrays.
    for (const a of before.records) {
      if (a.blocked || a.id !== null || usedBefore.has(a)) continue;
      const candidates = after.records.filter((b) => !b.blocked && b.id === null && !usedAfter.has(b)
        && a.kind === b.kind && a.x === b.x && a.y === b.y && a.z === b.z);
      if (candidates.length === 1) add(a, candidates[0], "stationary");
    }

    for (const type of new Set(before.records.map((record) => record.kind))) {
      // A same-kind throw between observations can replace an old grenade.
      // Do not invent an old-to-new trajectory on that interval.
      if (throws.some((event) => event.kind === type && event.time > before.time && event.time <= after.time)) continue;
      const left = before.records.filter((a) => !a.blocked && a.id === null && a.kind === type && !usedBefore.has(a));
      const right = after.records.filter((b) => !b.blocked && b.id === null && b.kind === type && !usedAfter.has(b));
      // A birth or disappearance is another ambiguous identity transition.
      if (left.length !== right.length || left.length === 0) continue;
      const forward = new Map(left.map((a) => [a, uniqueBest(a, right, budget)]));
      const backward = new Map(right.map((b) => [b, uniqueBest(b, left, budget)]));
      for (const a of left) {
        const b = forward.get(a);
        if (!b || backward.get(b) !== a || usedAfter.has(b)) continue;
        // A sampled smoke entity may persist after activation. Keep it anchored,
        // rather than making it fly toward a different anonymous smoke.
        if (nearActiveSmoke(a, before)) continue;
        add(a, b, "inferred_unique");
      }
    }
    return { links, reason: "unmatched_or_ambiguous" };
  }

  function build(round) {
    const frames = (Array.isArray(round?.frames) ? round.frames : []).map(snapshot);
    const throws = (Array.isArray(round?.events) ? round.events : [])
      .filter((event) => event?.type === "grenade_throw" && numeric(event.time))
      .map((event) => ({ time: event.time, kind: kind(event.grenadeType) }));
    const intervals = frames.map((current, index) => index + 1 < frames.length
      ? intervalLinks(current, frames[index + 1], throws) : { links: new Map(), reason: "last_snapshot" });
    return { frames, intervals, display_only: true,
      parameters: { max_gap: MAX_GAP, max_speed: MAX_SPEED, distance_margin: DISTANCE_MARGIN,
        uniqueness_margin: UNIQUENESS_MARGIN, smoke_pin_distance: SMOKE_PIN_DISTANCE } };
  }

  function sample(index, frameIndex, time, telemetry) {
    if (!telemetry || typeof telemetry !== "object") return telemetry;
    if (!Array.isArray(telemetry.projectiles)) return { ...telemetry };
    const interval = Number.isInteger(frameIndex) ? index?.intervals?.[frameIndex] : null;
    const current = Number.isInteger(frameIndex) ? index?.frames?.[frameIndex] : null;
    const projectiles = telemetry.projectiles.map((marker) => {
      const description = describe(marker);
      const link = description && interval?.links.get(description.signature);
      const held = { ...marker, display_motion: { mode: "held", display_only: true, inferred: false,
        alpha: 0, source_time: current?.time ?? null, target_time: null,
        reason: !numeric(time) ? "invalid_time" : interval?.reason ?? "missing_snapshot" } };
      if (!link || !numeric(time)) return held;
      const alpha = Math.min(1, Math.max(0, (time - link.source_time) / (link.target_time - link.source_time)));
      return { ...marker,
        x: link.from.x + (link.to.x - link.from.x) * alpha,
        y: link.from.y + (link.to.y - link.from.y) * alpha,
        z: link.from.z + (link.to.z - link.from.z) * alpha,
        display_motion: { mode: link.mode, display_only: true, inferred: link.mode === "inferred_unique",
          alpha, source_time: link.source_time, target_time: link.target_time } };
    });
    // Never add markers from the index: filtered friendly views and empty
    // simulation telemetry must remain filtered/empty.
    return { ...telemetry, projectiles };
  }

  return { build, sample, MAX_GAP, MAX_SPEED };
});
