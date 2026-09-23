# Player RL roadmap

Updated: 2026-09-23. Direction: learn to play as one Counter-Strike player, with IGL as an optional selectable role. This is a development plan; unchecked items are not implemented. See the [task proposal](docs/RL_TASK.md) for contracts and scope.

## Existing foundation

- [x] Professional CS:GO Dust II replay acquisition, provenance and corpus manifests.
- [x] 2D replay viewer, telemetry and recorded utility visualization.
- [x] DECOY adapter, scenario restore, team orders and automated verification.
- [x] Document the player-agent pivot and preserve the former IGL proposal.

There is no trained policy, player-input environment or original-CS2 bridge yet.

## P0 — prove one-player control before training

- [ ] Revise the original-game backend proposal around one player's inputs and observations.
- [ ] Pin and install a private development server, map/build and compatible control bridge; record exact versions and setup commands.
- [ ] Demonstrate independent movement, yaw/pitch, fire, reload, equip and use for one bot without conflicting native AI.
- [ ] Declare any temporary aim/navigation assistance and keep assisted results separate.
- [ ] Verify input hold/release, application ticks, missed-deadline fallback and input clearing on death/reset.
- [ ] Implement player-specific visibility and memory; test hidden-enemy, smoke and flash cases, and declare sound support.
- [ ] Verify constructed resets by reading back player/equipment/bomb state; clear old inputs, messages and episode memory.
- [ ] Measure action cadence, latency, reset reliability and valid transitions per wall-clock second.

**Exit check:** a reproducible demonstration of one player moving, aiming, firing and using an objective, with observation checks and repeated reset results. Decide backend feasibility from that evidence.

## P1 — define the learning environment

- [ ] Specify typed player observations, action bounds, simultaneous-input rules and action masks.
- [ ] Add reset/step contracts with elapsed ticks, requested/applied actions and explicit failures.
- [ ] Keep actor observations separate from privileged replay/debug state; add information-leakage tests.
- [ ] Keep ten roster slots and define inactive/dead-player behavior through the eventual team outcome.
- [ ] Implement authoritative terminal team reward and distinguish termination, truncation and invalid rollouts.
- [ ] Build small navigation/aim/objective checks, followed by short post-plant and retake scenario families.
- [ ] Add frozen teammate/opponent baselines and a reproducible held-out evaluation suite.
- [ ] Log scenario, build, map, controller, action, observation and reset provenance.

**Exit check:** baseline rollouts complete valid episodes, save transitions and produce a repeatable evaluation report without hidden information reaching the actor.

## P2 — collect usable data and train a first player

- [ ] Audit ESTA fields against the player action schema; document missing mouse/button labels and sampling limits.
- [ ] Keep historical CS:GO samples distinct from newly collected CS2 trajectories.
- [ ] Collect synchronized legal observations and actual player inputs if mechanical imitation is pursued.
- [ ] Freeze source-match/event and scenario-family splits before fitting any model.
- [ ] Choose a small policy and algorithm based on measured throughput and action-space support.
- [ ] Compare a simple baseline, optional behavior cloning and the first outcome-based RL run.
- [ ] Save checkpoints, configuration, seeds, training curves and held-out evaluation results.
- [ ] Compare win rate with uncertainty; report invalid runs, execution failures and per-scenario results.

**Exit check:** the learned player improves on a declared baseline on held-out scenarios under the same control and information limits.

## P3 — selectable roles, including IGL

- [ ] Add an explicit role setting to episode configuration and the viewer; begin with `player` and `igl`.
- [ ] Condition the player policy on role while retaining control of its own slot only.
- [ ] Define a bounded IGL call vocabulary, message timing and teammate response model.
- [ ] Implement and record communication through the declared information channel.
- [ ] Train role-conditioned behavior with a stated teammate/opponent distribution.
- [ ] Compare role conditioning alone, communication enabled and communication disabled.
- [ ] Verify that choosing IGL changes useful behavior and team outcomes, not just a label.

**Exit check:** selectable IGL remains an ordinary playing agent with tested communication behavior and no direct ownership of teammates' controls.

## P4 — expand after the first result

- [ ] Broaden starting positions, equipment, living-player counts and opponent styles toward 5v5 rounds.
- [ ] Add validated utility execution and perception coverage before evaluating utility tactics.
- [ ] Consider further roles, shared player-policy weights and frozen-opponent/self-play leagues.
- [ ] Add economy, buys and multi-round objectives only with a corresponding task and reward revision.
- [ ] Assess additional maps and current-build generalization using separate evaluation sets.

## Publication and reproducibility

- [ ] Reproduce setup and verification from a clean checkout on another machine.
- [ ] Add CI for checks that do not require downloaded game assets or a running server.
- [ ] Decide the project's own source license before making an open-source release; retain third-party attribution.
- [ ] Publish benchmark configuration and reproducible results when a trained agent exists.

Start with **P0**. Role selection and model training depend on a working player control bridge.
