# DECOY runtime foundation audit

Audited and exercised on Windows with Python 3.12. The backend is the actual
[DECOY repository](https://github.com/HATS-ICT/decoy) pinned to
`6f93b8efe5a778384ccd284c31b2141b6b0ce5da`, its public Dust II FBX, Bullet
collision/character simulation, effective waypoint graph, and unchanged public
damage-prediction checkpoints. No model training was performed.

## Reproduce

Use Python 3.12 to run `scripts/setup_decoy.py --install`. The script creates
`.venv-decoy`, installs the verified versions from `requirements-decoy.lock.txt`,
clones only when absent, checks the exact revision, downloads the map only when
absent, and validates immutable SHA-256 hashes for map, radar, waypoints, and both
checkpoints. It refuses changed assets or an existing checkout at another commit.
The separately downloaded FBX remains a local third-party asset.

PowerShell commands from the project directory:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv-decoy\Scripts\python.exe -m igl.decoy_runtime export-map --output data/assets/dust2_waypoints.json
.\.venv-decoy\Scripts\python.exe -m igl.decoy_runtime smoke --output data/simulations/smoke.json --seconds 120
.\.venv-decoy\Scripts\python.exe -m igl.decoy_runtime branch --scenario data/scenarios/pro_sample.json --output data/simulations/pro_branch.json --seconds 45 --max-snap-units 80
.\.venv-decoy\Scripts\python.exe -m pytest tests/test_decoy_runtime.py -q
```

Replay outputs use the same canonical `rounds[].frames[]` format as recorded
matches. `game: csgo` identifies the reference game; `source.kind: simulation`
and `source.engine: DECOY` identify the actual producer. Reports are adjacent
`*.report.json` files. Source/demo time is preserved separately from the new
simulation clock. Replays are privileged observer state, **not policy input**.

## What runs

- One commander can order the five T slots or five CT slots. `command(...,
  team="T")` rejects commands targeting CT agents. Each living slot accepts
  hold, route-to-waypoint/world-position, plant, or defuse.
  Hold/plant/defuse optionally accept finite `yaw` degrees, normalized to
  `[0,360)`, to control facing and FOV without advancing time or position.
  Repeating an ongoing plant/defuse preserves its progress, including when yaw
  changes. Hold/move interrupts and clears that progress.
- Paths follow the actual directed graph; all movement passes through upstream
  DECOY agent movement and Bullet physics. No map or movement substitute is used.
- Simulation advances synchronously at 60 Hz; `step(seconds)` is bounded.
  The round has an explicit timer and terminal result. Headless stepping does
not wait for wall-clock time or upstream asynchronous AEC decision queues.
- Damage/kill/bomb events accompany the replay. Damage includes predicted amount
  and actual health loss, apportioned proportionally across simultaneous
  contributors for reporting. Kill credit goes to the largest predicted
  contributor; external player ID breaks ties. Event attribution does not alter
  the physics or simultaneous damage calculation. Names and IDs are retained.
- `reset(seed=...)` seeds Python, NumPy and PyTorch and resets the clock and all
  commander state. Same-process, same-machine reproducibility is tested for
  both a complete 5v5 script and a professional-demo branch. Cross-platform
  bitwise physics determinism is not claimed.
- `team_observation(team)` exposes friends, visible enemies, and their last-seen
  positions. Approximate 100-degree horizontal FOV and Bullet occlusion gate
  enemy observations. Unseen enemy HP/equipment/orders and enemy bomb-carrier
  position are excluded. This does not yet model human callouts or sound.
- Restores preserve player identities, HP, teams, supported weapons, armor flag,
  helmet and kit, surviving roster, bomb state, and remaining timer. Coordinates
  use upstream `panda = hammer * 0.01905 + [0,0,3.1]` transformation.

## Verified assets and outputs

The effective graph includes upstream's additional nodes/connections and
removed connections, rather than only its input JSON: **6,638 nodes, 48,053
directed edges**. Strong connectivity and neighbor-table consistency pass.
The public FBX is **75,692,093 bytes**, SHA-256
`967f436a1f2768f9f07f37f530f1d84d5e5e56e4814864e135c7459cce774a48`.
All asset records are in `data/manifests/decoy_assets.json`.

`data/simulations/smoke.json` is a real headless 5v5 round with combat enabled.
`data/simulations/pro_branch.json` is a real branch from **G2 Esports vs ENCE,
IEM Fall 2021 Europe**, ESTA demo `0520c3de-fdfe-4387-8060-5916549ad991`, round 6,
frame 217, 109.496 seconds after freeze end. It starts with nexa and NiKo versus
dycha and Spinx after planting; all ten original slots remain represented.
The four living player snaps are 5.83–20.83 Hammer units. It runs without
`--allow-approximate` and with an 80-unit maximum live-player snap distance.
The complete source provenance and CC-BY-SA attribution are in the sample
scenario. The script is **omniscient routing for system validation**, not a
fair opponent and not evidence of strategic ability.

Tests exercise actual ten-agent initialization, graph integrity, navigation and
ownership, repeatable combat trajectories, bounded timeouts and reset clocks,
postplant survival after T elimination, 3.2-second planting, 5/10-second defusing,
state restore, input rejection, enemy-information masking, simultaneous damage
inputs, and a repeatable professional-demo branch. Consult current reports for
measured duration/outcome rather than treating one stochastic seed as a result.

## Upstream defects handled in the adapter

No tracked upstream source was modified. Fixes are explicit in
`src/igl/decoy_runtime.py`:

| Upstream behavior | Adapter behavior |
| --- | --- |
| Torch imported after Panda3D fails Windows DLL initialization | Import Torch first; single CPU thread |
| Relative model paths depend on current directory | Resolve asset paths; convert Panda paths correctly on Windows |
| Reset ignores seed and keeps an altered bomb clock | Seed all used generators and reset clock before engine reset |
| AEC observation says shape 3 but returns 28 at 5v5; stale reward/termination handling | Bypass AEC wrapper; expose validated canonical commander API |
| Stops can request decisions each tick; dead-agent queues can exhaust | Use fixed synchronous physics steps and explicit commander orders |
| Stuck bots teleport after 0.5 seconds | Disable teleport workaround; report agents stalled for over 2 seconds |
| Automatic instantaneous plant/defuse | Explicit stationary timed commands with kit-aware defusing |
| Eliminated T team wins CT immediately even with planted bomb | Planted bomb continues until defuse/explosion or CT elimination |
| Dropped bomb is never recovered | Living T can recover a nearby dropped bomb |
| Sequential model updates use already-damaged attacker HP | Snapshot boundary HP and apply all predicted damage simultaneously |
| Regressor could predict negative damage | Clamp negative damage to zero; reject nonfinite results |
| Engine does not provide a demo restore boundary | Validate canonical states, map weapons, report snaps, reject unsupported state |

## Limits and next fidelity gates

This is a functioning research foundation, **not a faithful CS2 simulator**.
The map is a decompiled CS:GO Dust II map with no precise version declared by
upstream. Dataset alignment checks elsewhere in this project quantify mismatch;
nearest-waypoint distance does not prove correct floor or unobstructed snapping.
Every restore reports displacement; large live-player snaps fail closed. Audit
routes and collision/visibility against source demos before drawing tactical
conclusions.

The existing damage model is used only for inference and has not been validated
for transfer. It runs every 0.5 seconds and abstracts aiming/shooting into learned
damage. Fixed 250-Hammer-unit/s movement, Boolean armor, and held view direction
are not full weapon/movement mechanics. No ammunition, reload, wall penetration,
sound, recoil, crouch, acceleration, economy, smoke, flash, HE, or fire simulation
is present. Bombsite boundaries and use radius are approximations. Timed bomb
logic is a tested wrapper approximation, not an engine reproduction.

Scenarios with unknown or active utility, blindness, active plant/defuse/reload,
airborne players, unknown live CT kits after planting, an unsupported live held
weapon, or a non-CS:GO source require explicit `--allow-approximate` and record
every assumption in output warnings/limitations. Missing/terminal bomb states
and excessive geometry mismatch always reject. Dead players' descriptive
equipment is preserved without affecting combat. Inventory utility remains
descriptive and cannot be commanded. Velocity and animation progress are not
restored. Demo clock precision is inherited from the source.

Before RL: validate travel and visibility on representative routes, inspect
collision edge cases, define the desired combat model, implement and validate
needed utility, define information rules, and add a non-omniscient opponent.
There is intentionally no training loop, reward design, learned commander, or
claim of complete PettingZoo/Gym compatibility in this foundation.
