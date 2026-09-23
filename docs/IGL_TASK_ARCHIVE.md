# Archived RL task definition: tactical IGL

Superseded on 2026-09-23 by the [player-agent task](RL_TASK.md). This document preserves the earlier commander design and its historical decisions; it is not the active roadmap.

Date: 2026-09-18. Status: design draft, no training or original-CS2 integration implemented.

**Confirmed by the user:** begin with mid/late-round tactics, starting with post-plant and retake scenarios.

**Proposed, not yet accepted or demonstrated:** one learned IGL controls five fixed skill executors. The user has asked how those executors would work with default CS2 bots. Their implementation and the exact supported action set remain feasibility decisions. This draft defines the learning problem conditional on obtaining reliable execution; it does not assume default bots already accept tactical orders.

## 1. Research question and objective

Can a policy improve round outcomes by coordinating the positions, viewing directions, utility and timing of five players, under a declared information model and fixed execution ability?

The eventual environment is original CS2, on one pinned map/build, with a 2D observer/control interface. Start with Dust II for continuity unless the map decision is revised. Begin with a small CT-retake scenario family; extend to T post-plant defense and broader mid-round decisions. Maintain five slots per team, including dead players. Two-versus-two or three-versus-three debugging scenarios are curriculum subsets, not replacements for the five-versus-five goal.

Version 0 excludes economy, saving for future rounds, purchases and match-level strategy. A one-round outcome objective cannot teach the real economic value of saving. Those require a later multi-round task or a separately justified continuation-value model.

## 2. What “fixed bot controller” means

It is a program that executes an instruction using current observations. Its rules and parameters stay constant while the IGL learns. Its actions can react to the game; they need not follow an unchanging recorded path.

```text
IGL policy: chooses player, destination/sector/skill and timing
    -> executor: follows route, aligns aim, performs inputs, reports progress
    -> CS2: resolves movement, collisions, weapons, utility and round outcome
```

Examples of the code we would need:

| Order | Executor responsibilities | Decisions retained by IGL |
|---|---|---|
| Move to anchor | Follow a valid route, steer with game inputs, handle ordinary obstruction, use declared combat reaction | Destination, route choice where offered, movement mode and start time |
| Hold sector | Face the chosen sector, react to permitted sightings, aim/fire under the fixed execution profile | Which player holds which position/angle, and for how long |
| Execute utility recipe | Reach its launch envelope, equip, align, perform release inputs, recover or report failure | Which recipe, who throws, when, and teammate coordination |
| Defuse | Reach the known bomb, satisfy use conditions, hold use, report progress/interruption | Who defuses, who covers, when to start or cancel |

Do not hardcode a complete “win the retake” routine as one action: that would hide the tactical problem inside the controller. Conversely, learning individual mouse deltas from scratch would expand the project into learning mechanical execution as well as IGL decisions.

### What default CS2 bots provide

