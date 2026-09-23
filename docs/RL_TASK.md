# RL task proposal: a Counter-Strike player

Date: 2026-09-23. Status: proposed direction following the user's pivot; no player policy, training loop, or original-CS2 bridge is implemented.

The new objective is to train an agent that **plays as one player**. IGL can be a selectable role for that player. The former design, where one policy directly commanded five fixed executors, is [archived](IGL_TASK_ARCHIVE.md). The implementation sequence is in [TODO.md](../TODO.md).

## Control boundary

Start with one learning player in a team, with teammates and opponents controlled by frozen, versioned baselines. Keep ten roster slots, including dead players. Small scenarios provide a curriculum toward 5v5 play; learning all ten players at once is deferred.

```text
player's observations + memory + selected role
    -> player policy
    -> own movement, view and button inputs
    -> game engine
    -> next observation and team outcome
```

The policy should eventually learn positioning and mechanical execution: moving, aiming, firing, reloading, equipping, using utility, planting and defusing. Begin with a restricted, measured input set. Any scripted aiming or navigation used for debugging must be declared as assistance and evaluated separately from learned execution.

Original CS2 remains the backend to investigate for this goal. The existing DECOY adapter is useful for replay, scenario and navigation experiments, but its outcome-based combat and missing weapon/utility mechanics cannot establish that a policy has learned to aim or play CS2. The [backend feasibility proposal](ORIGINAL_GAME_BACKEND.md) predates this pivot; its commander-specific design needs revision before implementation.

## Selectable roles

Proposed first role configuration: `player` and, later, `igl`. Additional specializations such as entry, support, lurker or AWPer are optional future experiments. These are task conditions, not implemented UI choices or evidence of different learned behavior.

Every role controls only its own player. Selecting IGL may later enable a bounded communication channel, for example a suggested site, regroup point or execute time. It does not grant direct teammate input control or additional hidden information. Teammates need an explicit, versioned model of whether and how they respond. A role token alone does not create leadership ability.

Start without learned communication. Once individual play works, compare the same player policy with and without role conditioning and with and without the communication channel. Assess both personal execution and team results before claiming the IGL option is useful.

## Observations and information

First proposal: structured observations rather than raw pixels, with missing values and observation ages. The choice remains open until the bridge demonstrates what it can reliably expose.

| Group | Permitted information |
|---|---|
| Self | Own pose/view, velocity, health, armor, equipped weapon, ammo, inventory and action state |
| Context | Side, selected role, round phase, known objective state and relevant map information |
| Perception | Enemies and effects currently sensed by this player; last-seen memory with age |
| Team reports | Explicit teammate messages and any declared shared-status abstraction |
| Control | Own supported actions, acknowledgements, elapsed ticks and failures |

Keep full engine state in a separate recorder/evaluator channel. Hidden enemy positions, inventory and future replay events must never enter actor input, action masks or recurrent memory. The existing team observation method is not automatically a suitable individual observation method.

Verify visibility, smoke, blindness and sound independently. Sharing exact friendly positions or instant sightings is an explicit abstraction; define it before training. At reset, clear memory unless a verified causal observation preamble is supplied. Source-demo omniscience and display interpolation are not player perception.

## Actions and timing

Prototype actions for a single owned slot:

- Bounded forward/side movement and supported movement buttons.
- Bounded yaw/pitch changes.
- Attack, reload, use, weapon selection and supported utility inputs.
- A neutral input with documented persistence and release semantics.

Do not adopt the previous 0.5-second commander cadence for aiming without measurement. Benchmark a fixed tick-indexed action interval, inference latency and input application, then choose the cadence. Record requested and applied actions separately. Native AI must not fight the policy's inputs; partial native assistance must be explicitly named.

Define simultaneous-input rules, hold/release behavior, illegal-action handling, stale-input expiry and the missed-deadline fallback. Clear held buttons on death, disconnect and reset. Releasing a grenade must execute through game inputs; selecting a distant effect location is not a throw.

## Episodes and rewards

First prove reset and controls in small constructed scenarios: navigation, aiming/firing and objective interaction. These are capability checks, not full-match skill claims. Then return to short post-plant/retake tasks, using one controlled player with fixed teammates and opponents. Expand to broader rounds after these work; economy and match-level saving remain later tasks.

For the first outcome-learning experiment, propose terminal team reward `+1` for a win, `-1` for a loss, and `0` otherwise, awarded once. Use undiscounted returns for finite bounded episodes to target round win probability. Any auxiliary skill reward or later shaping must be a separately named experiment with evaluation on the unshaped task.

Death ends the player's ability to act, but does not necessarily end the team episode. Continue to the authoritative round outcome and attribute it to the collected trajectory. A planted bomb may remain decisive after all attackers die. Infrastructure faults invalidate a rollout; they are not losses or draws. Distinguish game termination from collection truncation and retain the appropriate final observation.

Reset must clear inputs, communication and recurrent state, identify the episode, and read back the requested game state. Start with supported constructed states. Historical CS:GO demos can inspire scenarios but are not complete CS2 checkpoints.

## Data and learning sequence

1. Prove one-player control and player-specific sensing in the selected backend.
2. Build an environment contract and frozen baselines; measure valid transitions per wall-clock second.
3. Collect synchronized observations and actually applied inputs for the supported action set.
4. If labels are sufficient, compare behavior cloning with a simple baseline before adding RL.
5. Train a small recurrent player policy on easy scenarios, then broaden the scenario distribution.
6. Add selectable roles and evaluate the IGL communication extension independently.
7. Consider shared policies across multiple player slots, self-play and full-match economy later.

The current ESTA corpus contains historical CS:GO state/event samples at roughly 2 Hz. It is useful for scenario distributions and some positioning analysis; it does not provide dense mouse/button ground truth for the proposed player actions. Do not infer precise mechanical labels from interpolated frames. Audit label coverage and collect suitable input traces before claiming mechanical imitation learning is possible.

Choose the first RL algorithm only after measuring observation/action spaces and throughput. Keep source matches/events and scenario families disjoint across training, validation and test. Preserve existing corpus manifests and avoid mixing their independent split assignments.

## Evaluation and acceptance

Primary task metric: held-out team round win rate against frozen opponents with the same teammate setup and input capabilities. Report trial counts and uncertainty, including results per side, scenario family and selected role. Native bots require characterization; they are not automatically fair or professional-strength opponents.

Diagnostic metrics: navigation completion, aim error, valid shots, damage, trades, objective interactions, utility execution, communication effects, latency, reset success and invalid-rollout rate. These are not automatically rewards. Compare against baseline controls and, later, run role/communication ablations.

Log build/map/scenario/controller identifiers, exact actor observations, selected role, requested/applied inputs with ticks, reward, elapsed game time, termination/truncation, and rollout validity. Keep privileged replay data distinct from actor data.

The first milestone is complete when one player can move, aim, fire and interact with an objective through measured inputs, receive a checked individual observation, and survive repeated verified resets. No training run or claimed IGL behavior should substitute for this bridge demonstration.
