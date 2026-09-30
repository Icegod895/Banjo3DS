# M4.8B.9 — bounded current-player floor cadence

`floor_bridge.c/.h` are host-testable production modules, NOT connected to the
viewer or player runtime. Floor/segment/camera mathematics and movement remain
unchanged. This contract describes a **Banjo3DS port approximation** of upstream
candidate production, with exact original floor evaluation on supplied candidates.
It does not implement Rare's collision solver.

## Side-by-side update audit

| Stage | Original NTSC v1.0 | Current Banjo3DS |
|---|---|---|
| Input and physics | `bsmethods.c:282–296`: stick/state, baphysics, position offset, collision | `player_runtime.c:5–37`: stick/gait intent, jump/horizontal step |
| Initial candidate | Physics position and previous position in `code_C4B0.c:295–336` | Ground: X/Z proposal, previous actor Y; air: integrated XYZ before sweep (`jump.c:66–93`) |
| Before floor callback | Long-displacement volume sweep may change candidate (`code_C4B0.c:143–165`) | No corresponding wall/volume correction |
| Floor callback | `func_8029350C`, `code_C4B0.c:85,167`: set candidate/mask and update persistent floor | Proposed bridge observes pre-`movementFollowFloor` or pre-`banjo_jump_sweep` candidate |
| Floor correction | Ground/slope snap after floor callback (`code_C4B0.c:93–113`) | Ground-follow accepts/rejects entire move; air sweep chooses earliest contact |
| Further correction | Sphere/wall response; next iteration inherits corrections; up to five calls (`code_C4B0.c:116–239`) | No such iteration. Internal 14-unit floor-follow samples are NOT Rare candidates |
| Final position | Solver result; exhaustion can restore a different position (`code_C4B0.c:241–249`), further mode logic possible | Accepted/rejected actor, or swept contact; optional diagnostic void recovery |

The current pre-collision proposal matches the *location in the pipeline* of
Rare's initial physics candidate. It equals Rare's first **floor** input only
when upstream physics proposals agree and Rare's preceding volume sweep does not
change it. Those conditions are not assumed globally. Grounded Banjo3DS keeps
prior Y during horizontal proposal; original vertical/collision state can differ.

An accepted ground-follow Y is already a result of our floor solver. It is not
an original pre-floor candidate. Likewise, swept landing/contact may change X/Z
as well as Y and is not a second original iteration. A rejected/final position
may be somewhere else entirely. Neither is submitted as an ordinary second call.

## Chosen API and callback counts

```
bq_bridge_init(initial_parity)       new player lifetime, full floor init
bq_bridge_begin()                    start one simulation frame
bq_bridge_candidate(XYZ, ordinal)    genuine proposal, ordinal starts at zero
[explicit relocation event only:
 bq_bridge_reinit()
 bq_bridge_candidate(destination, next_ordinal)]
bq_bridge_end()                      advance frame/parity exactly once
```

The bridge passes fixed ordinary Spiral Mountain parameters upper=56 and
filter=0x400000. Other marker masks/player forms are outside this bounded contract.
No dt, grounded bit, animation state, velocity or normal is invented as an input
to the floor provider. The ordinal is scheduler validation, not floor mathematics.

| Current runtime path | Ordinary floor calls |
|---|---:|
| Stationary or moving grounded update, dt>0 | 1, pre-floor proposal |
| Rejected ground move | 1 at attempted proposal, NOT accepted position |
| Y-orbit grounded | 1; intent is zero, existing velocity still evolves |
| Jump takeoff / ascent / apex / descent | 1 integrated pre-sweep proposal |
| Landing | 1 pre-sweep proposal; no contact/final replay |
| Y-orbit airborne | 1; gravity/momentum continue normally |
| Zero dt / rejected invalid update, no proposal emitted | 0 |
| Diagnostic void recovery | 1 pre-recovery proposal + 1 explicit relocated destination |

A future connection must capture at these points; deriving the pre-sweep Y from
final vy is not safe because landing resets vy. No production hook is inserted
into `jump.c` or `player_runtime.c` in this task. Test observers are compiled from
temporary source copies and only write diagnostic values/counts.

