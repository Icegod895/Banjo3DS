# M4.10D-C: manual controller integrated with neutral physical input

Starting checkpoint: `5fa29290`. The D-B mathematics/reference remains unchanged.
The normal viewer now executes `bm_init` / `bm_update`, with logical buttons
explicitly **zero** and original input-enable mask `0x23` (bits 0/1/5).
There is no new physical 3DS button mapping.

## Ownership and frame boundary

`CameraRuntime.manual` owns one `BmState`: internal camera, zone selector,
post-contact counter/rollback history, manual state and visible viewport.
It replaces the separate camera/zone/post fields; it does not duplicate them.
`cameraRuntimeManualInput` supplies held logical `BM_R/LEFT/RIGHT/DOWN` and
original enablebits. The controller, not the caller, derives button edges.
Initialization defaults to neutral input; normal updates never reinitialize it.

One frame retains this ordering:

1. Scan existing controls; supply neutral logical manual-camera buttons.
2. `cameraRuntimeMovementInput` reads the **previous visible viewport yaw**.
   The accepted reflected Rare input basis and debug basis are unchanged.
3. Existing bridge actor decision; player horizontal/vertical/body/floor update
   and final player state. The floor bridge clock/parity and query cadence are
   unchanged. Existing Y intent suppression remains a player input policy.
4. Query terrain under the **internal** previous camera position through the
   published bridge query views. Supply the final player/floor inputs and +80Y
   body-center target to exactly one `bm_update`.
5. The proven controller performs zone/manual priority, dynamic camera/contact
   updates and viewport transition. It retains separate internal and visible
   state. Runtime validates the new visible matrix before committing state.
6. Existing bridge mesh publication, then rendering. The view matrix and SORT
   eye use **visible viewport XYZ/angles**, including R's 0.5-second transition.

The existing RH→LH matrix and REVERSED parity boundary is unchanged. Debug
NORMAL parity, orthographic projection and debug buttons are unchanged. Rare
presentation remains 40° vertical FOV, native 400/240 aspect, clips 10/20000.
There is no player, collision, bridge, animation, material or VBO change.

## Published world geometry

`bridge_state/query_manual.c` instantiates the unchanged D-B controller with
its external contact/finish dependencies routed to the existing bridge query
functions. `query_manual_contact.c` instantiates the unchanged manual gate and
recovery variants with `BQ_VERTEX_COMPONENT=bridge_component` and
`bq_segment=bridge_segment`. All queries borrow the same `BridgeModel` views
and published `BridgeState` as player/free-B/terrain queries.

The private shared source inclusion follows the existing bridge query build
pattern. The Makefile already discovers these two translation units through
its `bridge_state` source directory; dependency files include their source
includes. No duplicate standalone manual objects are added to the build.
The linker discards unused private entry points. No collision packet, vertex
block or triangle buffer is copied; no per-frame heap allocation is introduced.

## Independent validation

`test_camera_manual_runtime.py` drives the actual runtime adapter and observes
its single controller call using a **test-only** link wrapper. That wrapper is
not linked into the viewer. The independent oracle compiles the original
manual/zone/dynamic-camera/viewport routines, unchanged from D-B.

At both host `-O0` and `-O2`, packed float32 equality covers:

- All **43 / 7,360-update** frozen D-B histories through `cameraRuntimeUpdateView`,
  including R hold/release, 45° C edges/retargeting, gate rejection, zoom timer,
  node38, overlap/zone interruption and recovery variants 0/2/3.
- **2,160** additional updates: all three D.1 bridge diagnostic starts, both
  published ability states and neutral/R/left/right inputs. The oracle obtains
  transformed original vertices from compiled original actor/mesh routines;
  production keeps immutable B3Q1 packets and uses its borrowed sparse overlay.
- **480** updates through `cameraRuntimeMove`: actual player/body/floor updates,
  jump and Y suppression, injected logical manual input, original terrain
  queries and original camera/viewport evaluation. The movement basis is checked
  against the previous reference viewport, before this frame's camera update.

That is **10,000 independent integrated updates per optimization level**.
Existing D-B packed stream (`>53f13i8I9f`) SHA256 remains:
`091e285b262b4d1fbcaf4450fabc37baa3dd58da3b45a324e498a537e85d4a6f`.

Separately, **1,440 paired neutral player frames per optimization level** run
against the accepted original production zone path in the test-only wrapper.
Player state/velocity, floor history, body state, bridge publication, internal
camera, zone cache, contact history, visible viewport and matrix are byte-equal.
Starts include plateau, wall/floor junction, bridge and steep walkable slope;
both ability configurations, movement, coasting, jump and Y suppression run.
The existing original zone/body/floor/camera goldens remain independent checks.

