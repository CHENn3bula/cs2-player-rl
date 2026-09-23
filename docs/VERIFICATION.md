# Verification evidence

Run `.venv\Scripts\python.exe scripts/verify.py` to reproduce the automated checks. It fails on missing dependencies/assets, test failures, skipped required runtime tests, invalid source checksums, malformed canonical data, or unsuccessful strict sample branching.

## Publication check — 2026-09-23

The full verification command passed on the existing Windows workspace: 22 Python unit tests, 22 DECOY runtime tests, and 65 Node viewer tests (109 total, no failures or skips), plus asset integrity, corpus/navigation audit, the 5v5 smoke run and strict professional-demo branch. Node was supplied from the bundled runtime through `PATH`. Documentation links were checked separately. This run verifies the existing foundation, not the proposed player RL implementation; a fresh-machine rebuild and new interactive browser checks were not performed for this publication.

## What was executed

- Unit checks for checksum rejection, reproducible normalization, continuous timelines across bomb plants, five-player team slots, split separation, schema corruption, radar transforms, height-aware waypoint matching, directed navigation, and scenario isolation from recorded future events.
- Integration checks using the actual Dust II FBX, Panda3D/Bullet physics, and published DECOY combat models. They cover ten bots, commander ownership, movement/redirection, seeded reproducibility, bomb outcomes, reset clocks, scenario restore, unsupported state rejection, and restricted observations.
- Browser-independent viewer tests for projection, interpolation, discontinuities, visibility filters, input validation, and text escaping.
- A complete headless 5v5 scripted run with a terminal outcome, plus a strict branch from a real professional 2v2 post-plant.
- Interactive browser checks: data loading, visible world-aligned radar, play/pause and speed, frame stepping, friendly-only filtering, snapshot export, tested-scenario selection, simulation branching, seeking to the result, and return to the original recording.

Machine-readable results are generated in `reports/tests.json`, `reports/data_audit.json`, `reports/decoy_smoke_report.json`, `reports/pro_branch_report.json`, `reports/browser.json`, and `reports/foundation.json`. XML and log files retain the actual test output. These files are generated evidence, not hand-written claims of passing tests.

## Observed results

The initial full foundation run passed **48 tests**: 19 data/schema/navigation/scenario unit tests, 22 actual DECOY integration tests, and seven viewer tests. No required runtime test was skipped. Asset revision and checksum verification also passed.

The utility/gunfire viewer extension subsequently passed **44 targeted checks**: 19 Python unit tests and 25 Node viewer/telemetry tests. These include attributed real-data fixtures for double flashes, shot origins/yaw, utility positions, flash-affected players and malformed source smoke timing; they also cover backward scrubbing, event expiry, missing versus empty inventory, simulation boundaries and friendly-only filtering. Run `node --test web/app.test.cjs web/telemetry.test.cjs` for the browser-independent checks. The complete verification script now includes both Node suites; the physics runtime was unchanged by this extension.

Interactive utility checks used FaZe–ENCE demo `00e7fec9-cee0-430f-80f4-6b50443ceacd`: round 1 frame 111 showed recorded smoke, fire, projectile and flash-hit markers; round 2 frame 0 verified broky's two flashes; round 2 frame 64 showed utility and gunfire together. Layer toggles, playback, pause, backward seeking, team filtering and the explicit unsupported state in `pro_branch` were exercised. Browser checks at desktop, 1100px and 390px widths found no horizontal page/card overflow or console errors. A separate read-only check over all 40 G2–ENCE rounds confirmed causal event windows and team isolation; 638 future-start smoke records were excluded in every-seventh-frame sampling. These source anomalies remain in the raw data and must also be handled before future RL feature extraction.

The initial 12-map data corpus passed canonical validation for **325 rounds and 58,544 frames**. All raw checksums and match-level split constraints passed. Sampling every fourth frame yielded per-map 95th-percentile nearest-waypoint distances of approximately **38–52 Hammer units**. Some samples exceed 80 units; these remain visible in alignment reports. That is an alignment measurement, not proof of identical game geometry.

The effective DECOY navigation graph has **6,638 nodes and 48,053 directed edges**, with strong connectivity and neighbor consistency verified.

The full corpus also passed independently: **75 maps, 1,963 rounds, 352,117 frames and 394,130 active-round events**, with no quarantined maps. Raw SHA-256, canonical state/timeline/roster checks and 60/7/8 match-disjoint splits passed. The full geometry audit sampled **700,050 living-player positions**; **6,283 (0.90%)** exceeded 80 Hammer units, with maximum displacement **202.84**. The worst map's 95th percentile was **55.46** units. The full audit is `reports/full_data_audit.json`; reproduce it with the command in FULL_DATA.md.

The seeded 5v5 systems test ended through T elimination after approximately **15.02 simulated seconds**, with no recorded movement stalls. Stepping time was approximately **0.7 seconds**, excluding interpreter, model and map startup; this single run is not a throughput benchmark for arbitrary scenarios or training hardware.

The G2–ENCE professional snapshot (round 6, frame 217) restored a 2v2 post-plant with living-player displacement **5.83–20.83 Hammer units**, no unsupported-state override, and no restore warnings. The scripted branch ended with CT defuse after **15.25 simulated seconds**, with no recorded movement stalls. This is evidence that the pipeline works; it does not establish that the simulated tactic would win in CS:GO.

Browser checks confirmed a recorded-to-simulated round transition and restoration to the exact original frame. Snapshot export contained all ten player slots and source attribution, with no recorded future frames or events. The latest checked page had no console errors or warnings and no horizontal layout overflow. The browser tool could not resize its maximized window; responsive behavior beyond the tested desktop viewport is not claimed.

The full-corpus server mode was exercised separately: its API listed all **75 matches** and **1,739 candidates**, and the same viewer loaded the larger catalog.

## Interpretation

The grenade-motion update passed **87 targeted tests** (65 Node tests and 22 Python tests). Smoothing was checked on FaZe–ENCE round 1, frames 71–72: a 380.28-unit recorded jump becomes 31 distinct, evenly spaced display positions across the interval, with exact sampled endpoints. The original frame stays unchanged. A running browser animation produced 35 distinct grenade positions in 35 animation callbacks. Pausing, redrawing and resuming preserve identical pixels at a fractional timestamp; backward seeking reproduces the same state, and team view keeps projectile overlays hidden. Motion matching is display-only and explicitly marks inferred anonymous matches; it is not an RL observation or a recovered engine trajectory.

The subsequent stable-ID and replay-VFX update passed **65 targeted tests**: 22 Python tests and 43 Node tests across `app.test.cjs`, `telemetry.test.cjs` and `effects.test.cjs`. Coverage includes shuffled player arrays, permanent IDs through death/absence/side swaps, exact 64-bit identities, simulation inheritance, causal identified trails, deterministic replay-time effects and projection-scaled footprints. Browser sampling checked 3,160 player appearances across the 28-round FaZe–ENCE map with **zero number changes**; seeking away and back reproduced identical canvas pixels. The refreshed UI also passed desktop/mobile overflow checks.

This verifies a working engineering foundation for a deliberately limited tactical subset. It does **not** verify current-CS2 equivalence, utility tactics, fair opponent performance, a learned IGL, or real-world tactical quality. Unsupported features and the privileged scripted baseline are described in README.md and DECOY_AUDIT.md. Determinism is checked on this installed runtime; cross-platform bit-identical physics is not promised.