Duplicate/missing ordinals, nested begin, end without begin and invalid query
inputs fail without advancing the candidate counter. Query errors must be
propagated as unsupported, never replaced with movement-floor/final-position
queries. No floor value is publishable before the first successful callback;
constructor -9000 alone is not a completed query. The zero-dt-at-start test checks
state/parity but deliberately does not feed an uninitialized floor to the camera.

## Parity and lifecycle

- Frame starts at zero, with explicitly supplied parity seed 0 or1.
- All candidates use `(frame + initial_parity) & 1`.
- Only successful `end` advances the frame; candidate/reinit never do.
- Empty frames advance once too. A paused simulation with no frame does not.
- This is an explicit simulation-frame clock, not VI count, elapsed milliseconds,
  callback count, dt accumulator, or a claim to recover the original global timer.
- New player/session allocation: full reset, matching original allocation in
  `code_C4B0.c:263` / `code_94A20.c:25`. Seed can align an existing game-frame clock.
- Walk, rejection, Y-orbit, jump and landing preserve floor history.
- Explicit reinitialization: ONLY mode=1/countdown=5, like
  `code_C4B0.c:518` -> `func_8031BA7C`; retains previous position/heights/records.
- Diagnostic void recovery: **port policy**, not Rare respawn. The already tested
  runtime validates/teleports to lastSafeGroundPosition. We preserve history,
  issue reinit, then supply that genuine relocation destination at the next
  ordinal in the same frame. This avoids exposing a pre-teleport void result as
  the destination floor without fabricating ordinary collision iterations.
- Original teleport `code_7060.c:819` re-enters collision at the new position.
  That supports distinguishing relocation from normal completion, but does NOT
  prove Rare uses our diagnostic void lifecycle or the same reinit combination.

The production bridge supports multiple **genuine supplied** candidates with one
parity; the current runtime normally supplies just one. Tests exercise multiple
callbacks in special state4 where parity changes real query behavior. It never
manufactures repeats to approximate Rare's 1–5 iterations/countdown consumption.

## Independent proof and actual trajectories

The scheduling reference uses a Python frame/event schedule and the independently
compiled ORIGINAL floor routines. Production uses the C bridge and the unchanged
production floor/segment modules. Full120-byte states are compared after events
and candidate calls, bit-exact at -O0/-O2. Frame, ordinal and parity are separately
asserted. The fixture hashes original snapshots, not future production expectations.

15 real-map schedules: 3,960 frames / 3,881 callbacks, including acceleration to
500, slopes both ways, rejection/edge/no-hit, stationary, jump/apex/landing,
Y-orbit ground/air, explicit reinit, zero-dt frames, and diagnostic void recovery.
Void recovery has an explicitly marked injected out-of-world actor state; the
actual runtime's recovery and real map revalidation are then exercised. It is not
represented as a naturally occurring Rare route.

Camera tests feed both suppliers into unchanged M4.8B mathematics:
- six existing B.8 240-frame trajectories, same byte-exact camera/floor hashes;
- a 600-frame full-input northward route then reversal, with actual ground motion,
  no teleport: `(0x11,32) -> (0x11,-1) -> (0xB,-1) -> (0x11,32)`;
- additional rejection, slopes, Y-orbit, reinit and recovery probes.
Total camera checks: 3,720 updates, all finite, no unsupported trigger in this
corpus. The required seven acceptance trajectories account for2,040 updates.
Stable zone input is the existing current-runtime grounded bit, explicitly a
bounded port mapping, not a reconstruction of every Rare player_isStable state.

## Quantified differences — what the numbers do and do NOT mean

**Original floor on identical supplied candidate/event schedules:** no differing
state or height, maximum divergence0, at both optimization levels. This proves
the bridge does not alter the original floor contract.

**Actual complete Rare solver on these gameplay routes:** NOT reconstructed.
First divergence and maximum divergence against that solver are **unknown**.
No result below is mislabeled as that comparison. Dynamic providers, volume/wall
correction, different candidate Y and extra iterations could change the stream.