The matrix tests use the visible output, not merely internal XYZ. A distinct
internal/viewport yaw test protects movement timing, and a source-boundary
check protects the neutral viewer setter, previous-yaw ordering and SORT eye.
Query rejection remains atomic for committed camera/viewport/view state.

Full Python discovery: **384 tests, 378 passed and six pre-existing historical
skips**, zero failures. Both normal forced 3DS builds (abilities `0` and
`0x9DB1`, debug-camera `0`) completed with **zero compiler warnings**. ARM object
stack/layout builds also used warnings-as-errors. Tracked diff, cached diff
and new-file whitespace checks are clean; nothing is staged.

## Measured ARM costs

ARMv6K hard-float `-O2`, existing `-Wall -Wextra -Werror`, float contraction off.
Baseline and final normal Rare builds were both forced with `make -B`.

| Measure | Checkpoint | D-C | Delta |
|---|---:|---:|---:|
| `CameraRuntime` | 30,376 | 30,520 | +144 |
| `PlayerRuntime` | 42,644 | 42,644 | 0 |
| Shared `BpSharedScratch` | 9,764 | 9,764 | 0 |
| ELF `.text` | 156,128 | 169,008 | +12,880 |
| ELF `.rodata` | 1,736,772 | 1,736,860 | +88 |
| ELF `.data` | 50,148 | 50,148 | 0 |
| ELF `.bss` | 48,928 | 49,072 | +144 |
| ELF file including debug information | 3,495,824 | 3,629,072 | +133,248 |
| `.3dsx` | 1,959,040 | 1,972,020 | +12,980 |

The new persistent bytes are 136 manual/viewport bytes plus 8 logical-input
bytes. `BmState` is 344 bytes, replacing 208 bytes of camera/zone/post state.
The shared scratch still includes the existing 8,000-byte camera-contact lease,
sequentially reused after player queries. `BmTrace` is 224 caller-stack bytes;
no persistent observation buffer is added. Tutorial/full bridge builds have
the same sections and 3DSX size (tutorial debug ELF is four bytes smaller).
The final artifact uses `BANJO3DS_DEBUG_CAMERA=0`, abilities `0x9DB1`.

Compiler `-fstack-usage` own frames (not total call-chain high-water marks):

| Function | Before | D-C |
|---|---:|---:|
| `cameraRuntimeMove` | 232 | 224 |
| `cameraRuntimeUpdateView` | 544 | 808 |
| `cameraRuntimeInit` | 120 | 112 |
| `cameraRuntimeMovementInput` | — | 104 |
| Previous `bz_update` / new `bm_update` | 488 | 992 |
| `bm_gate` | — | 136 |
| `bm_obstruction` | — | 240 |

The camera dispatch prefix is 2,024 bytes versus 1,264 (+760), before deeper
shared contact/math calls. This is **not** a measured hardware peak or whole
stack bound. Contact scratch is persistent, not an 8,000-byte stack frame.
New wrapper object allocatable totals before link GC are 13,128 and 10,340
bytes, with zero `.data/.bss`; linked growth above is the useful binary cost.
No allocator symbols occur in the runtime/manual objects.

## Protected data and limits

Generated model SHA256 is unchanged:
`4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`.
B3Q1 hashes remain
`59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953`
and `500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f`.
All frozen fixtures are unchanged. Rendering remains 12,600 vertices,
97 textures, 469 materials, 510 draws (436 OPA → 28 Banjo → 46 XLU),
36 geo-nodes, four SORT nodes and a 28,022-byte pose packet.

No physical manual control is enabled. Scripted/underwater/first-person modes,
dynamic providers, outer scripted viewport transitions, save-state integration
and audio callbacks remain outside this normal dry-Banjo camera contract.
R's own viewport transition is supported and independently tested. No hardware
CPU measurement or new hardware acceptance is claimed.

## Hardware acceptance plan (neutral controls only)

1. Start on the plateau: confirm node32, idle, full-speed movement and jump.
2. Walk the accepted route through node11, node38 and back to node32; check
   zoom/free-B transitions for sticking, stutter or unintended jumps.
3. Check four Circle Pad directions, including while jumping; Y still suppresses
   player intent and must not become a new manual-camera button.
4. Check tutorial and full bridge configurations, player landing and existing
   free-B wall contact. Inspect water/transparent ordering during movement.
5. Confirm START exit and no new response to currently unmapped camera inputs.

R/C physical acceptance waits for separate D-D mapping approval. Do not treat
this neutral build as a hardware demonstration of manual input transitions.
