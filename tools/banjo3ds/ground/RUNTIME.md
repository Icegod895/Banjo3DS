# E.1B player integration

`cameraRuntimeMoveQueries` still owns one simulation frame/parity advance and
one shared persistent floor supplier. It dispatches `playerRuntimeMoveStepped`
with `playerGroundStep`; there is no live grounded `movementFollowFloor` fallback.
The historical direct-movement APIs remain for their independent regression tests.

Normal updates execute:

1. Previous position/floorheight -> `bg_state_update` (strict >60 FALL request).
2. Existing horizontal response: ground until FALL entry, then air response.
3. `bg_candidate`: normal gravity -2700, terminal -4000, full XYZ candidate.
4. One pre-collision callback -> existing bridge cadence -> persistent original
   floor provider (upper 56, mask 0x400000, original history/ranges/no-hit/parity).
5. `bg_resolve`: exact E.1 normal/snap/follow comparisons; accepted X/Z survives
   a floor miss. Confirmed contact changes only negative vertical velocity to -1.
6. Commit actor/contact state. A prior-frame landing releases the FALL latch.

`PlayerGroundState` stores the last resolved normal phase, a one-update FALL
request, and whether an explicit A jump owns the current flight. It adds no
animation state machine, 00B0 clip, impulse on FALL entry, or body collision.
Existing animation selection still consumes the existing player events/state.

An accepted A edge retains the old support recheck, 710 impulse, -1350 jump
gravity, horizontal takeoff response, swept landing and diagnostic recovery.
A failed A support recheck follows E.1; it cannot select the old grounded
floor-follow path. After jump landing, the next ordinary contact produces vy=-1.
Natural ledge falling uses E.1 and does not masquerade as an A jump.

Initialization uses the existing actor spawn contact height only until the first
real candidate query; provider initialization/history are untouched, with no
fabricated warm-up callbacks. The six-call warm-up in diagnostic E.1 fixtures is
not used by production. Void recovery retains the existing validated last-safe
policy and the documented provider reinitialization/relocation callback. The
normal phase then adopts that genuine relocated query's height/history.

There is one BridgeState, owned by CameraRuntime. Normal resolution uses its
borrowed B3Q1 query views; A support/sweep/recovery uses the existing generated
movement provenance overlay. Both see the currently published mesh coordinates,
before the unchanged actor-decision/query/mesh-publication boundary. Neither
collision buffer nor packet is copied.

`test_ground_runtime.py` compares the live dispatch with original decomp-based
E.1 candidate/resolution and floor-state reference at -O0/-O2. It covers cold
spawn, flat/slope motion, ledge departure/delayed FALL, reacquisition, A jump,
landing, both bridge states, Y suppression, recovery and known steep/wall
limitations. Old B.9 candidate fixtures describe the historical fail-closed
player schedule; those bytes are retained and tested independently. Camera and
bridge integration tests feed the new genuine candidates into their unchanged
original references, rather than expecting the retired player path's positions.

No body/volume response is added. A wall or non-walkable steep face can still be
penetrated by this isolated phase; explicit tests retain those limitations.
No heap allocation occurs. ARM state additions: PlayerGroundState 36 bytes in
CameraRuntime; PlayerRuntime unchanged. Borrowed per-call context: 36 bytes;
BgFrame: 52 bytes, plus compiler temporaries and unchanged provider call stacks.

## Validated E.1B build

- Full Python suite: 334/334, including 213 real-schedule updates per optimization
  level in the new live-runtime/original comparison, plus boundary/lifecycle tests.
- Forced normal-camera builds: abilities 0 and 0x9DB1, zero warnings with Werror.
- ARM CameraRuntime: 28,472 -> 28,508 bytes; PlayerRuntime unchanged 42,644 bytes.
- Full-abilities ELF .text: 145,840 -> 147,392 (+1,552); tutorial .text 147,384.
- Both builds: .rodata 1,733,820 unchanged; .data 50,148 unchanged;
  linked .bss 47,024 -> 47,056 (+32, distinct from the C struct-size delta).
- .3dsx: baseline 1,945,796; tutorial 1,947,340; full 1,947,348 bytes.
- ARM O2 compiler stack records: playerGroundStep 160, cameraRuntimeMove 200,
  playerRuntimeMoveStepped 152, ground candidate 40, resolve 8 bytes. These are
  individual function frames, not an inclusive bound for the nested floor/query
  call chain. No new query recursion, heap allocation or collision-buffer copy.
- generated_model.h SHA256 remains
  `4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`.
- E.1 fixture SHA256 remains
  `8f3bdf8311a972cd57dd294ebec90e5c28bd50d4be0af862fa5f5580855f687a`.
- 12,600 vertices, 97 textures, 469 materials, 510 draws
  (436 OPA / 28 Banjo / 46 XLU), 36 geo nodes / 4 SORT, 28,022-byte pose packet.