To measure the cadence choice, a second ORIGINAL floor object is instead fed
final accepted XYZ once per update (the rejected design). It receives the same
parity/lifecycle events. Both resulting floor streams are supplied to identical
camera mathematics, each with terrain queried at its own evolving camera position.
Indices below are zero-based, distances are world units; XYZ maximum is largest
absolute component difference, not Euclidean distance.

| Trajectory | First floor difference | Max floor difference | Max Fbase-Y difference | Max camera-XYZ difference |
|---|---:|---:|---:|---:|
| Node stationary/walk/jump-rest | none | 0 | 0 | 0 |
| Node exit jump/landing | 156 | 19.440613 | 19.440613 | 0 (focus differs) |
| Free walk | 2 | 10625.777832 | 130 | 130 |
| Free jump/landing | 3 | 0.000122071 | 0.000122071 | 0.000122071 |
| Rejected ground | 54 | 332 | 130 | 0 (node focus differs) |
| Slope down | 1 | 55.224148 | 55.224148 | 36.584076 |
| Slope up | 1 | 24.123001 | 24.123016 | 24.121216 |
| Full-speed roundtrip | 54 | 332 | 130 | 0.000244141 |
| Y-orbit/reinit/void recovery cases | none | 0 | 0 | 0 |

The large free-walk value is **no-hit sentinel arithmetic**, not a10km physical
height error: frame88 proposal `(125.435844,1625.777832,-1000)` has no ordinary
floor (-9000); movement rejects it and retains `(123.908066,1625.777832,-1000)`.
Final replay therefore finds1625.777832. Frame2's first difference is merely a
one-float-step Y difference after accepted floor reconstruction. These are
separate causes; do not attribute the large difference to float noise.

At rejected-ground frame54, proposal Z400.872559 samples floor1468 while accepted
Z392.540985 remains on1800. A replay would hide the attempted-candidate floor.
At landing, the sweep's contact can differ from the end proposal. Slope results
also depend on the accepted Y used by the next update and retained floor history.
All first/max contexts and complete hash summaries are frozen in
`tests/fixtures/floor_bridge_golden.json`.

The unchanged camera's130-unit Fbase rule bounds the **observed** downward
sentinel effect to130 here. This is not a universal bound for arbitrary stacked
surfaces/candidate corrections. No new clamp/filter/double-query is introduced.
Free-walk maximum one-frame camera position component step is4.453369 units;
node-exit and roundtrip maxima are26.712708 and18.969879 (including startup).
The acceptance gate means deterministic, finite, source-matching camera evolution
on the specified scope, not hardware-tested aesthetics or complete Rare accuracy.
The known focus differences must remain visible in the M4.8C acceptance report.

## Classification and next boundary

- **Exact:** floor math, same-input states, retained reinit history, parity shared
  by callbacks, ordinal validation; no mutation of query/packet/camera primitives.
- **Equivalent for tested supplied static-map trajectories:** production bridge
  and original floor results, all six prior camera hashes and the roundtrip chain.
- **Bounded port approximation:** initial pre-collision proposal delivery, one
  ordinary callback, simulation clock, current grounded stable input, void policy.
- **Unsupported:** full original solver candidate stream; actors/dynamic providers;
  wall/volume collisions, non-default player marker modes, other camera triggers.

The gate permits bounded M4.8C integration using precisely this contract, followed
by visual acceptance. It does not permit claiming a port of Rare's whole solver,
replacing proposals with final coordinates, or silently adding corrective callbacks.

## Cost and scope

Bridge state132 bytes = existing floor120 + scheduling12. No packet changes,
heap allocation or extra collision representation. ARM-O2 object text428 bytes,
data/BSS0; candidate wrapper stack frame24 bytes above the existing floor/query
chain (not a measured hardware peak). Host -O0/-O2 and ARM -Wall -Wextra -Werror.
No viewer, movement, jump, gait, camera math, renderer, generated header, staging,
commit or push changes. `tools/n64splat` is untouched.
