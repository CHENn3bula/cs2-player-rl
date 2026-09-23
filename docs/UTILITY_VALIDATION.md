# Utility reference data and validation plan

Design date: 2026-09-18. This is a proposed acceptance plan. No original-game utility capture, calibrated parameter fit or utility fidelity test has been completed by writing this document.

The custom-simulator implementation is paused in favor of evaluating an [original-game backend](ORIGINAL_GAME_BACKEND.md). Capture provenance, bot execution checks, observation filtering and reset checks remain relevant. Fitting our own grenade/effect equations is deferred unless the original-game route proves unsuitable.

Read [UTILITY_SYSTEM.md](UTILITY_SYSTEM.md) for the architecture. Validation is per game/build, map revision, capability and scenario envelope. The existing foundation tests do not certify grenade behavior.

## 1. First milestone

Demonstrate one stationary smoke and one stationary flash on Dust II, executed through actual inventory, bot preparation, physical flight, detonation, effect state and legal perception. Select launch points only after checking reference geometry; do not invent coordinates from a radar image.

The demonstration must include:

1. Correct execution from the measured launch pose, with recorded versus simulated trajectory and effect timing shown together.
2. The same named order issued from T spawn: travel to its launch region, or fail with a concrete reason before its deadline. It must not create an effect at the target directly.
3. A direct throw from a different origin: simulate that origin's flight and result. No destination correction.
4. A target behind solid cover and another exposed target with matched distance; blindness depends on the measured visibility conditions.
5. A bot inside a smoke-blocked sightline and a fully blinded bot: neither receives newly visible enemy coordinates nor engages using hidden current coordinates.
6. Interruptions before and after release, double submission, item exhaustion, expiry and reset.
7. Pause/seek/replay rendering agrees with authoritative state without changing it.

These checks establish a useful restricted capability. They do not establish full game parity or strategic transfer.

## 2. Reference environment

Use a local/private original-game session whose build and map assets can be recorded. The minimum method is manual controlled setup plus recordings; automation is optional initially. Record all commands/settings used for reproducibility. Confirm that instrumentation does not change the mechanic under test.

Required environment manifest:

| Field | Meaning |
|---|---|
| `reference_id` | Immutable capture batch identity |
| `game`, `build`, `client_version` | Exact installed family/build, unknown explicitly recorded |
| `map_name`, `map_hash`, `collision_hash` | Identity of playable map and exported simulator geometry |
| `server_settings` | Relevant cvars/settings, team damage, mode and bot settings |
| `client_settings` | Visual settings for smoke/flash visibility measurements |
| `capture_tools` | Parser, bridge and capture versions/commits |
| `clock` | Tick interval, time base, sub-tick availability and synchronization method |
| `files` | Raw demo/log/video paths, sizes, SHA-256 and source/license/provenance |

Keep historical CS:GO and CS2 captures in separate profile namespaces. If the old CS:GO build cannot be reproduced, its demos are observational evidence with unknown version alignment, not a controlled reference for CS2.

