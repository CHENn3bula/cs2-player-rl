# Professional match data foundation

The checked-in manifest identifies **12 real CS:GO Dust II professional map demos from 12 matches and seven tournaments**. The local raw cache contains the published parsed-demo files, not synthetic trajectories. These are Awpy 1.x JSON snapshots and events, not the original binary `.dem` recordings.

Source: [Esports Trajectories and Actions (ESTA)](https://github.com/pnxenopoulos/esta), pinned to commit [`0e81f74d480689a83f6e1e90835c1eb6f7aa0de2`](https://github.com/pnxenopoulos/esta/tree/0e81f74d480689a83f6e1e90835c1eb6f7aa0de2). ESTA is attributed to Peter Xenopoulos and contributors and publishes its data under **CC-BY-SA-4.0**. The complete source license is in `data/manifests/ESTA-LICENSE.txt`. Preserve that attribution, license and change notice when distributing source or adapted data. This data license is separate from the project's code and DECOY licenses.

Each record in `data/manifests/esta-dust2-v1.json` has an immutable download URL, SHA-256, compressed byte count, match and demo identities, event, date, HLTV source match link, and fixed split. The manifest itself is small and sufficient to rebuild the raw cache.

## Current corpus

| Measure | Verified count |
|---|---:|
| Source maps / matches | 12 / 12 |
| Events / tournaments | 7 |
| Raw compressed bytes | 33,268,048 |
| Rounds | 325 |
| Raw frames | 61,666 |
| Accepted active-round frames | 58,544 |
| Accepted active-round events | 64,475 |
| Pre/post-round frames excluded | 3,115 |
| Incomplete-roster frames excluded | 7 |
| Pre/post-round events excluded | 1,080 |
| Midround / postplant candidates | 181 / 119 |
| Train / validation / test maps | 8 / 2 / 2 |

The event names are IEM Fall 2021 Europe, PGL Major Stockholm 2021, BLAST Premier Fall Final 2021, IEM Winter 2021, BLAST Premier World Final 2021, ESL Pro League Season 15, and PGL Major Antwerp 2022. Dates and match links are in the manifest.

The sample is the first 12 Dust II LAN entries in lexicographic source path order, without filtering by outcome. This is an engineering corpus for testing the pipeline. It is not a representative competitive benchmark or enough data to establish a strong general tactical policy.

Splits are chronological by source match date, with all frames and rounds of a match assigned together. Different map IDs belonging to the same source match must also stay together when extending the corpus; the manifest validator rejects cross-split matches. Players, teams, and events can repeat across the current splits. A future generalization study needs deliberate player/team/event holdouts and more matches.

## Reproduce

After the main environment is installed, from the project directory:

```powershell
.venv\Scripts\igl.exe fetch
.venv\Scripts\igl.exe prepare
.venv\Scripts\igl.exe audit
.venv\Scripts\python.exe -m pytest tests/test_data.py -q
```

`fetch` verifies every existing raw file's byte count and SHA-256 before reporting a cache hit. A corrupt cache is an error. Missing files download to `.part` files, are length-checked and hashed, then renamed only after verification. `prepare` verifies the source again, normalizes, validates, and writes deterministic gzip output. No Awpy package or Go compiler is needed to consume these already parsed files.

Paths:

- `data/raw/esta/<demo_id>.json.xz`: unchanged upstream payloads.
- `data/processed/<demo_id>.json.gz`: normalized replay, schema version 1.
- `data/processed/summary.json`: per-map counts, splits and output checksums.
- `data/processed/scenarios.json`: conservative candidate frame index, not geometry certification.
- `tests/fixtures/esta_round_excerpt.json.xz`: small real round 3 excerpt from ENCE vs FaZe, ESL Pro League Season 15, with subsampled frames and source events retained; same attribution/license as the source.

## Canonical replay contract

The top-level `match_id` is ESTA's **demo ID**: it uniquely identifies this map recording and its filename. The source's actual multi-map match ID is `source.match_id`, which is the grouping key for split protection. `source.label` supplies the human-readable teams and event.

```text
schema_version: 1
match_id, map: de_dust2, game: csgo
source: URL, commit, license, attribution, raw SHA-256, source match/demo IDs,
        event, match URL/date, parser settings, server variables, normalization counts
rounds[]:
  number, winner, start_tick, freeze_end_tick, end_tick, plant_tick, teams, score_start
  frames[]:
    tick, time, source_seconds, source_clock_time, round_time_remaining
    players[]: id, team, name, x/y/z, yaw/pitch, hp, alive, weapon,
               armor, helmet, defuser, bomb, inventory, velocity, spotters,
               blinded, airborne, ducking, defusing, planting, reloading, scoped, cash
    bomb: state, x/y/z, carrier_id, time_remaining, timer_basis, site
    utility: smokes, fires, projectiles
  events[]: type, tick, time, source_seconds, original event fields
limitations[]
```

Player and event Steam IDs become decimal strings so JavaScript does not lose precision above `2^53`. Coordinates remain original Source world coordinates, with elevation retained. The radar/waypoint adapters perform later transformations. Player slots contain dead players when recorded; positions are never filled from the future. If the source loses a slot, that frame is excluded and counted rather than inventing a replacement. Raw data remains available for separate analysis.

`time` is `(tick - freezeTimeEndTick) / reported tickRate`, continuously measured from freeze end. **ESTA's `seconds` field resets to zero after bomb planting**, so copying it directly would create a backwards replay timeline. We preserve it as `source_seconds` for auditing. Some source demos report 127 Hz instead of 128 Hz; the adapter preserves that metadata and does not silently claim an engine-accurate time correction. Frames are nominally sampled every 64 ticks, approximately twice a second.

Many source server timer variables are zero/unavailable. Before a plant, `round_time_remaining` uses the source display clock. While planted, that field is null and the bomb owns `time_remaining`. When a valid bomb timer cvar is available, remaining time derives from that cvar and plant tick. Otherwise it uses the reported display clock, with `timer_basis=source_display_clock_quantized_1s`. This has up to roughly one second of display quantization and is not an exact hidden bomb timer. Missing information stays null.

Frames and events outside freeze-end through round-end ticks are excluded. This matters: the source can include a bomb plant **after** the round was already won by elimination. Such events must not be offered as live-round scenarios.

## Scenario candidates and training boundary

### Replay utility and firing telemetry

`web/telemetry.js` reads the preserved inventory and event fields without changing the corpus. Grenade quantities follow the historical Awpy representation: non-flash grenade entries each represent one grenade; flash quantity uses `ammoInMagazine + ammoInReserve`. Missing/negative flash quantities remain unknown. An unavailable inventory is distinct from a known empty inventory.

The viewer uses frame utility positions directly and event timestamps on the canonical continuous clock. It does not interpolate grenade flight or invent smoke radius, fire coverage, explosion times or bullet impacts. Grenade `throwerX/Y/Z` identifies the recorded projectile origin. `destroyTick` represents entity destruction, **not a reliable detonation timestamp**, so it is not used to synthesize explosion markers. Flash events mark affected player locations. Gunfire markers use recorded firearm origins and aim angles, excluding knife and grenade weapon-fire records.

Some raw ESTA smoke entries have `startTick` later than the frame containing them. Those inconsistent entries are excluded from the visualization, counted in diagnostics and flagged in the viewer. This rendering filter does not rewrite the raw/normalized records or certify the remaining smoke data as complete. Future events never appear early when seeking. Friendly-only filters suppress world utility effects with unknown ownership and opponent firing; this remains a display filter, not a reconstructed perception model.

### Candidate selection

The candidate index selects at most one midround and one postplant frame per round. Both sides must have a surviving player. Frames must show no active smokes, fires or projectiles, and no living player currently blinded, airborne, planting, defusing or reloading. Missing utility fields disqualify a candidate. Postplant candidates require at least 12 displayed seconds remaining; midround candidates start at 45 seconds elapsed. Every candidate carries `geometry_validated=false` until the navigation/scenario adapter verifies it.

This conservative filter does **not** imply full engine restoration. Inventory can still contain grenades; map version, collision geometry, ammo/recoil, sounds, utility execution, and team knowledge need their own support or an explicitly restricted scenario. Refer to the simulator's capability report before treating a candidate as playable.

These files are omniscient replay records. `winner`, future events and enemy coordinates are not policy inputs. The future learning pipeline must build team observations separately, apply information restrictions, and ensure that event extraction does not peek ahead. `spotters` preserves source information but does not reconstruct all vision, communication or sounds. The dataset contains no IGL voice calls, intended strategy labels, or counterfactual outcomes.

No model is trained by `fetch`, `prepare`, `audit`, or the tests. Adding raw CS2 `.dem` ingestion is a separate adapter task: this importer intentionally accepts historical ESTA/Awpy-1.x Dust II JSON only, and does not claim CS2 compatibility.

## Python API

```python
from igl.catalog import fetch_dataset, normalize_dataset
from igl.data import load_replay, normalize_esta, import_esta, build_scenario_index

fetch_dataset(manifest_path, raw_directory, limit=None)
summary = normalize_dataset(manifest_path, raw_directory, processed_directory, limit=None)
replay = load_replay("data/processed/<demo_id>.json.gz")
replay = normalize_esta("example.json.xz", source={"license": "CC-BY-SA-4.0"})
replay = import_esta("example.json.xz", "output.json.gz", provenance={})
candidates = build_scenario_index(replay, split="train")
```

`load_replay` supports `.json`, `.json.gz`, and `.json.xz`; it only decodes the container. `normalize_esta` performs the format conversion. `import_esta` additionally invokes the canonical schema validator before writing. `build_scenario_index` identifies recorded starting states; it neither restores a simulator nor chooses tactical actions.
