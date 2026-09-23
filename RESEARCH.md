# Counter-Strike IGL simulation research

Historical research: the active direction changed on 2026-09-23 to a player RL agent with an optional IGL role. See [the current task](docs/RL_TASK.md) and [TODO list](TODO.md). The commander recommendations below preserve earlier investigation and are not the active plan.

Research date: 2026-09-17. These are the original source-review notes. Implementation now exists; see [README.md](README.md) and [verification evidence](docs/VERIFICATION.md) for the current tested state. No ML policy has been trained.

## Scope and recommendation

Learn mid-round and late-round Counter-Strike decisions, with one IGL controlling five bots against five opposing bots. The user's clarified priority is fidelity to the original game; switching from Mirage to Dust II is acceptable if necessary. Treat the IGL as a learned team policy; movement, aim, and combat execution initially belong to fixed low-level controllers.

Updated recommendation: first evaluate DECOY on its supplied Dust II map, retaining its 3D geometry behind a 2D tactical interface. This supersedes the initial SiDeGame-first recommendation because original-game fidelity now takes priority over a purely 2D engine. Neither reviewed project supplies a verified, complete Mirage IGL training environment. Engine selection remains provisional until reset, control, geometry, and performance checks pass. The Mirage-specific pipeline and milestones below describe the original scope and should use Dust II for this initial evaluation.

DECOY is a CS:GO approximation, not the original CS2 engine. Its learned combat outcomes and simplified action interface must be audited before using it to judge tactical quality. Preserve original map coordinates, traversal, visibility, equipment, bomb interactions, and utility effects wherever practical; keep approximation choices explicit and validate them against same-version demos.

