# M4.9E.2A — one player frame, multiple genuine floor candidates

This is a host-only composition proof. `frame.c` is not in the viewer Makefile;
`player_runtime.c`, `player_ground.c`, `camera_runtime.c`, all existing providers,
E.1, E.2 and generated data are unchanged. No body collision is enabled in the
running viewer by this task.

## Exact boundary and order

Original `src/core2/bsmethods.c:282–296` performs state selection, physics and
position offset before `func_80293F0C`. `src/core2/code_C4B0.c:302–340` captures
previous/candidate positions and requested displacement once. Its normal body
loop (`:115–246`) performs `func_8029350C` at line 167 before each main body
check. Those are real, possibly different candidates, not repeated final actor
positions. The floor object is updated immediately by each invocation; its
history feeds the next. `code_94A20.c:257` reads global timer parity, not a floor
call count. The timer cannot advance inside this synchronous loop.

The current runtime has the required synchronous seam:

```
bridge_actor_tick: decision may become pending; applied coordinates unchanged
bq_bridge_begin: frame F, ordinal 0, parity P = (F + seed) & 1
playerRuntimeMoveStepped: existing input / gait / horizontal intent preparation
  PlayerMotionStep callback (currently playerGroundStep in the LIVE viewer)
    previous actor and previous floorheight -> ONE state update / FALL request
    ONE existing horizontal/vertical physics step -> ONE BgFrame XYZ candidate
    proposed host-only bp_frame_resolve:
      initial body sphere / optional raised-previous line
      1..5 iterations, same F/P/world:
        optional long line
        persistent working floor query -> unchanged temporary E.1 resolution
        main body moving sphere -> optional secondary queries / correction
      final position or saved fallback
      stuck-ground override -> negative vy=-1 if grounded -> stuck counter
      publish complete floor/body/ground result ONCE to owning runtime
      set floor ordinal to actual successful floor-query count (NO replay)
    final actor/velocity/contact publication
  existing accepted-displacement metrics, without overwriting physics velocity
optional existing diagnostic relocation lifecycle event (not a body iteration)
bq_bridge_end: advance frame ONCE
camera terrain / free-B contact (same applied bridge geometry)
bridge_mesh_tick: publish pending absolute mesh offsets
render reads the newly published bridge geometry
```

Source locations for the existing runtime are `player_runtime.c:6–52`,
`player_ground.c:31–100`, `camera_runtime.c:85–169`, and `main.c:789–821`.
The future body callback replaces the one-query motion phase; it must NOT invoke
that phase first, run `bp_resolve` afterward, or retain the old
`candidate_calls==1` floor-query assertion. One physics candidate and N floor
queries are different counters. `bp_frame_resolve` rejects a closed, wrong or
already-used frame. Clock begin/end remain the outer runtime's responsibility.

There is no new floor callback in `frame.c`: E.2 already calls the proven
provider for each genuine candidate. Its trace reports exactly those calls.
The ordinal assignment after success is accounting, not synthetic callbacks.
Independent link-time observers verify the actual supplier calls and parity.

### E.1 state and commit timing

The accepted E.2 implementation has a local working copy of the 120-byte floor
state. Every real floor call immediately updates that copy and the next call
reads it. On success it publishes that history to the runtime owner; on query
error it publishes nothing. This preserves the original observable ordering for
this static, non-reentrant call graph: no camera/player/actor observer runs
between body iterations. It does not claim dynamic provider callbacks could
observe the unchanged owner mid-loop. Dynamic providers are excluded.

The `BgState` used for each floor resolution has temporary vy=0, as already
proven in E.2. Position/ground flags and height are consumed, but the real
post-physics vy remains unchanged until body finalization. Example OPA
`corner-0-1050-0-25` has temporary grounded sequence **1,1,0,0,0** and ends with
**vy=-500**, not -1. The state selector runs once before the loop; intermediate
height changes cannot generate a new FALL request. The stuck counter and last
body normal persist, while saved fallback and iteration hit count are per-call.
On exhaustion the last genuine floor history remains published even if its
candidate differs from the final fallback. There is NO fallback floor requery.

