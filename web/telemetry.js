/* Factual ESTA telemetry: sampled positions and event origins, never inferred paths. */
(function installTelemetry(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IGLTelemetry = api;
})(typeof globalThis === "object" ? globalThis : this, function createTelemetry() {
  "use strict";

  const UTILITY_KEYS = ["smoke", "flash", "he", "molotov", "incendiary", "decoy"];
  const SHOT_WINDOW = 0.65;
  const PULSE_WINDOW = 1.15;
  const TRAIL_WINDOW = 3;
  const FIREARM_CLASSES = new Set(["pistol", "pistols", "rifle", "rifles", "smg", "heavy", "shotgun", "shotguns", "machinegun", "machineguns"]);
  const token = (value) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const numeric = (value) => typeof value === "number" && Number.isFinite(value);
  const nonnegativeInteger = (value) => Number.isInteger(value) && value >= 0;

  function utilityKind(name) {
    switch (token(name).replace(/^weapon/, "")) {
      case "smoke": case "smokegrenade": return "smoke";
      case "flash": case "flashbang": return "flash";
      case "he": case "hegrenade": case "highexplosivegrenade": return "he";
      case "molotov": return "molotov";
      case "incendiary": case "incendiarygrenade": case "incgrenade": return "incendiary";
      case "decoy": case "decoygrenade": return "decoy";
      default: return null;
    }
  }

  function utilityInventory(player, { simulated = false } = {}) {
    const known = !simulated && Array.isArray(player?.inventory);
    const counts = Object.fromEntries(UTILITY_KEYS.map((kind) => [kind, known ? 0 : null]));
    let unclassified = false;
    let malformed = false;
    if (known) {
      for (const item of player.inventory) {
        if (!item || typeof item !== "object" || typeof item.weaponName !== "string") {
          malformed = true;
          unclassified = true;
          continue;
        }
        const kind = utilityKind(item?.weaponName);
        if (!kind) {
          if (token(item?.weaponClass) === "grenade") unclassified = true;
          continue;
        }
        // Awpy 1.x counts non-flash grenades by inventory entry. Reserve=-1 is
        // common and does not erase a recorded smoke/HE/fire grenade.
        let quantity = 1;
        if (kind === "flash") {
          // One flash inventory entry can represent two carried flashes.
          quantity = nonnegativeInteger(item.ammoInMagazine) && nonnegativeInteger(item.ammoInReserve)
            ? item.ammoInMagazine + item.ammoInReserve : null;
        }
        counts[kind] = counts[kind] === null || quantity === null ? null : counts[kind] + quantity;
      }
    }
    if (malformed) for (const kind of UTILITY_KEYS) counts[kind] = null;
    counts.fire = counts.molotov === null || counts.incendiary === null ? null : counts.molotov + counts.incendiary;
    const total = known && !unclassified && UTILITY_KEYS.every((kind) => counts[kind] !== null)
      ? UTILITY_KEYS.reduce((sum, kind) => sum + counts[kind], 0) : null;
    return { known, counts, total, complete: total !== null, unclassified };
  }

  function position(record, prefix = "") {
    const names = prefix ? [prefix + "X", prefix + "Y", prefix + "Z"] : ["x", "y", "z"];
    const [x, y, z] = names.map((name) => record?.[name]);
    if (!numeric(x) || !numeric(y) || !numeric(z)) return null;
    return { x, y, z };
  }

  function entityId(record) {
    // An already rounded 64-bit JavaScript number cannot be repaired by String().
    // The HTTP server preserves source integers as strings before JSON parsing.
    for (const key of ["entity_id", "grenadeEntityID", "uniqueID", "entityId", "entityID"]) {
      const value = record?.[key];
      if (typeof value === "string" && value.trim() && value !== "-1") return value;
      if (typeof value === "bigint" && value >= 0n) return String(value);
      if (Number.isSafeInteger(value) && value >= 0) return String(value);
    }
    return null;
  }

  function effectKind(category, record) {
    return category === "smokes" ? "smoke" : category === "fires" ? "fire" : utilityKind(record?.projectileType) ?? "unknown";
  }

  function buildEffectHistories(round) {
    const histories = { smokes: new Map(), fires: new Map(), projectiles: new Map() };
    const frames = Array.isArray(round?.frames) ? round.frames : [];
    frames.forEach((frame, frameIndex) => {
      if (!numeric(frame?.time) || !numeric(frame?.tick)) return;
      for (const category of Object.keys(histories)) {
        const records = frame.utility?.[category];
        if (!Array.isArray(records)) continue;
        const counts = new Map();
        for (const record of records) {
          const id = entityId(record);
          if (id !== null) counts.set(id, (counts.get(id) ?? 0) + 1);
        }
        for (const record of records) {
          const id = entityId(record), xyz = position(record);
          if (id === null || !xyz || counts.get(id) !== 1) continue;
          if (numeric(record.startTick) && record.startTick > frame.tick) continue;
          const list = histories[category].get(id) ?? [];
          const previous = list[list.length - 1];
          const kind = effectKind(category, record);
          const continuous = previous && previous.frame_index === frameIndex - 1 && previous.kind === kind
            && previous.time < frame.time && previous.tick < frame.tick;
          // Never bridge a missing frame or an ambiguous/reused entity sample.
          const segment = continuous ? previous.segment : (previous?.segment ?? -1) + 1;
          list.push({ ...xyz, time: frame.time, tick: frame.tick, kind, frame_index: frameIndex, segment });
          histories[category].set(id, list);
        }
      }
    });
    return histories;
  }

  function pastTrail(index, category, id, record, frame, time) {
    if (id === null) return [];
    const samples = index.effectHistories?.[category]?.get(id);
    if (!samples?.length) return [];
    const end = upperBound(samples, Math.min(time, frame.time));
    const current = samples[end - 1];
    const xyz = position(record);
    if (!current || !xyz || current.tick !== frame.tick || current.time !== frame.time
        || current.x !== xyz.x || current.y !== xyz.y || current.z !== xyz.z) return [];
    const result = [];
    for (let cursor = end - 1; cursor >= 0; cursor--) {
      const sample = samples[cursor];
      if (sample.segment !== current.segment || sample.time < time - TRAIL_WINDOW) break;
      if (sample.time > time || sample.tick > frame.tick) continue;
      result.push({ x: sample.x, y: sample.y, z: sample.z, time: sample.time, tick: sample.tick });
    }
    return result.reverse();
  }

  function eventTime(event, round, source) {
    if (numeric(event.time)) return event.time;
    const tick = event.tick ?? event.throwTick;
    if (numeric(tick) && numeric(round.freeze_end_tick) && numeric(source.tick_rate) && source.tick_rate > 0) {
      return (tick - round.freeze_end_tick) / source.tick_rate;
    }
    // Source seconds reset after a plant; using that as a fallback leaks/misorders events.
    return null;
  }

  function buildTelemetry(round, source = {}) {
    const simulated = source.kind === "simulation" || source.simulated === true;
    const known = !simulated && Array.isArray(round?.events);
    const shots = [], pulses = [];
    const diagnostics = { invalidEventsExcluded: 0, nongunWeaponFiresExcluded: 0 };
    const firstRoster = new Map((round?.frames?.[0]?.players ?? []).map((player) => [String(player.id), player.team]));
    function eventTeam(event, prefix) {
      const side = event[prefix + "Side"];
      if (side === "T" || side === "CT") return side;
      const byId = firstRoster.get(String(event[prefix + "SteamID"]));
      if (byId === "T" || byId === "CT") return byId;
      const name = event[prefix + "Team"];
      for (const team of ["T", "CT"]) if (name && round.teams?.[team] === name) return team;
      return null;
    }
    if (known) {
      for (const event of round.events) {
        if (!event || typeof event !== "object" || Array.isArray(event)) {
          diagnostics.invalidEventsExcluded++;
          continue;
        }
        const time = eventTime(event, round, source);
        if (time === null) { diagnostics.invalidEventsExcluded++; continue; }
        if (event.type === "weapon_fire") {
          if (!FIREARM_CLASSES.has(token(event.weaponClass)) || utilityKind(event.weapon)) {
            diagnostics.nongunWeaponFiresExcluded++;
            continue;
          }
          const xyz = position(event, "player");
          if (!xyz) { diagnostics.invalidEventsExcluded++; continue; }
          shots.push({ ...xyz, time, yaw: numeric(event.playerViewX) ? event.playerViewX : null,
            kind: "shot", phase: "fire", team: eventTeam(event, "player"),
            player_id: event.playerSteamID == null ? null : String(event.playerSteamID),
            name: event.playerName ?? null, weapon: event.weapon ?? null,
            display_duration: SHOT_WINDOW });
        } else if (event.type === "grenade_throw") {
          const kind = utilityKind(event.grenadeType);
          const xyz = position(event, "thrower");
          if (!kind || !xyz) { diagnostics.invalidEventsExcluded++; continue; }
          // These fields are the projectile position at the throw callback,
          // not its later landing/destroy point and not a bullet/flight path.
          pulses.push({ ...xyz, time, yaw: null, kind, phase: "throw",
            team: eventTeam(event, "thrower"),
            player_id: event.throwerSteamID == null ? null : String(event.throwerSteamID),
            name: event.throwerName ?? null, weapon: event.grenadeType,
            display_duration: PULSE_WINDOW });
        } else if (event.type === "flash") {
          const xyz = position(event, "player");
          if (!xyz) { diagnostics.invalidEventsExcluded++; continue; }
          pulses.push({ ...xyz, time, yaw: numeric(event.playerViewX) ? event.playerViewX : null,
            kind: "flash", phase: "affected", team: eventTeam(event, "player"),
            player_id: event.playerSteamID == null ? null : String(event.playerSteamID),
            name: event.playerName ?? null, weapon: "Flashbang",
            duration: numeric(event.flashDuration) && event.flashDuration >= 0 ? event.flashDuration : null,
            display_duration: PULSE_WINDOW });
        }
      }
    }
    shots.sort((a, b) => a.time - b.time);
    pulses.sort((a, b) => a.time - b.time);
    return { simulated, known, shots, pulses, diagnostics,
      effectHistories: simulated ? null : buildEffectHistories(round),
      tickRate: numeric(source.tick_rate) ? source.tick_rate : null,
      freezeEndTick: numeric(round?.freeze_end_tick) ? round.freeze_end_tick : null };
  }

  function upperBound(events, time) {
    let low = 0, high = events.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (events[middle].time <= time) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  function recentEvents(events, time, window, perspective) {
    const end = upperBound(events, time);
    const start = upperBound(events, time - window);
    return events.slice(start, end)
      .filter((event) => perspective === "all" || event.team === perspective)
      .map((event) => ({ ...event, age: time - event.time }));
  }

  function telemetryAt(index, time, frame, perspective = "all") {
    const result = { known: { smokes: false, fires: false, projectiles: false, shots: false, pulses: false },
      smokes: [], fires: [], projectiles: [], shots: [], pulses: [],
      diagnostics: { ...index?.diagnostics, futureSmokesExcluded: 0, invalidEffectsExcluded: 0 } };
    if (!index || index.simulated || !numeric(time)) return result;
    const safePerspective = perspective === "T" || perspective === "CT" ? perspective : perspective === "all" ? "all" : "none";
    result.known.shots = index.known && safePerspective !== "none";
    result.known.pulses = index.known && safePerspective !== "none";
    result.shots = recentEvents(index.shots, time, SHOT_WINDOW, safePerspective);
    result.pulses = recentEvents(index.pulses, time, PULSE_WINDOW, safePerspective);
    // The friendly-only view does not imply world-effect visibility or sound.
    if (safePerspective !== "all") return result;
    // A caller accidentally selecting a future snapshot cannot reveal its effects.
    if (!frame || !numeric(frame.time) || frame.time > time) return result;
    for (const category of ["smokes", "fires", "projectiles"]) {
      const records = frame.utility?.[category];
      if (!Array.isArray(records)) continue;
      result.known[category] = true;
      for (const record of records) {
        if (!record || typeof record !== "object" || Array.isArray(record)) {
          result.diagnostics.invalidEffectsExcluded++;
          result.known[category] = false;
          continue;
        }
        if (category === "smokes" && numeric(record.startTick)) {
          // ESTA's shared smoke slice can contain future SmokeStart entries in
          // older snapshots. Filter by snapshot tick, not by playback time.
          if (!numeric(frame.tick) || record.startTick > frame.tick) {
            result.diagnostics.futureSmokesExcluded++;
            result.known.smokes = false;
            continue;
          }
        }
        const xyz = position(record);
        if (!xyz) {
          result.diagnostics.invalidEffectsExcluded++;
          result.known[category] = false;
          continue;
        }
        const kind = effectKind(category, record);
        const id = entityId(record);
        const sampleAge = time - frame.time;
        const effectAge = nonnegativeInteger(record.startTick) && numeric(frame.tick) && record.startTick <= frame.tick
          && numeric(index.tickRate) && index.tickRate > 0 ? (frame.tick - record.startTick) / index.tickRate + sampleAge : null;
        result[category].push({ ...xyz, kind, phase: category === "projectiles" ? "projectile" : "active",
          team: null, player_id: null, name: null, yaw: null,
          time: frame.time, age: effectAge ?? sampleAge, sample_age: sampleAge, effect_age: effectAge,
          entity_id: id, trail: pastTrail(index, category, id, record, frame, time),
          start_tick: numeric(record.startTick) ? record.startTick : null,
          weapon: record.projectileType ?? null });
      }
    }
    return result;
  }

  return { utilityInventory, utilityKind, buildTelemetry, telemetryAt, SHOT_WINDOW, PULSE_WINDOW, TRAIL_WINDOW };
});