For maximum mechanics fidelity, a separate candidate is an actual private CS2 server with a 2D tactical interface and bot-control bridge. [CS2-Bot-Controller](https://github.com/XBribo/CS2-Bot-Controller) documents engine-level bot locks and command injection; it is an integration building block, not a verified complete RL environment. Reset/restore coverage, navigation orders, utility execution, observation filtering, current-build compatibility, and accelerated simulation remain to be tested. This route would not itself require abandoning Mirage. Keep it as the reference-backend option if DECOY's abstractions invalidate the target tactics.

## Existing foundations

| Project | Verified capability | Fit and missing work |
|---|---|---|
| [SiDeGame](https://github.com/JernejPuc/sidegame-py) | Python 2D defusal environment; original 5v5 setup; imitation-learning example; synchronous `SDGSyncEnv` RL implementation | Closest literal 2D foundation. Ships a Cache-derived map. Requires Mirage, commander actions, demo conversion, and executor validation. Maintainer says no further experiments are planned. |
| [DECOY](https://github.com/HATS-ICT/decoy) | CS:GO strategic simulator using waypoints, Panda3D/Bullet, and learned damage models | Closest strategic research reference. Dust II assets and 3D internals; Mirage and current CS2 calibration require work. |
| [CS2D](https://cs2d.com/serverhosting.php) | Existing game with bots, dedicated server, and Lua scripting | Useful interactive prototype candidate. Deterministic stepping, accelerated training, state restore, and a compatible Mirage map remain unverified. |

SiDeGame code is marked MPL-2.0; DECOY is marked MIT. Game/map/audio assets need separate provenance tracking; a repository's code license should not be assumed to cover every asset.

DECOY source inspection found a concrete interface mismatch: `observation_space()` declares shape `(3,)`, while `Agent.observation` returns position plus health, bomb, and teammate features. Its action space is nine movement/stop actions; bomb handling triggers automatically from location. These are reasons to audit and extend the implementation before treating it as an IGL benchmark. Sources: [environment](https://github.com/HATS-ICT/decoy/blob/main/env/csgo_environment.py), [agent](https://github.com/HATS-ICT/decoy/blob/main/env/agent.py), [configuration](https://github.com/HATS-ICT/decoy/blob/main/env/config.py).

The [DECOY paper](https://arxiv.org/abs/2509.06355) is useful evidence for abstracting combat through data-calibrated outcomes. Its reported replay agreement is not proof that a trained policy will remain realistic under novel tactics.

## Proposed control design

Start with one recurrent commander producing coordinated orders for five player slots. Each order includes a destination/region, behavior, look direction, timing or synchronization condition, and optional utility instruction. Dead slots are masked. Example behaviors: hold, clear, take space, rotate, regroup, trade a teammate, execute, plant, retake, and save.

Use fixed execution bots initially so improvements can be attributed to IGL decisions. Later compare a shared player policy conditioned on role and commander orders. MAPPO is a reasonable multi-agent baseline for that later stage, not a prerequisite for a single team controller. See the [MAPPO paper](https://arxiv.org/abs/2103.01955).

The commander should receive team-visible information: friendly state, round clock, inventory, known bomb information, last enemy sightings with age, and modeled sound reports. It should never receive unseen enemy coordinates as ordinary input. Keep an omniscient state only for rendering, diagnostics, and optionally the training critic. Instant perfect teammate communication would be an explicit initial simplification.

A 2D display can retain elevation-aware navigation and visibility internally. Mirage must preserve traversable routes, cover, directional drops, and relevant elevation relationships. A radar image alone cannot define those rules. Smokes, flashes, and incendiaries must change observations or behavior; otherwise execute and retake decisions lose their meaning.

## Demo pipeline

Use current CS2 Mirage demos as the target corpus. [Demoparser2](https://github.com/LaihoE/demoparser) exposes tick properties and events. [Awpy](https://awpy.readthedocs.io/en/stable/) provides parsing and analysis; its [map assets and visibility tools](https://awpy.readthedocs.io/en/stable/visibility.html) provide versioned geometry and coordinate transforms. Verify the selected version rather than mixing older Awpy tutorials with current APIs.

1. Record source, match, map/game version, parser version, and checksum for every demo.
2. Extract synchronized positions including height, orientation, health, equipment, utility, bomb events, round clock, damage, deaths, and outcome. Validate actual parser field availability on sample demos.
3. Map trajectories onto the simulator's navigable representation; reject impossible paths rather than silently snapping across walls or floors.
4. Reconstruct each team's observation history using geometry, view direction, dynamic utility, and explicit hearing assumptions. Geometry line-of-sight alone is not proof that a human saw an opponent.
5. Derive behavior targets from future trajectories and events: destinations, rotations, regrouping, utility timing, and site commitments. Future data may define labels, never input features.
6. Split by match/event and time before sampling windows. Hold out teams or styles for additional generalization evaluation.

Ordinary match demos should not be treated as ground-truth IGL call labels. Movement reveals behavior, but may not reveal whether it resulted from a call, an individual reaction, or a failed plan. Use weak labels with uncertainty, supplemented by a small manually reviewed tactical dataset.

[ESTA](https://github.com/pnxenopoulos/esta) is an available historical CS:GO dataset with 2 Hz snapshots and events. It can help prototype schemas and models, but needs an explicit adapter and should remain separate from the CS2 target distribution.

## Training and validation sequence

1. Prove the engine can run ten controlled entities, reset reproducibly, restore mid-round states, and simulate without rendering. Measure throughput locally.
2. Add Mirage and verify route times, collision, elevation, visibility, bomb interactions, and utility effects against demo examples.
3. Implement scripted baseline commanders and fixed execution bots. Start with post-plant/retake scenarios, then mid-round rotations and site choices, then complete rounds.
4. Pretrain team movement and order prediction with behavior cloning. [Learning to Move Like Professional Counter-Strike Players](https://arxiv.org/abs/2408.13934) supports the feasibility of learning coordinated movement from demos, but does not establish a complete Mirage IGL solution.
5. Fine-tune through simulation against a mixture of scripted opponents and frozen previous policies. Both teams must react to new actions; replaying an opponent's recorded path is unsuitable for strategic counterfactual evaluation.
6. Evaluate on unseen matches, initial states, and opponent policies. Use paired seeds and report uncertainty, not only a single win-rate number.

Primary outcome: round success under equal execution capability. Also measure coordinated arrivals, trade opportunities, rotation timing, utility effectiveness, and realism of engagement distributions. Test simulator sensitivity by varying combat and perception parameters. A policy winning through simulator defects is not evidence of good IGL decisions.

Saving decisions need future economic value. A one-round win/loss reward alone will generally undervalue saving; introduce multi-round economy or an explicitly validated continuation-value estimate when that behavior enters scope.

The first implementation milestone should be a reproducible Mirage scenario with ten bots, team-limited observations, executable commander orders, working round termination, and a top-down viewer. Model scale and hardware budget should follow measured simulator throughput.