### Jump boundary

Live E.1B currently keeps explicit jumps in `banjo_jump_step_overlay`, where
candidate formation and swept landing are in one function. The host harness
uses the real `PlayerMotionStep` dispatch, with a detached air-candidate adapter
using that unchanged pre-sweep arithmetic. A separate test executes the ACTUAL
existing jump function on a copy and captures its existing pre-collision
observer: candidate XYZ, post-gravity vy and horizontal velocity match exactly
for rest/full-speed takeoff and airborne Y-orbit.

A later live patch must route that one pre-collision candidate through E.2,
not execute the old swept landing first and then do body/floor resolution. This
proof does not change jump impulse, input, horizontal response or the live
sweep. After E.2 contact the original negative-vy finalization is -1; the legacy
sweep's landing vy=0 must not overwrite it. This is collision finalization,
not a new jump impulse/gravity policy. Diagnostic void recovery remains a
separate port lifecycle event after collision, with reinitialization and one
real relocation query at the same frame parity; it is not simulated as a body
iteration or a second physics step here.

## Ownership and lifetime (ARM ABI, bytes)

| Data | Bytes | Owner / lifetime |
| --- | ---: | --- |
| Persistent original floor state | 120 | Existing `CameraRuntime.bridge.floor`; one shared player/camera history |
| Clock/ordinal/lifecycle metadata | 12 | Existing floor bridge; begin/end once per simulation frame |
| `PlayerGroundState` | 36 | Existing camera runtime: BgState 28, FALL flag, jump-flight latch/padding |
| `BpState` last normal / stuck counter | 16 | Only NEW unavoidable semantic persistent state; one per player lifecycle |
| Existing `BcScratch` | 8000 | Reusable sequential query workspace, not camera history |
| E.2 five work records | 580 | Per-body-call scratch, rebuilt on every invocation |
| E.2 trace | 1184 | Diagnostic scratch; output aliases scratch.trace, no second persistent trace |
| `BpSharedScratch` union | 9764 | Proposed shared arena: player BpScratch OR camera BcScratch |
| `BpFrameContext` | 28 | Borrowed pointers for one call, not persistent storage |
| `BgFrame` | 52 | One physics candidate and original requested displacement, call-local |
| BridgeState | 40 | Existing runtime world lifecycle, no second player instance |
| Two BridgeModel views | 80 | Existing borrowed packets/state, no copies |
| Camera math table | 20002 | Existing immutable initialized table, borrowed by body edge helper |
| PlayerRuntime | 42644 | Unchanged owner of actor, velocities, accepted metrics and animation |
| Current CameraRuntime | 28508 | Unchanged in this task |

Full runtime/map initialization zeros body history as original
`code_C4B0.c:262–277` does. A floor-only reinitialization preserves body history,
clock and all floor fields except the original mode/countdown reset. No history
reset on a body miss, loop entry, landing, Y-orbit or a camera update. The stuck
counter evolves only via E.2; caller never derives it from a floor miss.

### Scratch safety

The viewer calls `cameraRuntimeMoveQueries` synchronously. The motion callback
returns BEFORE `cameraRuntimeUpdateView` uses `contact_scratch`; the latter
returns before `bridge_mesh_tick`. All query providers are synchronous leaves,
and bridge coordinate reads have no callbacks/publication. No job/thread or
camera reentry is launched by this path. GPU use is VBO/rendering, not CPU
contact scratch. Therefore the camera and player scratch leases cannot overlap
under the existing update order.

`BpSharedScratch` explicitly represents this reuse, with alignment 4 and both
members at offset 0. Tests overwrite all 8000 camera-scratch bytes between player
updates and still match original body/floor/history byte-for-byte. The 1764
bytes beyond the existing scratch remain necessary with E.2's current work/trace
layout; this task does not optimize it. Final player state and floor history
must never live in the scratch arena. No duplicate 8000-byte allocation is needed.

