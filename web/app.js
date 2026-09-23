/* Tactical Lab: a dependency-free viewer. Coordinates remain in Hammer units. */
"use strict";

const $ = (id) => document.getElementById(id);
const COLORS = { T: "#e9bc78", CT: "#6bacdd" };
const UTILITY_STYLE = {
  smoke: { label: "S", name: "Smoke", color: "#b6c9d5" },
  flash: { label: "F", name: "Flash", color: "#fff0ad" },
  he: { label: "HE", name: "HE grenade", color: "#e89c81" },
  fire: { label: "M", name: "Molotov / incendiary", color: "#f6a15c" },
  decoy: { label: "D", name: "Decoy", color: "#b59cdd" },
};
const telemetryCache = new WeakMap();
const motionCache = new WeakMap();
const recordedPlayerNumbers = new Map();
const state = {
  catalog: null, match: null, recording: null, roundIndex: 0, frameIndex: 0,
  map: null, mapImage: null, mapImageError: false, playing: false,
  playbackTime: 0, previousAnimation: null, perspective: "all", selectedPlayer: null,
  loading: false, branching: false, simulated: false, loadToken: 0, screenPlayers: [],
  scenarios: [],
  playerNumbers: new Map(), playerIdentityMatch: null,
};
let toastTimer;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}
function finite(value, fallback = 0) { return Number.isFinite(Number(value)) && value !== null ? Number(value) : fallback; }
function alive(player) { return player.alive !== false && finite(player.hp, 100) > 0; }
function currentRound() { return state.match?.rounds?.[state.roundIndex] ?? null; }
function frames() { return currentRound()?.frames ?? []; }
function currentFrame() { return frames()[state.frameIndex] ?? null; }
function frameTime(frame) { return finite(frame?.time); }
function displayTime() {
  const start = frameTime(currentFrame());
  const end = frameTime(frames()[state.frameIndex + 1] || currentFrame());
  return Math.max(start, Math.min(end, finite(state.playbackTime, start)));
}
function startTime() { return frameTime(frames()[0]); }
function duration() { const list = frames(); return list.length ? Math.max(0, frameTime(list[list.length - 1]) - startTime()) : 0; }
function roundNumber() { return currentRound()?.number ?? state.roundIndex + 1; }
function clock(seconds, tenths = false) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "—:—";
  const time = Math.max(0, Number(seconds));
  return `${String(Math.floor(time / 60)).padStart(2, "0")}:${String(Math.floor(time % 60)).padStart(2, "0")}${tenths ? `.${Math.floor((time % 1) * 10)}` : ""}`;
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, error ? 12000 : 5500);
}
async function api(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`The local service returned an unreadable response (${response.status}).`); }
  if (!response.ok || data?.error) {
    const detail = typeof data?.error === "string" ? data.error : data?.error?.message || data?.message || `Request failed (${response.status}).`;
    throw new Error(detail);
  }
  return data;
}
function showEmpty(title, message, error = false) {
  const empty = $("emptyState");
  empty.hidden = false;
  empty.classList.toggle("error", error);
  empty.querySelector("h3").textContent = title;
  empty.querySelector("p").textContent = message;
}
function validateReplay(replay) {
  if (!replay || !Array.isArray(replay.rounds) || !replay.rounds.length) throw new Error("This replay has no rounds. Parse a supported demo and add it to the catalog first.");
  if (!replay.rounds.some((round) => Array.isArray(round.frames) && round.frames.length)) throw new Error("This replay contains no player frames.");
  for (const round of replay.rounds) {
    if (!Array.isArray(round.frames)) round.frames = [];
    if (!Array.isArray(round.events)) round.events = [];
    let previous = -Infinity;
    for (const frame of round.frames) {
      if (!Number.isFinite(Number(frame.time)) || frame.time === null || Number(frame.time) < previous) throw new Error("Replay frame timestamps are missing or out of order.");
      if (!Array.isArray(frame.players)) throw new Error("Replay player data is malformed.");
      previous = Number(frame.time);
    }
  }
  return replay;
}
function metadataHtml(match) {
  const source = match.source || {};
  const label = source.label || source.name || source.filename || source.demo_file || source.demo || source.dataset || match.label;
  const game = String(match.game || "unknown game").toUpperCase();
  const map = match.map || "unknown map";
  const rounds = match.rounds?.length || 0;
  return `<strong>${escapeHtml(game)} · ${escapeHtml(map)}</strong><br>${rounds} round${rounds === 1 ? "" : "s"}${label ? `<br>${escapeHtml(label)}` : ""}`;
}
function populateRounds() {
  $("roundSelect").innerHTML = state.match.rounds.map((round, index) => `<option value="${index}"${round.frames.length ? "" : " disabled"}>${String(round.number ?? index + 1).padStart(2, "0")}${round.winner ? ` · ${escapeHtml(round.winner)} win` : ""}</option>`).join("");
  $("roundSelect").disabled = false;
  $("roundSelect").value = state.roundIndex;
}
function setReplay(match, simulated = false, reset = true) {
  stop();
  state.match = validateReplay(match);
  state.simulated = simulated;
  setPlayerIdentity(state.match, simulated);
  state.selectedPlayer = null;
  if (reset) {
    state.roundIndex = Math.max(0, match.rounds.findIndex((round) => round.frames.length));
    state.frameIndex = 0;
  }
  state.playbackTime = frameTime(currentFrame());
  populateRounds();
  $("sourceMeta").innerHTML = metadataHtml(match);
  $("modeBadge").textContent = simulated ? "SIMULATED BRANCH" : "RECORDED DEMO";
  $("modeBadge").classList.toggle("simulated", simulated);
  $("returnBtn").hidden = !state.recording || !simulated;
  $("emptyState").hidden = true;
  renderEventTicks();
  renderAll();
}
async function loadReplay(value) {
  if (!value) return;
  const token = ++state.loadToken;
  stop();
  state.loading = true;
  setControls();
  showEmpty("Loading replay", "Reading player frames and round events from the local service.");
  try {
    const [kind, ...parts] = value.split(":");
    const id = parts.join(":");
    const replay = await api(`/api/${kind === "simulation" ? "simulations" : "matches"}/${encodeURIComponent(id)}`);
    if (token !== state.loadToken) return;
    state.recording = null;
    setReplay(replay.replay || replay, kind === "simulation");
  } catch (error) {
    if (token !== state.loadToken) return;
    state.match = null;
    showEmpty("Replay unavailable", error.message, true);
    $("dataStatus").textContent = "Replay could not be loaded";
    toast(error.message, true);
  } finally {
    if (token === state.loadToken) {
      state.loading = false;
      setControls();
      drawMap();
    }
  }
}
async function loadMap() {
  try {
    const metadata = await api("/api/map");
    if (![metadata.pos_x, metadata.pos_y, metadata.scale].every((value) => Number.isFinite(Number(value))) || Number(metadata.scale) <= 0) throw new Error("Map projection metadata is invalid.");
    state.map = metadata;
    if (metadata.image) {
      const mapImage = new Image();
      mapImage.onload = () => {
        state.mapImage = mapImage;
        state.mapImageError = false;
        updateMapStatus();
        drawMap();
      };
      mapImage.onerror = () => {
        state.mapImageError = true;
        updateMapStatus();
        drawMap();
      };
      mapImage.src = metadata.image;
    } else state.mapImageError = true;
    updateMapStatus();
    drawMap();
  } catch (error) {
    $("mapStatus").textContent = "MAP PROJECTION UNAVAILABLE";
    toast(`Map unavailable: ${error.message}`, true);
  }
}
function updateMapStatus() {
  const name = String(state.map?.name || state.map?.map || "DUST II").replace(/^de_/, "").replaceAll("_", " ").toUpperCase();
  $("mapStatus").textContent = state.mapImageError ? `${name} · RADAR IMAGE UNAVAILABLE` : `${name} · ${state.mapImage ? "WORLD-ALIGNED RADAR" : "LOADING RADAR"}`;
}
async function initialize() {
  wireControls();
  for (const key of document.querySelectorAll('.utility-key[data-kind] b')) key.innerHTML = IGLEffects.iconSvg(key.parentElement.dataset.kind);
  new ResizeObserver(drawMap).observe($("mapStage"));
  const mapPromise = loadMap();
  const scenariosPromise = loadScenarios();
  try {
    state.catalog = await api("/api/catalog");
    const matches = state.catalog.matches || [];
    const simulations = state.catalog.simulations || [];
    const options = (items, kind) => items.map((item) => {
      const id = item.match_id || item.simulation_id || item.id;
      return `<option value="${escapeHtml(`${kind}:${id}`)}">${escapeHtml(item.label || item.name || id)}</option>`;
    }).join("");
    $("matchSelect").innerHTML = (matches.length ? `<optgroup label="Recorded demos">${options(matches, "match")}</optgroup>` : "") + (simulations.length ? `<optgroup label="Simulations">${options(simulations, "simulation")}</optgroup>` : "");
    if (!matches.length && !simulations.length) {
      $("matchSelect").innerHTML = "<option>No local matches</option>";
      $("sourceMeta").textContent = "The catalog is empty. Add a parsed demo to the local dataset.";
      showEmpty("Your first round starts here", "No replay data is available yet. Parse a Dust II demo and refresh the viewer.");
      $("dataStatus").textContent = "Local catalog · 0 replays";
    } else {
      $("matchSelect").disabled = false;
      await loadReplay($("matchSelect").value);
    }
  } catch (error) {
    $("matchSelect").innerHTML = "<option>Data service unavailable</option>";
    $("sourceMeta").textContent = "Start the local Python service and refresh this page.";
    showEmpty("Local service unavailable", error.message, true);
    $("dataStatus").textContent = "Cannot connect to data service";
  }
  await mapPromise;
  await scenariosPromise;
  requestAnimationFrame(animate);
}
async function loadScenarios() {
  try {
    const catalog = await api("/api/scenarios");
    state.scenarios = (catalog.verified || []).filter((scenario) => scenario.match_id && Number.isInteger(scenario.round_number) && Number.isInteger(scenario.frame_index));
    if (state.scenarios.length) {
      $("sampleBtn").hidden = false;
      $("sampleBtn").title = state.scenarios[0].label || "Load a verified scenario from the professional match data";
      setControls();
    }
  } catch {
    // Older servers can still replay and export matches without a scenario catalog.
    $("sampleBtn").hidden = true;
  }
}
async function loadVerifiedScenario() {
  const sample = state.scenarios[0];
  if (!sample || state.loading || state.branching) return;
  const selection = `match:${sample.match_id}`;
  $("matchSelect").value = selection;
  await loadReplay(selection);
  if (!state.match || state.match.match_id !== sample.match_id) return;
  const roundIndex = state.match.rounds.findIndex((round) => Number(round.number) === sample.round_number);
  if (roundIndex < 0 || !state.match.rounds[roundIndex].frames[sample.frame_index]) {
    toast("The tested scenario points to a frame that is no longer available in this dataset.", true);
    return;
  }
  state.roundIndex = roundIndex;
  state.perspective = "all";
  $("viewSelect").value = "all";
  $("perspectiveNote").querySelector("span:last-child").textContent = "Omniscient observer · all positions";
  $("roundSelect").value = roundIndex;
  seek(sample.frame_index);
  renderEventTicks();
  toast(`${sample.label || "Tested post-plant"} loaded. Select Branch simulation to run it.`);
}
function setControls() {
  const hasFrames = Boolean(frames().length);
  const disabled = !hasFrames || state.loading || state.branching;
  for (const id of ["playBtn", "prevBtn", "nextBtn", "timeline", "exportBtn"]) $(id).disabled = disabled;
  $("branchBtn").disabled = disabled || state.simulated;
  $("sampleBtn").disabled = !state.scenarios.length || state.loading || state.branching;
  $("roundSelect").disabled = !state.match || state.loading || state.branching;
  $("matchSelect").disabled = !state.catalog || (!(state.catalog.matches?.length) && !(state.catalog.simulations?.length)) || state.branching;
  if (hasFrames) {
    $("prevBtn").disabled ||= state.frameIndex === 0;
    $("nextBtn").disabled ||= state.frameIndex === frames().length - 1;
  }
}
function stop() {
  state.playing = false;
  $("playBtn").textContent = "▶";
  $("playBtn").setAttribute("aria-label", "Play replay");
  setControls();
}
function togglePlayback() {
  if ($("playBtn").disabled) return;
  if (state.playing) { stop(); return; }
  if (state.frameIndex >= frames().length - 1) seek(0);
  state.playing = true;
  state.previousAnimation = null;
  state.playbackTime = displayTime();
  $("playBtn").textContent = "Ⅱ";
  $("playBtn").setAttribute("aria-label", "Pause replay");
}
function seek(index) {
  state.frameIndex = Math.max(0, Math.min(frames().length - 1, index));
  state.playbackTime = frameTime(currentFrame());
  renderAll();
}
function animate(timestamp) {
  if (state.playing && frames().length) {
    const delta = state.previousAnimation === null ? 0 : Math.min((timestamp - state.previousAnimation) / 1000, .25);
    state.playbackTime = Math.min(frameTime(frames().at(-1)), state.playbackTime + delta * finite($("speedSelect").value, 1));
    let index = state.frameIndex;
    const list = frames();
    while (index + 1 < list.length && frameTime(list[index + 1]) <= state.playbackTime) index++;
    if (index !== state.frameIndex) {
      state.frameIndex = index;
      renderDetails();
      setControls();
    }
    drawMap();
    renderTimeline();
    if (state.playbackTime >= frameTime(list[list.length - 1])) { stop(); setControls(); }
  }
  state.previousAnimation = timestamp;
  requestAnimationFrame(animate);
}
function wireControls() {
  $("matchSelect").addEventListener("change", (event) => loadReplay(event.target.value));
  $("roundSelect").addEventListener("change", (event) => {
    stop(); state.roundIndex = Number(event.target.value); state.selectedPlayer = null;
    seek(0); renderEventTicks();
  });
  $("viewSelect").addEventListener("change", (event) => {
    state.perspective = event.target.value;
    $("perspectiveNote").querySelector("span:last-child").textContent = state.perspective === "all" ? "Omniscient observer · all positions" : "Friendly positions only · no inferred enemy vision";
    state.selectedPlayer = null;
    $("playerTooltip").hidden = true;
    renderAll();
  });
  for (const id of ["trailsToggle", "namesToggle", "utilitiesToggle", "shotsToggle"]) $(id).addEventListener("change", drawMap);
  $("timeline").addEventListener("input", (event) => { stop(); seek(Number(event.target.value)); });
  $("playBtn").addEventListener("click", togglePlayback);
  $("prevBtn").addEventListener("click", () => { stop(); seek(state.frameIndex - 1); });
  $("nextBtn").addEventListener("click", () => { stop(); seek(state.frameIndex + 1); });
  $("exportBtn").addEventListener("click", exportSnapshot);
  $("sampleBtn").addEventListener("click", loadVerifiedScenario);
  $("branchBtn").addEventListener("click", branchSimulation);
  $("returnBtn").addEventListener("click", () => {
    if (!state.recording) return;
    const recording = state.recording;
    state.roundIndex = recording.roundIndex; state.frameIndex = recording.frameIndex;
    state.recording = null;
    setReplay(recording.match, false, false);
  });
  document.addEventListener("keydown", (event) => {
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(event.target.tagName) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.code === "Space") { event.preventDefault(); togglePlayback(); }
    if ((event.code === "ArrowLeft" || event.code === "ArrowRight") && !$("timeline").disabled) {
      event.preventDefault(); stop(); seek(state.frameIndex + (event.code === "ArrowRight" ? 1 : -1));
    }
  });
  $("mapCanvas").addEventListener("mousemove", showPlayerTooltip);
  $("mapCanvas").addEventListener("mouseleave", () => { $("playerTooltip").hidden = true; });
  $("mapCanvas").addEventListener("click", (event) => {
    const player = hitPlayer(event);
    state.selectedPlayer = player?.id ?? null;
    renderAll();
  });
}
function renderAll() { renderDetails(); renderTimeline(); drawMap(); setControls(); }
function renderDetails() {
  const frame = currentFrame();
  if (!frame) return;
  const players = frame.players;
  const number = roundNumber();
  const winner = currentRound()?.winner;
  $("roundTitle").textContent = `Round ${String(number).padStart(2, "0")}${state.simulated ? " · Simulation" : ""}`;
  $("replayEyebrow").textContent = `${String(state.match.map || "MAP").replace(/^de_/, "").replaceAll("_", " ").toUpperCase()} / ${state.simulated ? "SCENARIO BRANCH" : "TACTICAL REPLAY"}`;
  $("tAlive").textContent = state.perspective === "CT" ? "?" : players.filter((player) => player.team === "T" && alive(player)).length;
  $("ctAlive").textContent = state.perspective === "T" ? "?" : players.filter((player) => player.team === "CT" && alive(player)).length;
  const planted = ["planted", "plant"].includes(String(frame.bomb?.state).toLowerCase());
  $("roundClock").textContent = clock(planted ? frame.bomb?.time_remaining : frame.round_time_remaining);
  $("clockLabel").textContent = planted ? "BOMB TIMER" : "ROUND TIME";
  $("roundClock").parentElement.classList.toggle("planted", planted);
  $("rosterCount").textContent = `${players.length} players`;
  renderRoster("T", players);
  renderRoster("CT", players);
  renderEvents();
  $("eventTicks").hidden = state.perspective !== "all";
  const sample = frames().length > 1 ? frames().length / Math.max(.001, duration()) : 0;
  $("dataStatus").textContent = `${state.simulated ? "Simulation" : "Demo data"} · ${frames().length.toLocaleString()} frames${sample ? ` · ~${sample.toFixed(1)} Hz` : ""}${winner ? ` · ${winner} round win` : ""}`;
  $("branchNote").innerHTML = state.simulated ? "Model-based branch · no learned policy<br>Simulated outcomes are approximations." : "30 seconds · fixed seed 42<br>Simulated outcomes are approximations.";
}
function buildPlayerNumbers(match, inherited = null) {
  // SteamIDs exceed Number's safe integer range. Their exact strings are the identity.
  const numbers = new Map(inherited || []);
  const firstSide = new Map();
  for (const round of match?.rounds || []) {
    for (const frame of round.frames || []) {
      for (const player of frame.players || []) {
        if (player.id === null || player.id === undefined) continue;
        const id = String(player.id);
        if (id && !firstSide.has(id)) firstSide.set(id, player.team);
      }
    }
  }
  const used = new Set(numbers.values());
  const compareIds = (left, right) => left < right ? -1 : left > right ? 1 : 0;
  // Scan the whole recording before assigning numbers, so missing players and seeking
  // cannot change the roster. Frame array order, name changes, and deaths are irrelevant.
  const overflow = [];
  for (const [team, start] of [["T", 1], ["CT", 6]]) {
    const ids = [...firstSide.keys()].filter((id) => firstSide.get(id) === team && !numbers.has(id)).sort(compareIds);
    const slots = Array.from({ length: 5 }, (_, index) => start + index).filter((slot) => !used.has(slot));
    for (const id of ids) {
      const slot = slots.shift();
      if (slot === undefined) overflow.push(id);
      else { numbers.set(id, slot); used.add(slot); }
    }
  }
  overflow.push(...[...firstSide.keys()].filter((id) => !numbers.has(id) && !overflow.includes(id)));
  let next = Math.max(10, ...used) + 1;
  for (const id of overflow.sort(compareIds)) { numbers.set(id, next); next++; }
  return numbers;
}
function setPlayerIdentity(match, simulated = false) {
  const parent = simulated ? state.recording?.match : null;
  const parentId = simulated ? match?.source?.scenario_match_id : null;
  const inherited = parent
    ? recordedPlayerNumbers.get(String(parent.match_id)) || buildPlayerNumbers(parent)
    : parentId !== null && parentId !== undefined ? recordedPlayerNumbers.get(String(parentId)) : null;
  state.playerNumbers = buildPlayerNumbers(match, inherited);
  state.playerIdentityMatch = match;
  if (!simulated && match?.match_id !== null && match?.match_id !== undefined) {
    recordedPlayerNumbers.set(String(match.match_id), new Map(state.playerNumbers));
  }
}
function playerOrder(player) {
  if (state.playerIdentityMatch !== state.match) setPlayerIdentity(state.match, state.simulated);
  return state.playerNumbers.get(String(player.id)) ?? "?";
}
function orderedTeamPlayers(team, players) {
  return players.filter((player) => player.team === team).sort((left, right) => {
    const difference = finite(playerOrder(left), Infinity) - finite(playerOrder(right), Infinity);
    if (Number.isFinite(difference) && difference !== 0) return difference;
    return String(left.id) < String(right.id) ? -1 : String(left.id) > String(right.id) ? 1 : 0;
  });
}
function inventoryHtml(player) {
  if (!alive(player)) return '<div class="utility-loadout unknown">Utility —</div>';
  const inventory = IGLTelemetry.utilityInventory(player, { simulated: state.simulated });
  if (!inventory.known) return `<div class="utility-loadout unknown">Utility ${state.simulated ? "not simulated" : "unknown"}</div>`;
  const chips = Object.entries(UTILITY_STYLE).map(([kind, style]) => {
    const count = inventory.counts[kind];
    const label = count === null ? "?" : count;
    return `<span class="utility-chip${count === 0 ? " empty" : ""}${count === null ? " unknown" : ""}" data-kind="${kind}" title="${style.name}: ${count === null ? "unknown" : count}" aria-label="${style.name}: ${count === null ? "unknown" : count}">${IGLEffects.iconSvg(kind)}<b class="utility-quantity">${label}</b></span>`;
  }).join("");
  return `<div class="utility-loadout" aria-label="Grenade inventory">${chips}<span class="utility-total" title="Total grenades">${inventory.total ?? "?"} util</span></div>`;
}
function inventorySummary(player) {
  if (!alive(player)) return "Utility —";
  const inventory = IGLTelemetry.utilityInventory(player, { simulated: state.simulated });
  if (!inventory.known) return state.simulated ? "Utility not simulated" : "Utility unknown";
  return Object.entries(UTILITY_STYLE).map(([kind, style]) => `${style.label} ${inventory.counts[kind] ?? "?"}`).join(" · ");
}
function renderRoster(team, players) {
  const teamPlayers = orderedTeamPlayers(team, players);
  const target = $(team === "T" ? "tRoster" : "ctRoster");
  const hidden = state.perspective !== "all" && state.perspective !== team;
  $(team === "T" ? "tHealth" : "ctHealth").textContent = hidden ? "HIDDEN" : `${teamPlayers.reduce((sum, player) => sum + (alive(player) ? finite(player.hp, 100) : 0), 0)} HP`;
  if (hidden) { target.innerHTML = '<p class="roster-empty">Opponent positions and loadouts hidden.<br>This is a friendly-only display filter.</p>'; return; }
  if (!teamPlayers.length) { target.innerHTML = '<p class="roster-empty">No players on this team.</p>'; return; }
  target.innerHTML = teamPlayers.map((player) => {
    const hp = Math.max(0, Math.min(100, finite(player.hp, 100)));
    const isAlive = alive(player);
    const weapon = String(player.weapon || "Unknown weapon").replace(/^weapon_/, "").replaceAll("_", " ");
    const kit = [finite(player.armor) > 0 ? `${finite(player.armor)} A` : null, player.helmet ? "H" : null, player.defuser ? "KIT" : null, player.bomb ? "C4" : null].filter(Boolean).join(" · ");
    return `<button type="button" class="player-card ${team.toLowerCase()}${isAlive ? "" : " dead"}${String(state.selectedPlayer) === String(player.id) ? " selected" : ""}" data-player="${escapeHtml(player.id)}" aria-label="Inspect player ${playerOrder(player)}, ${escapeHtml(player.name || player.id)}, ${isAlive ? `${hp} health` : "dead"}"><span class="player-number">${playerOrder(player)}</span><div><div class="player-name">${escapeHtml(player.name || player.id)}</div><div class="player-weapon">${isAlive ? escapeHtml(weapon) : "Eliminated"}</div></div><div class="player-details">${isAlive ? `${hp} <span class="muted">HP</span>` : "—"}<span class="player-kit">${escapeHtml(kit) || "&nbsp;"}</span></div>${inventoryHtml(player)}<span class="health-track"><span class="health-bar" style="width:${isAlive ? hp : 0}%"></span></span></button>`;
  }).join("");
  for (const button of target.querySelectorAll("button[data-player]")) button.addEventListener("click", () => {
    state.selectedPlayer = state.selectedPlayer === button.dataset.player ? null : button.dataset.player;
    renderAll();
  });
}
function eventTime(event) {
  if (Number.isFinite(Number(event.time)) && event.time !== null) return Number(event.time);
  const tick = finite(event.tick, NaN);
  if (Number.isFinite(tick)) return frameTime(frames().find((frame) => finite(frame.tick) >= tick) || frames().at(-1));
  return startTime();
}
function eventName(value) {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "object") return value.name || value.id || null;
  const player = currentFrame()?.players.find((item) => String(item.id) === String(value));
  return player?.name || String(value);
}
function eventDescription(event) {
  const type = String(event.type || event.event || "event");
  const attacker = eventName(event.attacker_name || event.attackerName || event.attacker || event.attacker_id || event.attackerSteamID || event.killer_name || event.killer);
  const victim = eventName(event.victim_name || event.victimName || event.victim || event.victim_id || event.victimSteamID || event.user_name || event.userid);
  const player = eventName(event.player_name || event.playerName || event.player || event.player_id || event.playerSteamID || event.user_name || event.userid);
  if (["player_death", "kill", "death"].includes(type)) return { icon: "×", text: `${attacker || "World"} → ${victim || "player"}${event.weapon ? ` · ${String(event.weapon).replace(/^weapon_/, "")}` : ""}` };
  if (type.includes("bomb_planted") || type === "bomb_plant") return { icon: "◆", text: `Bomb planted${event.site || event.bombSite ? ` · ${event.site || event.bombSite}` : ""}${player ? ` by ${player}` : ""}` };
  if (type.includes("bomb_defused") || type === "bomb_defuse") return { icon: "◇", text: `Bomb defused${player ? ` by ${player}` : ""}` };
  if (type.includes("bomb_exploded")) return { icon: "✦", text: "Bomb exploded" };
  if (type.includes("round_end")) return { icon: "⚑", text: `Round ended${event.winner ? ` · ${event.winner} win` : ""}` };
  if (type === "grenade_throw") return { icon: "↗", text: `${eventName(event.throwerName || event.throwerSteamID) || player || "Player"} · ${event.grenadeType || event.weapon || "grenade"}` };
  if (type === "flash") return { icon: "✧", text: `${attacker || "Player"} flashed ${player || victim || "player"}${event.flashDuration ? ` · ${Number(event.flashDuration).toFixed(1)}s` : ""}` };
  return { icon: "·", text: `${type.replaceAll("_", " ")}${player ? ` · ${player}` : ""}` };
}
function renderEvents() {
  const round = currentRound();
  const allEvents = round?.events || [];
  // Event feeds are observer data; omit them in the deliberately limited team filter.
  if (state.perspective !== "all") {
    $("eventCount").textContent = "—";
    $("eventList").innerHTML = '<p class="roster-empty">Observer event feed hidden in team view. Demo-derived perception is not reconstructed.</p>';
    return;
  }
  const time = frameTime(currentFrame());
  const ordered = allEvents.map((event, index) => ({ event, index, time: eventTime(event) })).sort((a, b) => a.time - b.time);
  const important = ordered.filter(({ event }) => !["damage", "player_hurt", "player_footstep", "weapon_fire", "bullet_impact"].includes(event.type));
  const relevant = important.length ? important : ordered;
  const past = relevant.filter((item) => item.time <= time);
  const visible = past.slice(-12);
  $("eventCount").textContent = `${past.length} / ${relevant.length}`;
  if (!visible.length) { $("eventList").innerHTML = '<p class="roster-empty">No events yet at this point in the round.</p>'; return; }
  $("eventList").innerHTML = visible.slice().reverse().map(({ event, index, time: eventAt }) => {
    const description = eventDescription(event);
    return `<div class="event-item${time - eventAt < 3 ? " current" : ""}" role="button" tabindex="0" data-event="${index}" aria-label="Seek to ${escapeHtml(description.text)}"><span class="event-time">${clock(eventAt - startTime())}</span><span class="event-icon">${description.icon}</span><span class="event-text">${escapeHtml(description.text)}</span></div>`;
  }).join("");
  for (const element of $("eventList").querySelectorAll("[data-event]")) {
    const seekEvent = () => { stop(); const at = eventTime(allEvents[Number(element.dataset.event)]); const index = frames().findIndex((frame) => frameTime(frame) >= at); seek(index < 0 ? frames().length - 1 : index); };
    element.addEventListener("click", seekEvent);
    element.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); seekEvent(); } });
  }
}
function renderEventTicks() {
  const span = duration();
  $("eventTicks").innerHTML = span ? (currentRound()?.events || []).filter((event) => /death|kill|bomb_(plant|defus|explod)/.test(event.type)).map((event) => `<i class="event-tick${String(event.type).includes("bomb") ? " bomb" : ""}" style="left:${Math.min(100, Math.max(0, (eventTime(event) - startTime()) / span * 100))}%"></i>`).join("") : "";
}
function renderTimeline() {
  const list = frames();
  if (!list.length) return;
  const elapsed = displayTime() - startTime();
  $("timeline").max = list.length - 1;
  $("timeline").value = state.frameIndex;
  const progress = duration() > 0 ? elapsed / duration() * 100 : 0;
  $("timeline").style.background = `linear-gradient(to right,var(--t) ${progress}%,#2b3b4e ${progress}%)`;
  $("timeElapsed").textContent = clock(elapsed, true);
  $("timeDuration").textContent = clock(duration(), true);
  $("frameLabel").textContent = `FRAME ${state.frameIndex + 1} / ${list.length} · TICK ${currentFrame()?.tick ?? "—"}`;
}
function mapLayout() {
  const canvas = $("mapCanvas");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const mapWidth = finite(state.map?.width, state.mapImage?.naturalWidth || 1024);
  const mapHeight = finite(state.map?.height, state.mapImage?.naturalHeight || 1024);
  const padding = Math.min(30, width * .045);
  const scale = Math.min((width - padding * 2) / mapWidth, (height - padding * 2) / mapHeight);
  return { width, height, mapWidth, mapHeight, scale, left: (width - mapWidth * scale) / 2, top: (height - mapHeight * scale) / 2 };
}
function project(player, layout) {
  const map = state.map;
  return {
    x: layout.left + (finite(player.x) - finite(map.pos_x)) / finite(map.scale, 1) * layout.scale,
    y: layout.top + (finite(map.pos_y) - finite(player.y)) / finite(map.scale, 1) * layout.scale,
  };
}
function visiblePlayer(player) { return state.perspective === "all" || player.team === state.perspective; }
function interpolatedPlayers() {
  const frame = currentFrame();
  if (!frame) return [];
  const next = frames()[state.frameIndex + 1];
  if (!next || frameTime(next) <= frameTime(frame)) return frame.players;
  const amount = Math.max(0, Math.min(1, (displayTime() - frameTime(frame)) / (frameTime(next) - frameTime(frame))));
  const nextPlayers = new Map(next.players.map((player) => [String(player.id), player]));
  return frame.players.map((player) => {
    const target = nextPlayers.get(String(player.id));
    // Do not interpolate a respawn, death, or teleport across the map.
    if (!target || !alive(player) || !alive(target) || Math.hypot(finite(target.x) - finite(player.x), finite(target.y) - finite(player.y)) > 500) return player;
    const yawDelta = ((finite(target.yaw) - finite(player.yaw) + 540) % 360) - 180;
    return { ...player, x: finite(player.x) + (finite(target.x) - finite(player.x)) * amount, y: finite(player.y) + (finite(target.y) - finite(player.y)) * amount, yaw: finite(player.yaw) + yawDelta * amount };
  });
}
function drawMap() {
  const canvas = $("mapCanvas");
  const context = canvas.getContext("2d");
  const layout = mapLayout();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(layout.width * dpr), pixelHeight = Math.round(layout.height * dpr);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, layout.width, layout.height);
  state.screenPlayers = [];
  if (!state.map) return;
  if (state.mapImage) {
    context.globalAlpha = .78;
    context.drawImage(state.mapImage, layout.left, layout.top, layout.mapWidth * layout.scale, layout.mapHeight * layout.scale);
    context.globalAlpha = 1;
  }
  if (!currentFrame()) return;
  if ($("trailsToggle").checked) drawTrails(context, layout);
  drawTelemetry(context, layout);
  const players = interpolatedPlayers().filter(visiblePlayer);
  for (const player of players.filter((item) => !alive(item))) drawPlayer(context, player, layout);
  for (const player of players.filter(alive)) drawPlayer(context, player, layout);
  drawBomb(context, layout);
}
function currentTelemetry() {
  const round = currentRound();
  if (!round) return null;
  if (!telemetryCache.has(round)) telemetryCache.set(round, IGLTelemetry.buildTelemetry(round, state.match.source || {}));
  const time = displayTime();
  const telemetry = IGLTelemetry.telemetryAt(telemetryCache.get(round), time, currentFrame(), state.perspective);
  if (!motionCache.has(round)) motionCache.set(round, IGLMotion.build(round));
  return IGLMotion.sample(motionCache.get(round), state.frameIndex, time, telemetry);
}
function drawTelemetry(context, layout) {
  const telemetry = currentTelemetry();
  if (!telemetry) return;
  const utilities = $("utilitiesToggle").checked;
  const shots = $("shotsToggle").checked;
  const status = [];
  if (utilities) {
    if (telemetry.known.smokes) status.push(`${telemetry.smokes.length} smoke${telemetry.smokes.length === 1 ? "" : "s"}`);
    else if (state.perspective === "all" && !state.simulated) status.push(`${telemetry.smokes.length} smoke markers · incomplete source`);
    if (telemetry.known.fires) status.push(`${telemetry.fires.length} fire${telemetry.fires.length === 1 ? "" : "s"}`);
    if (telemetry.known.projectiles) status.push(`${telemetry.projectiles.length} grenade entit${telemetry.projectiles.length === 1 ? "y" : "ies"}`);
    if (telemetry.pulses.length) status.push(`${telemetry.pulses.length} utility event${telemetry.pulses.length === 1 ? "" : "s"}`);
  }
  if (shots && telemetry.known.shots) status.push(`${telemetry.shots.length} recent shot${telemetry.shots.length === 1 ? "" : "s"}`);
  const statusText = state.simulated ? "Utility and individual shots not simulated" : status.join(" · ") || "Telemetry layers hidden or unavailable";
  if ($("telemetryStatus").textContent !== statusText) $("telemetryStatus").textContent = statusText;
  const notes = [];
  if (state.simulated) notes.push("DECOY models combat outcomes; it does not generate grenade use or individual gunshots.");
  else {
    notes.push("Grenade motion is visually interpolated. Inventory uses recorded samples.");
    if (state.perspective !== "all") notes.push("World effects hidden in team view.");
    else if (!telemetry.known.projectiles) notes.push("Projectile positions unavailable.");
    if (telemetry.diagnostics?.futureSmokesExcluded) notes.push("Inconsistent source smoke records hidden.");
  }
  const note = notes.join(" ");
  if ($("telemetryNote").textContent !== note) $("telemetryNote").textContent = note;
  context.save();
  if (utilities) IGLEffects.drawUtilities(context, telemetry, {
    project: (point) => project(point, layout),
    worldScale: layout.scale / finite(state.map.scale, 4.4),
    time: displayTime(),
  });
  if (shots) for (const shot of telemetry.shots) {
    const point = project(shot, layout);
    context.globalAlpha = Math.max(.2, 1 - finite(shot.age) / .8);
    context.strokeStyle = "#ffe7ac"; context.fillStyle = "#fff4d8"; context.lineWidth = 1.6;
    if (shot.yaw !== null && Number.isFinite(Number(shot.yaw))) {
      const angle = -Number(shot.yaw) * Math.PI / 180;
      const dx = Math.cos(angle), dy = Math.sin(angle);
      context.beginPath(); context.moveTo(point.x + dx * 10, point.y + dy * 10); context.lineTo(point.x + dx * 36, point.y + dy * 36); context.stroke();
      context.beginPath(); context.moveTo(point.x + dx * 15 - dy * 3, point.y + dy * 15 + dx * 3); context.lineTo(point.x + dx * 21, point.y + dy * 21); context.lineTo(point.x + dx * 15 + dy * 3, point.y + dy * 15 - dx * 3); context.closePath(); context.fill();
    } else {
      context.beginPath(); context.arc(point.x, point.y, 11, 0, Math.PI * 2); context.stroke();
    }
  }
  context.restore();
}
function drawTrails(context, layout) {
  const frame = currentFrame();
  const from = frameTime(frame) - 5;
  let first = state.frameIndex;
  while (first > 0 && frameTime(frames()[first - 1]) >= from) first--;
  // Bound drawing work for high-frequency files while retaining the full data on disk.
  const stride = Math.max(1, Math.floor((state.frameIndex - first) / 70));
  for (const player of frame.players.filter(visiblePlayer)) {
    context.beginPath();
    let previous = null;
    let previousWorld = null;
    for (let index = first; index <= state.frameIndex; index += stride) {
      const historic = frames()[index].players.find((item) => String(item.id) === String(player.id));
      if (!historic || !alive(historic)) { previous = null; previousWorld = null; continue; }
      const position = project(historic, layout);
      const jump = previousWorld && Math.hypot(finite(historic.x) - finite(previousWorld.x), finite(historic.y) - finite(previousWorld.y)) > 500;
      if (!previous || jump) context.moveTo(position.x, position.y); else context.lineTo(position.x, position.y);
      previous = position; previousWorld = historic;
    }
    context.strokeStyle = COLORS[player.team] || "#abb7c7";
    context.lineWidth = String(player.id) === String(state.selectedPlayer) ? 2.5 : 1.3;
    context.globalAlpha = String(player.id) === String(state.selectedPlayer) ? .8 : .3;
    context.stroke(); context.globalAlpha = 1;
  }
}
function drawPlayer(context, player, layout) {
  if (!Number.isFinite(Number(player.x)) || !Number.isFinite(Number(player.y))) return;
  const position = project(player, layout);
  const color = COLORS[player.team] || "#abb7c7";
  const selected = String(player.id) === String(state.selectedPlayer);
  const size = layout.width < 400 ? 6 : 7;
  if (!alive(player)) {
    context.globalAlpha = .55; context.strokeStyle = color; context.fillStyle = "#101a28"; context.lineWidth = 1;
    context.beginPath(); context.arc(position.x, position.y, size, 0, Math.PI * 2); context.fill(); context.stroke();
    context.textAlign = "center"; context.textBaseline = "middle"; context.font = "600 8px Segoe UI, sans-serif"; context.fillStyle = color;
    context.fillText(String(playerOrder(player)), position.x, position.y + .4);
    context.font = "600 9px Segoe UI, sans-serif"; context.fillText("×", position.x + size + 2, position.y + size + 1); context.globalAlpha = 1;
    state.screenPlayers.push({ ...player, screenX: position.x, screenY: position.y });
    return;
  }
  const angle = -finite(player.yaw) * Math.PI / 180;
  context.beginPath(); context.moveTo(position.x + Math.cos(angle) * (size + 9), position.y + Math.sin(angle) * (size + 9)); context.lineTo(position.x + Math.cos(angle + .58) * (size + 2), position.y + Math.sin(angle + .58) * (size + 2)); context.lineTo(position.x + Math.cos(angle - .58) * (size + 2), position.y + Math.sin(angle - .58) * (size + 2)); context.closePath(); context.fillStyle = color; context.globalAlpha = .8; context.fill(); context.globalAlpha = 1;
  if (selected) {
    context.beginPath(); context.arc(position.x, position.y, size + 5, 0, Math.PI * 2); context.strokeStyle = "#e9eff8"; context.lineWidth = 1.3; context.stroke();
  }
  context.shadowColor = "#000a"; context.shadowBlur = 5;
  context.beginPath(); context.arc(position.x, position.y, size, 0, Math.PI * 2); context.fillStyle = color; context.fill(); context.strokeStyle = "#0b1523"; context.lineWidth = 1.8; context.stroke(); context.shadowBlur = 0;
  context.textAlign = "center"; context.textBaseline = "middle"; context.font = "600 8px Segoe UI, sans-serif"; context.fillStyle = "#102131"; context.fillText(String(playerOrder(player)), position.x, position.y + .4);
  if ($("namesToggle").checked || selected) {
    const name = String(player.name || player.id);
    context.font = `${selected ? "600" : "500"} ${layout.width < 400 ? 8 : 9}px Segoe UI, sans-serif`;
    const nameWidth = context.measureText(name).width;
    const textX = Math.min(layout.width - nameWidth / 2 - 5, Math.max(nameWidth / 2 + 5, position.x));
    const textY = position.y + size + 12;
    context.fillStyle = "#0a121fd9"; context.fillRect(textX - nameWidth / 2 - 4, textY - 6, nameWidth + 8, 13);
    context.fillStyle = selected ? "#ffffff" : "#d3dce8"; context.fillText(name, textX, textY);
  }
  state.screenPlayers.push({ ...player, screenX: position.x, screenY: position.y });
}
function drawBomb(context, layout) {
  const bomb = currentFrame()?.bomb;
  if (!bomb || !["planted", "dropped", "carried", "plant"].includes(String(bomb.state).toLowerCase())) return;
  // A team-filtered radar does not reconstruct knowledge of a dropped bomb.
  if (state.perspective !== "all" && bomb.state !== "planted" && bomb.state !== "plant") return;
  let location = bomb;
  if (bomb.carrier_id !== null && bomb.carrier_id !== undefined && bomb.state === "carried") location = interpolatedPlayers().find((player) => String(player.id) === String(bomb.carrier_id)) || bomb;
  if (!Number.isFinite(Number(location.x)) || location.x === null || !Number.isFinite(Number(location.y)) || location.y === null) return;
  const position = project(location, layout);
  const carried = bomb.state === "carried";
  context.save(); context.translate(position.x + (carried ? 11 : 0), position.y + (carried ? -10 : 0)); context.rotate(Math.PI / 4);
  context.fillStyle = ["planted", "plant"].includes(bomb.state) ? "#f3c57b" : "#edf1f6";
  context.strokeStyle = "#101827"; context.lineWidth = 2;
  context.fillRect(-4, -4, 8, 8); context.strokeRect(-4, -4, 8, 8); context.restore();
  if (["planted", "plant"].includes(bomb.state)) {
    context.beginPath(); context.arc(position.x, position.y, 13, 0, Math.PI * 2); context.strokeStyle = "#efb66a88"; context.lineWidth = 1; context.stroke();
  }
}
function hitPlayer(event) {
  const rect = $("mapCanvas").getBoundingClientRect();
  const x = event.clientX - rect.left, y = event.clientY - rect.top;
  return state.screenPlayers.slice().reverse().find((player) => Math.hypot(player.screenX - x, player.screenY - y) < 13);
}
function showPlayerTooltip(event) {
  const player = hitPlayer(event);
  const tooltip = $("playerTooltip");
  if (!player) { tooltip.hidden = true; return; }
  tooltip.innerHTML = `${escapeHtml(player.name || player.id)} <span style="color:${COLORS[player.team] || "#ddd"}">· ${escapeHtml(player.team)}</span><small>${alive(player) ? `${finite(player.hp, 100)} HP` : "Eliminated"} · ${escapeHtml(String(player.weapon || "unknown").replace(/^weapon_/, ""))}<br>${escapeHtml(inventorySummary(player))}<br>x ${Math.round(finite(player.x))} · y ${Math.round(finite(player.y))} · z ${Math.round(finite(player.z))}</small>`;
  tooltip.hidden = false;
  const rect = $("mapCanvas").getBoundingClientRect();
  tooltip.style.left = `${Math.min(rect.width - tooltip.offsetWidth - 8, Math.max(8, player.screenX + 17))}px`;
  tooltip.style.top = `${Math.min(rect.height - tooltip.offsetHeight - 8, Math.max(8, player.screenY - 15))}px`;
}
function exportSnapshot() {
  if (!currentFrame()) return;
  const snapshot = {
    schema_version: 1, kind: "scenario_snapshot", match_id: state.match.match_id,
    map: state.match.map, game: state.match.game, round_number: roundNumber(), frame_index: state.frameIndex,
    source: { ...state.match.source, replay_kind: state.simulated ? "simulation" : "recorded_demo", tick: currentFrame().tick },
    frame: currentFrame(),
    limitations: ["Recorded state is not a complete game-engine snapshot.", "Contains observer information; construct limited team observations before use as a policy input."],
  };
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${String(state.match.match_id || "match").replace(/[^a-zA-Z0-9_-]/g, "_")}_round-${roundNumber()}_tick-${currentFrame().tick ?? state.frameIndex}.json`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Snapshot exported with source provenance and observer-state limitations.");
}
async function branchSimulation() {
  if (!currentFrame() || state.branching || state.simulated) return;
  stop(); state.branching = true; setControls();
  const previousLabel = $("branchBtn").innerHTML;
  $("branchBtn").textContent = "Running simulation…";
  const recording = { match: state.match, roundIndex: state.roundIndex, frameIndex: state.frameIndex };
  try {
    const response = await api("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_id: state.match.match_id, round_number: roundNumber(), frame_index: state.frameIndex, seed: 42, seconds: 30 }),
    });
    const replay = validateReplay(response.replay || response);
    state.recording = recording;
    setReplay(replay, true);
    toast("Simulation branch ready. The recorded continuation remains available.");
  } catch (error) {
    toast(`Simulation could not start: ${error.message}`, true);
  } finally {
    state.branching = false;
    $("branchBtn").innerHTML = previousLabel;
    setControls();
  }
}

initialize();