Native bots have their own autonomous behavior; the reviewed tools do not establish a complete public `move_to / hold / throw_lineup` task interface. CS2-Bot-Controller v0.6.3 exposes input overrides, locks and weapon selection. CounterStrikeSharp exposes bot state. These are lower-level integration tools, not proof of high-level order execution. [Bot-controller API](https://github.com/XBribo/CS2-Bot-Controller/blob/v0.6.3/csharp/BotControllerApi/IBotControllerApi.cs), [CounterStrikeSharp bot reference](https://docs.cssharp.dev/api/CounterStrikeSharp.API.Core.CCSBot.html)

Three possible execution implementations must be distinguished:

1. **Native task integration:** reuse native navigation/combat while directing specific goals. Desirable if reliable, but a suitable task API has not been verified.
2. **Custom fixed executor:** take ownership of bot inputs and implement a restricted route/aim/utility/combat controller. This is the controllable fallback, and meaningful engineering work. Suppressing native AI also removes behaviors we might otherwise have hoped to reuse.
3. **Learned executor:** train a player policy that converts an order and local observations into movement/aim/button inputs. This is an additional RL problem, not a shortcut that removes the need for an input bridge.

Selective native-AI overrides are an experiment, not an assumed capability. Switching off autonomous movement while retaining trustworthy native aim/combat needs verification. A field named `AimGoal` does not prove a stable command API. Live aim control itself remains a bridge feasibility check.

If we build the custom executor, begin with one short route, one stationary angle and one utility recipe. Use the same frozen execution version when comparing IGL policies. Per-player controller parameters may include declared reaction delay, turn rate and aim error; initially keep them constant across comparable runs. Exact human-equivalent mechanics are not claimed.

## 3. Formal learning setup

Let `x_t` be complete engine state, `o_t` the legal team observation, `h_t` the policy's observation/action history or recurrent memory, and `a_t` the joint order for the five friendly slots.

```text
a_t ~ policy(o_t, h_t)
next world state = CS2 + fixed friendly executors + sampled frozen opponent
objective J(policy) = expected terminal team score over the declared scenario/opponent distribution
```

With one learned commander and fixed opponents/executors, this is a partially observed single-agent control problem over a multi-player game. It does not require five independently learned policies or a multi-agent algorithm merely because five characters are controlled.

The policy needs memory for sightings, earlier orders and utility timing. A recurrent model is a reasonable initial choice; recurrence does not establish that our observation approximation equals human perception.

## 4. Observations

Return typed values, missingness and age rather than a screenshot for the first task:

| Group | Proposed contents |
|---|---|
| Timing/context | Team/role, game time, known objective time, phase, observation age, relevant static map/anchor data |
| Five friendly slots | Alive, position, view, velocity, HP/armor, weapon/ammo, utility, kit, current order and execution stage |
| Enemy reports | Currently permitted sightings and last-seen locations, age and reporting teammate; identity only if legitimately available |
| Objective | Known bomb state/site/location and time with source/uncertainty; defuse state only when legitimately known |
| Utility/sound | Friendly reports and effects/cues sensed under the declared perception model |
| Control | Supported/available actions, pending orders, application acknowledgements and failures |

Initial communication assumption: immediate sharing of friendly status and legitimate sightings. Exact friendly position/velocity and perfect communication are explicit abstractions, stronger than ordinary human callouts. The IGL's team knowledge must not give a blinded individual shooter perfect current target tracking.

Never expose hidden enemy HP, inventory, current coordinates, unpublished effect outcomes or private controller state. Privileged engine data remains in a separate recorder/evaluator channel. Action masks must not reveal whether an unseen opponent is in a flash radius or occupies a destination.

Visibility through smoke, blindness and sound remain sensing-integration requirements. A geometric ray or full server entity list does not solve them. Use verified game sensing where possible; label any approximate observation model and limit the task accordingly. If hearing is omitted in an early test, name that variant explicitly.

Update sensing on game ticks; observation queries are read-only. At a reconstructed mid-round reset, start with empty enemy memory and `history_available=false` unless a verified causal observation preamble is available. Do not reconstruct knowledge from omniscient replay history or carry recurrent memory between episodes.

## 5. Actions and timing

Proposed first IGL cadence: every **0.5 game seconds**, subject to bridge timing measurements. The five ongoing skills execute concurrently; the world and opponents continue during inference.

For each player, choose one candidate command:

| Command | Parameters | Semantics |
|---|---|---|
| `continue` | None | Preserve current skill/progress; also the only action for a dead slot |
| `hold` | Facing sector | Remain at current position and watch the chosen direction |
| `move` | Destination anchor, optional route/movement mode | Execute navigation; combat reaction follows the declared controller profile |
| `utility` | Validated skill ID, optional short release delay | Travel/prepare/throw through actual inputs; report failure if conditions cannot be met |
| `defuse` | Known bomb target | Navigate/use according to the supported skill; only available to eligible CTs |
| `cancel` | None | End an interruptible current order and enter a declared hold state |

Start with a small curated set of map anchors, facing sectors and utility recipes. Exact catalog sizes follow control testing. A factorized or autoregressive action representation can avoid enumerating every combination of five orders. Adding synchronization groups/deadlines is a later extension if the first action set cannot express the target coordination.

A recipe with travel can be selected away from its launch position. Only its physical release is constrained to the launch envelope. It must never teleport the player or place an effect at the target. A grenade already released remains in the world after cancellation or death.

Repeated orders must be idempotent; `continue` must not restart a defuse or throw. Define interruptible phases and weapon occupancy. A cancelled skill does not refund a released grenade. Reject stale-invalid orders with explicit acknowledgement and the documented fallback; do not silently turn them into another command.

Record observation, submission, acceptance and application ticks. If inference misses its deadline, continue the existing bounded skill under the declared fallback. A Python `step()` call does not imply that CS2 pauses. Pending order state and elapsed engine time belong in the transition record.

Fixed-rate decisions simplify the first interface even though individual skills have different durations. If later switching to event-driven decisions, returns/discounts must account for actual elapsed time; per-decision discounting must not accidentally reward a policy for generating extra decision events.

## 6. Reward

Version 0 reward is deliberately direct:

```text
+1  the controlled team wins the round
-1  the controlled team loses the round
 0  otherwise
```

Award the outcome exactly once, from the authoritative game event. A genuine draw, if supported by the chosen mode, is explicitly scored zero; infrastructure failures are not draws.

Use `gamma = 1` for these finite, bounded episodes. With wins/losses only, expected return equals `2 * win_probability - 1`, so maximizing it maximizes round-win probability. The game objective timer already creates urgency. Adding a time penalty or discount would introduce an additional preference for when wins/losses happen.

Do not initially reward kills, damage, smoke count, flash duration, moving toward the bomb, staying alive or starting a defuse. Those can conflict with winning: chasing kills may abandon the objective, repeated flashes may be wasted, and a useful sacrifice may lose personal HP. Record them as diagnostics.

If sparse feedback proves insufficient, first use easier scenarios, scripted baselines and vetted imitation examples. Any later reward shaping is a separately versioned experiment evaluated against the same unshaped outcome metric. Do not expose hidden-state shaping to a recurrent actor as a covert enemy-information channel. There is no shaped reward formula implemented in this draft.

## 7. Episodes, reset and termination

An episode starts from a verified constructed post-plant scenario and ends at the real game's round result. Prerequisite: the bridge can create and read back bomb location/timer/state. If that fails, use pre-plant control demonstrations to repair the bridge; do not label them completed retake training.

Vary supported starting regions, living players, equipment, bomb position/time and defender setups. Use the actual remaining objective time rather than cutting every episode at an arbitrary 30 seconds. Operational watchdogs must allow the game to reach its result.

| Event | Learning treatment |
|---|---|
| Authoritative round win/loss | True termination and terminal reward |
| All T players die while bomb remains planted | Follow engine outcome; this alone does not end the task |
| Skill completes/fails or grenade is exhausted | Ordinary nonterminal transition |
| Rollout batching boundary | Collection boundary; preserve environment and recurrent state appropriately |
| External time cap with valid final state | Truncation, handled separately from game termination |
| Server crash, corrupt telemetry, unverifiable reset | Invalid rollout; no fabricated win/loss or bootstrap state |

This follows the distinction between task termination and administrative truncation. [Gymnasium time-limit guidance](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/)

Reset must read back actual engine state and verify requested fields, clear old commands/entities and isolate episode identity. Start without active utility, airborne players or in-progress actions. A sampled pro demo is not a complete engine checkpoint. Source frames can inspire a constructed scenario without making its continuation an exact replay branch.

## 8. Opponents, data and learning sequence

Initially train against a fixed pool of defender setups/controllers with a declared sampling distribution. Use several behaviors so a policy cannot win solely by exploiting one stationary arrangement. Freeze opponent and execution versions for evaluation. Native bots may be a useful baseline but need separate behavior/perception characterization; they are not automatically a fair professional-strength opponent.

Suggested sequence, after the environment works:

1. Scripted IGL baselines exercise move/hold/utility/defuse and demonstrate that coordination changes outcomes.
2. Short, simple retake scenarios test whether outcome learning beats those baselines under fixed execution.
3. Increase scenario variety and living-player counts toward five-versus-five.
4. Add T defense and broader mid-round tasks with distinct evaluation suites.
5. Consider frozen-opponent leagues/self-play and, separately, learned player execution.

Recurrent PPO is a candidate first algorithm once throughput and action masks are known, not a requirement of the task definition. Simultaneously training the IGL and five execution policies changes both the learning problem and how improvements can be attributed. If later pursued, use a separate specification for shared player-policy parameters, local observations, team orders and credit assignment.

Pro demos supply tactical examples, scenario distributions and outcomes, not direct IGL orders or rewards for unchosen actions. Any inferred action labels need confidence/provenance. Split by source match/event and scenario family before fitting. Keep historical CS:GO data separate from current CS2 data; neither future demo frames nor viewer interpolation enter policy input.

## 9. Evaluation and logging

Primary metric: round win rate on a fixed held-out distribution, with uncertainty and comparison against a scripted IGL using identical execution capability. Report per-side/site/difficulty results as well as the aggregate. Hold out scenario families and opponent variants; random frames from one round are not independent train/test examples.

Secondary diagnostics: utility execution success, flash/smoke timing, teammate synchronization, trades, friendly damage, deaths, defuse attempts, order churn, rejected/stale commands, latency, resets and invalid-rollout rate. These diagnose behavior; they are not automatically reward terms.

Pair scenario conditions across policies when feasible, but do not assume the real CS2 server offers reproducible RNG seeds. Repeated trials and uncertainty remain necessary. Publish failures rather than dropping all hard scenarios silently.

Keep separate logs for:

- Privileged replay and outcome events.
- Exact observation, mask and recurrent reset boundary presented to the actor.
- Requested/applied actions and their ticks, controller versions, skill progress and failures.
- Reward, termination/truncation, rollout validity and failure reason.
- Scenario/source/build/map/controller/opponent identifiers and reset verification.

A simple transition contract is `(observation, requested_action, action_acknowledgements, reward, next_observation, elapsed_game_time, terminated, truncated, validity, provenance)`. Never train as if an unexecuted command had been applied successfully.

## 10. Decisions before implementation

The user has selected the tactical scope. The next decision is the execution boundary, after a concrete demonstration of one commanded bot. We should not finalize a large action catalog or start training until we can show:

1. One bot moves, aims and holds according to our order without competing native AI.
2. It executes one real utility recipe and reports state/failure accurately.
3. Its firing/visibility behavior follows the declared information and execution model.
4. The same controls work independently for five bots and survive resets.

The observation/reward/episode design above can be reviewed now. The proposed macro-action learning setup remains conditional on those capabilities and the user's choice of what should learn.