## World lease and original visibility

Both views point at the SAME BridgeState. The actor tick may change pending,
elapsed and alive fields before queries; it does not publish the applied XYZ.
There is no bridge mesh tick during E.2. Every floor query records all three
applied offsets, and the harness asserts the entire world state is unchanged
through the whole body callback (including sphere/line/secondary contacts).

Both tutorial and full-ability configurations are tested, including a fresh
pending actor decision with all original applied offsets still zero. All
queries of that frame see zero; only next frame sees the published -5000 mesh
selection. This is intentionally not "make all consumers see pending geometry".
The independent original actor/mesh routines publish the reference vertices
only after the frame's queries. Body providers borrow the immutable B3Q1 blocks.
No new provider, collision representation or packet/vertex copy exists.

## Independent proof and corpus

`body_frame_reference.py` augments E.2's compiled original decomp reference with
read-only before/after floor snapshots and original static-map supplier counts.
It imports no production body/frame/ground algorithm. The original
`func_8029350C`, `func_80293668`, floor state machine and primitives still execute.
A separate original E.1 reference proves state selection and normal candidate
formation. The existing production input/horizontal/gait modules are called
through actual `playerRuntimeMoveStepped`; their previously frozen numerical
contracts are retained, not reimplemented as this collision oracle.

Query instrumentation distinguishes floor INVOCATIONS from segment queries:
a floor call may perform ordinary AND special/split segment queries. Counts
compare the static map line supplier, including the original direct-map special
query which does not pass through the generic world-line wrapper. Sphere and
moving counts include secondary body queries. The main five-iteration bound
therefore is not a bound of five total primitive calls.

The frozen composition certificate includes:
- all 65 E.2 post-physics candidates, including steep 91/93/108, wall 258,
  original occurrence 497, long displacements just below/at/above 66, OPA/XLU
  corners and five-iteration exhaustion;
- 12 sequential schedules / 354 logical updates: wall, flat, plateau ledge,
  slope up/down, tutorial/full bridge, grounded Y-orbit, jump from rest,
  full-speed jump, airborne Y-orbit and landing near a wall;
- additional targeted tests for pending publication, reinit, scratch reuse,
  zero dt, invalid/second dispatch, deferred vy, physics/accepted separation,
  and the actual jump pre-sweep observer.

Every frame compares packed float32/u32 state at O0 and O2: final BgState,
full 120-byte floor history, BpState, complete BpTrace, each real floor candidate,
before/after floor snapshots, parity and primitive counts. The JSON additionally
records frame/dispatch counts, applied bridge offsets, heights and corrections,
full XYZ velocity, original physics candidate/request and accepted horizontal displacement.
No tolerance is used. State, physics candidate and body-loop dispatch counts
are each ONE (zero at dt=0); floor counts can be 1..5. Frame parity advances once
including the existing zero-dt clock frame policy.

Fixture SHA256 (`body_frame_golden.json`, 575260 bytes):
`9d8c3004d60cf90e4f9eb74df6360c3861663f247bb6afcebfb924e753ce8286`.
This is an additional integration certificate, not a replacement/re-freeze of
any accepted E.1/E.2 or earlier golden.

### Representative traces

Known wall: candidate (-37.666668,1783.233276,-3776), parity 0:
1. floor at Y1784, grounded; body OPA497 corrects Z to -3754.125;
2. genuine floor query at corrected position, same parity; body miss;
final grounded, vy=-1, floor ordinal 2, next frame identity 1.
Full physics speed remains 500 while accepted displacement is only about 3.125.

Steep91: first floor Y2014.666626 rejects support; body changes candidate.
Second floor Y1983.773193 also rejects support. Both calls share parity0; the
current frame has no extra FALL request and real vy remains -735.