One possible automation component is CS2-Bot-Controller, whose maintainer documents bot input control and movement recording/replay. Its compatibility, state-reset coverage, measurement perturbation and exact throw reproducibility must be tested before adoption. It is not presently an installed or verified backend in this project. [Maintainer repository](https://github.com/XBribo/CS2-Bot-Controller)

## 3. Per-trial contract

Each trial contains the intended input, measured realized input, outcome and uncertainty. Commanded input is not sufficient if the engine applied it later or from a different pose.

- **Identity:** case family, trial/repetition ID, profile and environment manifest, split assignment.
- **Thrower state:** stable player ID, team, feet/eye/release coordinates, yaw/pitch, velocity, stance, ground state, inventory, equipped item, input/button sequence with timestamps.
- **Projectile:** instance identity/generation, actual release state, timestamped XYZ/velocity where observable, contacts/surfaces where observable, activation/detonation/destruction with distinct semantics.
- **Targets:** timestamped position, eye pose, facing, stance, HP, numeric armor, team, prior blindness and controlled movement.
- **Effects:** flash intensity/duration signals; smoke lifecycle plus ray visibility/player-view captures; HE health/armor deltas; fire occupied surfaces where observable and damage/expiry; sound reports if available.
- **Evidence quality:** observed, reconstructed, estimated or unavailable for each channel; source timing resolution; missing intervals; attribution ambiguity; measurement error.

Do not make up a trajectory or spread volume when the parser provides only an origin. Preserve null for missing velocity, duration, shape or input. A destroyed projectile does not necessarily identify the relevant effect event.

### Demo extraction

The current ESTA corpus is sparse parsed CS:GO data, not the original binary demos. It can nominate tactical situations, inventory patterns and candidate throws. It cannot certify exact launch input or small-scale collision behavior. Its display interpolation is forbidden as calibration evidence.

For CS2 raw demos, select and pin one parser/version, then run an actual field-availability audit before defining an extractor. Demoparser2 documents tick properties and grenade parsing; advertised fields are not guaranteed to be present in every demo. Avoid combining schemas from different Awpy parser generations. [Demoparser2 maintainer repository](https://github.com/LaihoE/demoparser)

Current Awpy datasets describe projectile identity using both entity index and serial. They also document reconstructing blindness when a direct event is absent. Retain that distinction and mark source attribution ambiguous when multiple flashes are candidates. Demo smoke/fire summary records do not by themselves supply their full occupied geometry. [Awpy dataset documentation](https://awpy.readthedocs.io/en/stable/datasets.html)

Smoke visibility needs controlled rendered observations as well as geometry; a server-side occlusion bit or a collision ray is not automatically what a human could see. Measure flash intensity recovery where possible, not just a nominal networked duration. Never promise exact full game state restoration from an ordinary demo.

## 4. Capture matrix

Start small and extend only after the first pair works. Suggested first batch: twelve distinct scenario configurations per utility with five repetitions each, for 120 smoke/flash trials. This is an engineering pilot, not a statistically established sample size. Increase repetitions or coverage when observed variance and failures require it.

| Family | Vary | Why |
|---|---|---|
| Free flight | Several aims/strengths, standing pose | Identify launch and gravity independently of bouncing |
| First contact | Floor, wall, slope, corner | Separate collision geometry from response errors |
| Release clearance | Close wall, ceiling, ledge | Detect spawning through geometry and invalid initial overlap |
| Flash | Target distance, full view, side view, looking away | Fit effect response and recovery |
| Flash cover | Solid wall, edge exposure, elevation | Verify occlusion and partial-cover behavior |
| Smoke | Open space, narrow passage, corner, elevated edge | Measure growth, leakage and sightline coverage |
| Timing | Different release phases and target arrival times | Measure event quantization and synchronization |
| Interruption | Move/re-aim, cancel/death before/after release | Verify state-machine semantics |

Additional batches cover moving/jump throws only once supported; player collisions; stacked flashes; overlapping smoke; smoke/flash; HE/smoke; fire/extinguishing; damage armor/team rules; sound/decoys; breakables; and gunfire/smoke after an explicit shot backend exists.

Perturb position, angle and input timing around every proposed recipe. Learn its allowed tolerance region from observed success, rather than declaring a generous radius. Report misses and aborts as well as successful throws. A narrow lineup may remain narrow even if the average endpoint is accurate.

Record original-game trial variation before fitting. If the same nominal action produces variable realized inputs, evaluate distributions or match on measured release state; do not blame all variance on the simulator.

## 5. Splits and calibration

Freeze splits before fitting parameters. Keep repeated/perturbed versions of the same setup together. Hold out complete throw families and locations as a check against overfitting, not merely random trajectory samples. Keep professional match/event splits separate from controlled-capture splits.

Use calibration captures to estimate parameters, development captures to choose model complexity, and untouched test captures for the final report. With the small pilot, reserve at least one whole configuration of each important family when feasible; absence of a held-out family is reported as untested coverage.

Calibrate in dependency order:

1. Coordinate/eye/release alignment and collision geometry.
2. Launch and free flight.
3. Contact response and detonation predicates.
4. Flash/smoke effects in controlled scenes.
5. Inventory/action timing, perception and integrated combat restrictions.
6. Cross-utility interactions and tactical recipe reliability.

Do not compensate for an incorrect wall position by tuning bounce speed. Do not tune flash strength to hide a bad eye-height transform. Changes to upstream parameters invalidate dependent reports.

## 6. Acceptance criteria

The numerical targets below are **proposed project tolerances**, not Valve specifications or achieved measurements. Review them after measuring reference resolution and repeatability, then freeze them before the holdout evaluation. Report median, 95th percentile, worst case and coverage for each family; an overall average cannot hide an important failure.

| Capability | Proposed acceptance target |
|---|---|
| State invariants | Zero duplicate releases, negative inventory, owner changes, teleport-to-target effects or future-data leaks in the test matrix |
| Collision | Correct bounce/obstruction classification on every declared reference case; no tunneling or propagation through fully solid separating walls |
| Free flight | 95th-percentile position error <= 8 Hammer units on aligned reference samples; detonation position error <= 16 units for the initial subset |
| Flight/event timing | Error <= 2 reference capture intervals; record its absolute value and reject capture resolution too coarse for the intended timing study |
| Flash | Blindness duration error <= 0.15 seconds at the 95th percentile; intensity/recovery error also reported; no false visibility through fully opaque solid cover |
| Smoke | >= 95% agreement on a balanced set of visible/blocked ray-time cases, with separate false-clear/false-block rates; each tactically critical sightline must pass individually |
| Smoke timing | Start/expiry error <= 0.15 seconds; growth/edge transitions and boundary uncertainty reported |
| HE, later | 95th-percentile health damage error <= 5 HP; numeric armor loss and cover failure cases independently checked |
| Fire, later | >= 0.85 occupied-surface overlap at declared sample times plus correct critical passage blocking; damage/timing checked separately |
| Repeatability | Same inputs/seed give the same events and bounded numeric state on the pinned platform; restore-and-continue matches uninterrupted simulation |

Only apply a target when it is actually measurable. Sparse reference data cannot receive a pass by interpolation. When reference uncertainty exceeds a target, mark it inconclusive, improve capture, or revise the experiment's scope transparently.

For a recipe, compare useful coverage and timing in addition to endpoint error. A smoke landing sixteen units away may open a decisive gap; a flash meeting the duration metric may arrive too late. Require all named critical tactical checks to pass regardless of aggregate scores. Report recipe success counts and binomial uncertainty intervals; five pilot repetitions cannot certify a 95% success probability.

## 7. Automated engineering checks

These checks verify implementation properties and are distinct from original-game comparison:

- Analytic no-collision flight, units, gravity independence, angle transforms and release clearance.
- Multiple bounces per slice, thin walls, corners, rest/fuse behavior, contact-work overflow and numerical convergence.
- Event order, simultaneous utility damage, release/death ties, thrown ownership after death, item reservation, duplicate commands, timeout and weapon recovery.
- Partial-step clock accumulation; `step(a); step(b)` versus `step(a+b)` under the same documented input schedule.
- Fresh reset, cleanup, complete checkpoint restore and same-platform reproducibility.
- Observation reads do not mutate state or RNG. Team ownership, enemy inventory filtering, hidden effect identity and sound localization remain legal.
- A blinded player cannot acquire a target merely because a teammate sees it. Smoke visibility and combat gating use the same effect state.
- Display-only interpolation and cosmetic variation do not change any physics, perception, checkpoint or measurement output.
- Legacy replay loading preserves unknown utility status and 64-bit identity. Recorded raw data checksums do not change.

Use actual Bullet/map integration tests after small synthetic geometry tests. Tests that merely repeat the implementation's formula are insufficient evidence of game fidelity.

## 8. Reports and failure behavior

Produce a machine-readable report per profile/capability containing source hashes, coverage, exclusions, fit IDs, holdout IDs, errors, uncertainty, failed cases and pass/inconclusive/fail status. Keep raw logs alongside overlays and concise visual comparisons in the viewer.

Capability levels:

```text
unimplemented -> experimental -> measured -> validated_for_declared_subset
```

Passing a projectile test cannot promote smoke, flash or combat. A changed map/build/model invalidates dependent validations until rechecked. A scenario's requirements must be a subset of available validated capabilities for validated evaluation; reject mismatches with specific reasons. Engineering runs can opt into experimental behavior and label results accordingly.

Numerical errors, invalid geometry state or unknown effects during a rollout invalidate that rollout. They do not count as wins/losses or attractive terminal rewards in future RL. Keep failure rates visible; silently dropping difficult cases would bias results.

## 9. Performance and future RL boundary

Benchmark startup and stepping separately: ten players, no utility; realistic recorded concurrency; and a stress scene with overlapping utility. Report simulated seconds per wall-clock second, peak memory, query counts and tail latency on named hardware. Compare numerical/voxel resolutions before optimizing. No present benchmark measures utility throughput.

Replay spatial structures may be cached by geometry/profile hash. State, event queues and RNG are per episode. Preserve subprocess isolation for Panda3D as used by the current runtime. Reference-game stepping/reset limits must be measured rather than assuming accelerated deterministic rollouts.

Before RL, replace the omniscient systems-test opponent, declare the communication/combat subset, and check tactical rankings under plausible parameter uncertainty. Randomizing uncertain parameters is a robustness experiment, not evidence that their central values are correct. Ground-truth enemy effects may be used for offline validation and future training rewards, never ordinary policy input.

The first deliverable is a verified utility capability with evidence. Agent training remains a separate project stage.
