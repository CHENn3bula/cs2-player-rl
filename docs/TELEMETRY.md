# Recorded utility and gunfire telemetry

## Visual layer and player identities

`web/motion.js` smooths projectile positions **for display only** between adjacent recorded samples. Exact IDs are preferred; anonymous ESTA projectiles use conservative, unique same-type spatial matches. Ambiguous matches, new throws of the same type, missing samples, long gaps and implausible jumps are held rather than connected. Stationary grenades remain stationary. Inferred matches are tagged in `display_motion`; no synthetic entity ID or trajectory is written into telemetry or the dataset.

This renderer intentionally looks at the next recorded sample to interpolate the on-screen position. It is not a causal RL observation: raw `telemetryAt`, snapshots, exported scenarios and stored replay files remain based on recorded samples. The display clock is preserved when pausing, resuming, resizing or changing layers; seeking reconstructs the same result without animation-history dependence. Inventories stay discrete, and source-only trails remain limited to reliable identities.

`web/effects.js` renders replay-time smoke clouds, flickering fire patches, grenade silhouettes and flash-hit starbursts. It draws behind player markers and creates no gameplay state. Pausing or seeking back to the same frame produces identical pixels. The visual reference is the soft smoke/flash treatment in [Leetify's published replay image](https://leetify.com/assets/images/match-details-loginwall/2d-replay.png) and the utility animations documented in [SCOPE.GG's VFX update](https://blog.scope.gg/scopegg-update-025-en/); no proprietary assets are copied.

The nominal 144-Hammer-unit smoke radius and 150-unit fire display scale follow the configurable approximations in [Awpy's map-control documentation](https://awpy.readthedocs.io/en/stable/map_control.html). They scale with the radar projection. These soft footprints are illustrative: ESTA supplies an inferno origin, not burning-cell polygons, and this layer does not implement wall clipping, smoke occlusion, damage radii or CS2 volumetric smoke. Flash-hit effects remain at recorded affected-player positions; no explosion center is invented. Current projectiles without reliable IDs get icons at recorded samples and no fabricated flight trail.

Player numbers are keyed by exact SteamID strings and computed once per match. Initial T players receive 1–5 and initial CT players 6–10, sorted deterministically by SteamID. Numbers follow the players when sides switch; deaths and missing snapshots do not reuse a number. The roster sorts by these same IDs. Interactive simulation branches inherit the source match registry, and return to recording preserves it.

`web/telemetry.js` exports `IGLTelemetry` in the browser and the same API through CommonJS. It reads the already normalized corpus; no download, normalization or model run is required.

- `utilityInventory(player, { simulated: false })` returns `known`, per-kind `counts`, `total`, and `complete`. `known` means an inventory collection exists. An uncertain individual quantity remains null, while other known quantities remain usable. `fire` combines `molotov` and `incendiary`; the total does not count that alias twice. Team totals must exclude dead slots.
- `buildTelemetry(round, source)` builds sorted event indexes with continuous canonical timestamps.
- `telemetryAt(index, time, frame, perspective)` returns sampled `smokes`, `fires`, `projectiles`, recent `shots` and `pulses`, availability flags, and corruption diagnostics. Marker coordinates are in Hammer units. Shots contain origin and recorded yaw, never a bullet endpoint. Throw pulses mark the recorded throw origin; flash pulses mark an affected player, not the grenade's detonation center.

Effect markers also expose `entity_id`, `sample_age`, `effect_age` and `trail`. The HTTP viewer preserves known 64-bit effect identity fields as decimal strings before JSON serialization; raw and canonical files are unchanged. The helper refuses already rounded, unsafe JavaScript numeric IDs. A valid recorded start tick supplies `effect_age`; an unavailable ignition/start time remains null. Smoke age can be known, while the current fire records have no start tick.

Trails contain only exact sampled positions of the same reliable entity ID from the past three seconds, ending at the selected snapshot. Missing or ambiguous snapshots break continuity; backwards seeking cannot expose later samples. The current ESTA projectile records contain only type and coordinates, with **no entity identity**, so their `entity_id` is null and their `trail` is empty. The recorded-history helper does not infer paths; the separate display-only motion layer can animate conservative matches without adding them to recorded history. Fire records contain an entity origin, not individual burning cells or a recorded spread polygon.

Shot markers persist for 0.65 seconds and event pulses for 1.15 seconds as display cues. These windows are not projectile travel times or flash blindness durations. A flash-affected event also retains its recorded `duration`, where available. Sampled grenade entities can already be stationary; their presence does not imply flight. The helper does not infer area radii, spread footprints, unsampled grenade paths, detonation times or bullet hits. Any stylized cloud or flame footprint drawn by the viewer is a visual approximation around recorded positions.

Friendly-only views hide world utility effects because their visibility is unavailable, and retain only friendly firearm/throw events and friendly flash-affected events. Simulation utility/gunfire telemetry is marked unavailable, rather than shown as an empty known inventory or invented shots.

## Source semantics checked

The existing raw and normalized ESTA files were inspected directly. The matching parser family was inspected through the official [Awpy 1.3.1 source distribution](https://files.pythonhosted.org/packages/d5/da/16edfa78ecb7f535abaf85950c13c2198eeca475d1285909ca38ae13799a/awpy-1.3.1.tar.gz), SHA-256 `9474546f94347e39fa82f305212bc98c9d08ba2dc053aa0e1ab7677f1114366c`. The package's `awpy/parser/parse_demo.go` establishes:

- Lines 766–791: inventories are weapon entries; non-flash utility is counted by entry, while flashes use magazine plus reserve ammunition. A single flash entry with magazine 1 and reserve 1 means two flashes. Unknown/negative flash ammunition stays unknown. A negative reserve does not erase a known smoke/HE/fire inventory entry.
- Lines 1864–1915: grenade throw records use the projectile's position at the throw callback. The `throwerX/Y/Z` field names do not mean a later landing position.
- Lines 1921–1938: `destroyTick` and `grenadeX/Y/Z` describe the projectile-destroy callback. They are not a universal detonation event.
- Lines 2455–2485: projectile and inferno positions are sampled. Smoke state is assigned from a shared slice, which is consistent with the future-start smoke records observed in the released data.

ESTA smoke arrays can contain an entry whose `startTick` is later than the containing frame's tick. The helper suppresses these records and marks smoke completeness unknown. This is a viewer safeguard; **the canonical corpus still preserves the original recorded arrays**. Future RL feature construction needs the same causality checks. Existing corpus audits validate schemas, player timelines, checksums and geometry coverage; they do not certify utility-state causality.

## Real regression examples

The attributed `web/telemetry.fixture.json` contains selected real source records under the ESTA CC-BY-SA-4.0 license. `node --test web/telemetry.test.cjs` runs 25 tests, including:

- ENCE–FaZe, demo `00e7fec9-cee0-430f-80f4-6b50443ceacd`: round 2 frame 0, broky's double flash inventory.
- The same demo, round 1 at 7.6299 seconds: Snappi's recorded USP-S fire origin and view yaw.
- The same demo, round 1 frame 109 at 55.165 seconds: one smoke, one fire and three grenade entities.
- The same demo, round 1 frame 111 at 56.173 seconds: flash-affected events at 55.929 seconds for hades, broky and karrigan.
- G2–ENCE, demo `0520c3de-fdfe-4387-8060-5916549ad991`, frame tick 10040: source smoke contamination with start tick 16337, suppressed by the helper.

Tests also cover unknown quantities, excluding grenade/knife `weapon_fire` records from gunshots, backwards seeking, source seconds resetting on bomb plant, missing coordinates, friendly information filtering, unavailable simulation telemetry, exact identities, disjoint same-type grenade histories, past-only trail windows and unknown effect ages. Three Python tests in `tests/test_server_telemetry.py` verify that HTTP identity preservation keeps exact integers and does not rewrite corpus files or fabricate missing IDs.