Five-iteration OPA259 corner: five floor calls all parity0, saved fallback
returned, last floor history retained, ordinal5. The next update uses parity1
regardless of how many calls either update performs. Counter evolves once.

Plateau ledge schedule starts (0,1800,391.666779): first update accepts
Y1799.233276/Z400.000122; FALL request occurs on update1 using the previous
height, never inside a body iteration. No fail-closed XZ restoration is added.

## Costs and later integration plan

ARM O2 armv6k/hard-float, Werror and existing float flags:
- new frame.o: .text **288**, .rodata/.data/.bss **0/0/0**;
- unchanged body.o: .text **6272**, .rodata/.data/.bss **0/0/0**;
- frame wrapper own stack **64**; body resolver **648**;
- existing floor update **416**, segment model query **312**, moving model **272**;
- test-only runtime callback **296**, floor observer **112** (not production costs).
These are individual compiler stackframes, not the summed call-chain/interrupt
budget. They exclude libc/libm frames. No frame/query heap allocation or complete
collision copy is introduced by the proposed boundary.

Minimal future storage growth with the unoptimized accepted E.2 layout is
**16 semantic persistent + 1764 reusable arena = 1780 bytes**, making the current
CameraRuntime 30288 if both are placed there. PlayerRuntime can remain 42644;
ownership is logical player history even when held by the existing world owner.
The 28-byte context/52-byte candidate are transient, not added globals. Additional
raw code measured so far is 6560 bytes for body+frame, with existing math/query
providers reused. Future dispatch glue/link alignment/section GC determines
exact .3dsx growth; it cannot honestly be frozen before that patch is linked.
Current viewer .text/.rodata/.data/.bss/.3dsx and runtime RAM growth are **zero**.

Smallest later live patch: replace the supplied PlayerMotionStep callback's
collision boundary with one bp_frame_resolve after unchanged normal/jump
candidate formation; admit actual E.2 ordinals instead of the B.9 one-floor
assertion; add BpState and share the scratch union; preserve outer bridge clock,
recovery, camera and publication ordering. Do not call the old floor/sweep
resolution in addition to E.2. No new camera, geometry, physics or collision
formula is required by the tested normal static-map subset.

Unsupported: dynamic/cube providers, reentrant provider callbacks, alternative
collider modes, water/slide state controllers. No claim is made that this bounded
host composition ports those original systems, nor that isolated underwater XLU
geometry probes represent normal underwater gameplay. Diagnostic void recovery
remains the accepted port policy rather than an original Rare body-loop feature.

## Final validation

Baseline 341/341; final **353/353**, 164.156 seconds. All 12 new test methods
pass, including complete original/production comparisons at both -O0 and -O2.
The frozen 419-frame corpus executes **577 real floor-provider calls, 602
moving-sphere queries and 1304 static-map line queries** (including floor's
special/split queries). Additional focused tests are outside those counts.

ARM compilation passed with -Wall -Wextra -Werror and the project's numerical
flags, including a second body/frame/harness compile with -mword-relocations
and -ffunction-sections. No warnings. Diff, cached-diff and all new-file
whitespace/newline checks pass. All **242 pre-existing project/artifact files**
were SHA256-compared with the start-of-task snapshot: **zero changes**, including
old fixtures, generated headers and built ELF/3DSX. No viewer rebuild was needed.
Nothing is staged, committed or pushed; tools/n64splat was not accessed/modified.

For budgeting only, summing the measured nested floor-query branch's own frames
(frame 64 + body 648 + E.1 query 32 + floor 416 + query 104 + segment 128 + world
segment 104 + model query 312 + bounds 20) yields a conservative **1828-byte**
subtotal. It excludes the future motion caller, compiler/runtime/libm frames and
interrupt stack. It is not a measured total hardware high-water mark. The body
and camera call stacks are sequential, not additive live scratch leases.
