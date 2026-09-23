# Counter-Strike player RL foundation

A local research workspace for professional-match replay and controllable 5v5 Counter-Strike simulation. **No ML policy is trained or running.** The simulator uses the actual pinned DECOY Panda3D/Bullet implementation and its published combat models for inference.

**Direction updated 2026-09-23:** investigate an RL agent that plays as one player, with an optional selectable IGL role. Start by proving player input control and observations, then train individual play, and later add role conditioning and team communication. The current runtime remains the replay/DECOY foundation; player RL and role selection are planned. See the [prioritized TODO list](TODO.md) and [player-agent task proposal](docs/RL_TASK.md).

The current supported target is **historical CS:GO Dust II**, shown through a 2D tactical viewer. This is not the CS2 engine and is not a faithful simulation of every CS mechanic. Read the capability boundaries below before interpreting a bot outcome as tactical evidence.

## Open the prepared workspace

From PowerShell in this project:

```powershell
.\scripts\serve.ps1
```

Open [the local tactical viewer](http://127.0.0.1:8765). Select a professional match and round, then play or scrub the timeline. **Load tested post-plant** selects a verified G2–ENCE 2v2; **Branch simulation** starts a new DECOY rollout from that snapshot. **Return to recording** returns to the original match. Recorded and simulated outcomes are labeled separately.

The tested snapshot is G2 vs ENCE, IEM Fall 2021 Europe, round 6, frame index 217. Its original and simulated continuations can differ. A recorded future is never used to force the simulated opponent's movements.

The viewer's team filter shows friendly positions only. It is not a reconstructed human perception model. Snapshot exports always contain the full privileged state for reproducible initialization, irrespective of the viewer filter.

Grenade movement is visually interpolated between the roughly 2 Hz source samples. Anonymous grenades are matched conservatively for display; ambiguous transitions retain their recorded positions. Pausing preserves the exact displayed moment. This smoothing does not modify exported snapshots or training data.

Player cards show grenade icons and remaining smoke, flash, HE, fire and decoy counts, including two flashes when recorded. Player numbers **1–10 stay attached to the same SteamIDs** across frames, deaths, side swaps and rounds; the roster uses the same stable ordering. **Utility activity** draws animated smoke clouds, fire patches, grenade icons and flash-hit effects at recorded positions. **Gunfire direction** shows brief shot-direction markers. Play, pause and scrubbing all use replay time. Smoke/fire footprints are illustrative rather than exact effect geometry; missing telemetry stays unknown. These are recorded-demo features: DECOY does not simulate utility use or individual shots.

## Rebuild on another machine

Prerequisites: Python **3.12**, Git, Node.js for viewer tests, network access, and disk space for two Python environments, DECOY, and the corpus. Windows is the verified platform. No graphics window or GPU is required for the smoke simulation.

```powershell
.\scripts\bootstrap.ps1 -Python312 C:\Path\To\Python312\python.exe
```

On this machine the script can also find the Codex-bundled Python if no path is supplied. It creates `.venv` and `.venv-decoy`, installs pinned dependencies, fetches pinned DECOY source and checksummed assets, downloads the dataset, normalizes it, exports navigation, and runs verification. It never trains a model.

The environments are separate because the replay/data tools do not need Torch or Panda3D. The DECOY wrapper imports Torch before Panda3D to avoid a Windows DLL-loading conflict found during setup.

## Data included

The **full public ESTA Dust II LAN corpus** has also been gathered: **75 professional maps, 1,963 rounds, 352,117 frames and 394,130 events**, spanning 11 tournaments. It contains **1,739 scenario candidates** and uses match-disjoint chronological splits of **60 / 7 / 8**. All 680 source LAN-file headers were inspected to identify the 75 Dust II maps. The full normalized corpus is in `data/processed-full/`; see [full-corpus provenance and commands](docs/FULL_DATA.md).

The viewer defaults to the smaller sample below for quicker startup. To browse all 75 maps, stop the running server and launch `.\scripts\serve.ps1 -Corpus full`. The first catalog load takes longer. Do not mix the two manifests' independent split assignments in a training/evaluation benchmark.

The default engineering sample contains **12 real professional Dust II maps from seven tournaments**, with **325 rounds, 58,544 active-round frames, and 64,475 events**. Both corpora contain ESTA's published parsed-demo JSON files, **not original binary `.dem` files**. Raw bytes remain unchanged; normalized outputs are deterministic gzip JSON. All downloads have immutable commit URLs, byte counts, SHA-256 hashes, and source attribution.

There are 300 conservative scenario candidates: 181 mid-round and 119 post-plant. A candidate is not automatically certified for DECOY: active utility, unsupported equipment, missing information, or excessive map displacement can still make a branch invalid. The tested 2v2 is a working strict example.

Eight matches are assigned to training, two to validation, and two to test, in chronological order. Splits are reserved for future work; no training was performed. This small engineering sample establishes pipeline behavior, not tactical generalization. See [data documentation](docs/DATA.md) for source limitations, attribution, timing reconstruction, and how to extend the manifest.

## Commands

```powershell
# Verify/reuse downloaded raw bytes, then rebuild normalized replays
.venv\Scripts\python.exe -m igl fetch
.venv\Scripts\python.exe -m igl prepare

# Check checksums, schemas, time, rosters, splits and waypoint alignment
.venv\Scripts\python.exe -m igl audit

# Export effective DECOY navigation and run an actual 5v5 systems test
.venv\Scripts\python.exe -m igl export-map
.venv\Scripts\python.exe -m igl smoke

# Full repeatable check: Python tests, real runtime tests, Node tests,
# corpus audit, 5v5 smoke and a strict professional-demo branch
.venv\Scripts\python.exe scripts/verify.py

# Rebuild and independently audit the larger corpus
.venv\Scripts\python.exe scripts/gather_lan_corpus.py
.venv\Scripts\python.exe -m igl audit --manifest data/manifests/esta-dust2-lan-full-v1.json --processed-dir data/processed-full --report reports/full_data_audit.json
```

Export or branch a professional starting state:

```powershell
.venv\Scripts\python.exe -m igl scenario data/processed/0520c3de-fdfe-4387-8060-5916549ad991.json.gz --round 6 --frame 217 --output data/scenarios/example.json
.venv\Scripts\python.exe -m igl simulate data/scenarios/example.json --seed 42 --seconds 30 --output data/simulations/example.json
```

Create auditable waypoint targets for one recorded round:

```powershell
.venv\Scripts\python.exe -m igl project data/processed/0520c3de-fdfe-4387-8060-5916549ad991.json.gz --round 1 --output data/derived/round1.json
```

The projection keeps per-point displacement and legal directed routes; points beyond its tolerance and impossible timing segments are rejected. It does not infer tactical intent or certify collision-free snapping across thin walls.

## What is functioning

- Original DECOY Dust II mesh, Bullet physics and effective directed navigation graph.
- Ten persistent player slots, controllable with `hold`, `move`, `plant`, and `defuse` orders; commander team ownership checks.
- Bounded stepping, seeded reset, reproducible trajectories on the tested runtime, and round termination.
- Explicit timed plant and kit-dependent defuse approximations, including post-plant survival of the round after all Ts die.
- Strict professional snapshot restore with displacement reports and unsupported-state rejection.
- Separate privileged state and approximate team observations, with FOV/raycast enemy filtering and last-seen history.
- Public-data acquisition, validation, projection, scenario export, and 2D playback.

## Limits that remain

- DECOY's map revision is not specified upstream; the pinned asset and checksum identify exactly what we used. Matching map names alone does not prove geometry equivalence.
- No smoke, flash, HE, incendiary, hearing, wall penetration, ammo/reload, crouch, economy, or realistic movement inertia simulation. Active unsupported effects are rejected in strict restore. Utility inventory remains in the data but cannot be executed by the bots.
- Movement uses fixed knife speed; combat uses published learned CS:GO outcome models. No calibration or transfer to current CS2 is claimed.
- Restoring a snapshot snaps positions to waypoints and resets velocity. It does not restore all hidden Source engine state.
- The bundled scripted opponent uses privileged routing as a **systems test**, not a fair evaluation opponent. Policy observations are a separate API. It must be replaced before comparing learned player skill.
- Demo voice/calls and intent labels are absent. A geometric action target is not an IGL-call label.
- Full match economy, reward design, learning algorithms, and policy training are deliberately deferred.

See [the DECOY audit](docs/DECOY_AUDIT.md), [architecture and interfaces](docs/ARCHITECTURE.md), and [verification evidence](docs/VERIFICATION.md).

The revised [original-game backend proposal](docs/ORIGINAL_GAME_BACKEND.md) evaluates running CS2 behind the existing 2D interface. The custom [utility system design](docs/UTILITY_SYSTEM.md) and [validation plan](docs/UTILITY_VALIDATION.md) are paused alternatives. These are proposals; the running backend remains DECOY with no simulated utility support.

The [player RL task proposal](docs/RL_TASK.md) defines the new control boundary, proposed observations/actions, outcome rewards, episodes and evaluation. Post-plant/retake scenarios remain a proposed initial curriculum after basic player controls work. The previous five-player commander design is [archived](docs/IGL_TASK_ARCHIVE.md). Existing `igl` package and CLI names remain for compatibility; they do not imply an implemented learned IGL.

## Layout

| Path | Purpose |
|---|---|
| `src/igl/` | Data, schema, navigation, scenario, runtime, CLI and local server |
| `web/` | Dependency-free 2D tactical viewer and its tests |
| `data/manifests/` | Pinned datasets/assets and licenses; tracked in Git |
| `data/raw/`, `data/processed/` | Downloaded source and normalized replays; rebuildable |
| `data/scenarios/`, `data/simulations/` | Snapshot inputs and simulation outputs |
| `vendor/decoy/` | Pinned upstream checkout; fetched by setup |
| `reports/` | Actual test, alignment, browser and simulation evidence |

Large downloaded files, virtual environments and generated outputs are ignored by Git. Preserve the checked-in manifests to reproduce them. Third-party game assets and data retain their respective provenance and licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
