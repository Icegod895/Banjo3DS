# M4.10C camera-zone runtime integration

The normal Rare-camera build now calls the proven M4.10B zone composition once
at the existing `cameraRuntimeUpdateView` boundary. No new camera mathematics.

## Dataflow and lifetime

```
bridge actor decision
  -> existing player physics/body loop and persistent floor queries
  -> terrain-under-camera query
  -> stable player XYZ + floorheight + visible yaw + dt/VI
  -> bridge_bz_update
       original group/local history and enablebits
       node parameters/profile -> camera prepare
       existing bridge-aware free-B contact/finish (B only)
       final view validation and atomic publication
  -> bridge mesh publication
  -> existing rendering
```

`CameraRuntime.zone_data` borrows generated constant trigger/group/node arrays.
`CameraRuntime.zones` owns the 96-byte BzState. It is initialized once at runtime
initialization, not on landing, B entry, zoom entry, or player void recovery.
Stable query XYZ, smoothing accumulators and obstruction/rollback state retain
existing owners and lifetimes. No new post-collision/final-position callbacks.

`bridge_state/query_zones.c` uses the existing compile-time namespace pattern:
the unchanged zone algorithm calls `bridge_free_b_finish_phase`, hence all
contact queries retain the published sparse bridge coordinate overlay. No new
BridgeState, query mathematics, collision buffer or per-frame allocation.

The camera exporter embeds 150 ordered triggers, 27 groups and 43 node slots.
150/26/27 group identity and every node parameter match the M4.10B oracle.
The existing B3Q1 packet bytes remain identical. The new arrays total 6,504
bytes plus a 20-byte ARM pointer descriptor; all reside in read-only storage.
Unused historical bounded-trigger/zoom arrays are absent from the final ELF.

On a successful update, camera, contact state, selector history and view commit
together. Unsupported node payloads and query failures preserve the published
camera/selector state. An ordinary query miss retains original no-hit semantics.
There is no old-selector fallback and no second camera/contact update.

## Independent runtime proof

`tests/test_camera_zones_runtime.py` calls the actual runtime and generated
arrays at both `-O0` and `-O2`. Original decomp selection/mode/camera/contact
routines are the oracle, not production `bz_update`.

- All 13 M4.10B schedules / 1,412 frozen-input updates per optimization agree
  exactly for packed camera state, counter/rollback history and zone state.
- Eight real player/floor trajectories (seven * 240 plus a 600-frame roundtrip,
  2,280 updates per optimization) use the actual E.2
  runtime output as inputs to the independent original camera chain. This
  checks the integration boundary rather than reimplementing player physics.
- Cases include spawn32, node11/trigger1542, node38, overlap history, zoom
  replacement, the final zoom exit frame, stable query XYZ during jumps,
  landing, full-speed movement and Y intent suppression.
- Both bridge progress configurations compare identical player, body, floor
  and bridge state with zones enabled versus disabled under identical explicit
  movement inputs. Existing independent bridge geometry/contact tests remain.
- Failure tests verify atomic state preservation. Generated arrays are compared
  byte-for-byte with the host data and against the frozen original group hash.

Historical M4.9 B.6 inputs and golden files remain unchanged. Its bounded
node32-only runtime comparison ends when the original bounded evaluator reports
an unsupported zone. M4.10's complete independent comparison continues through
those new zones. Test-only accessors allow the old no-zone diagnostic fixtures
to disable node enablebits; there is no legacy-selector branch in production.

Fixture viewport seeds are passed identically on both sides. The runtime's
normal bootstrap uses float32 player coordinates/addition; a Python double seed
must not silently become a different initial camera position.

## Measured build costs

Forced normal builds (`BANJO3DS_DEBUG_CAMERA=0`, `-Wall -Wextra -Werror`), bytes:

| Item | Before C, full bridge | C tutorial (0) | C full (0x9DB1) |
|---|---:|---:|---:|
| .text | 154536 | 156120 | 156128 |
| .rodata | 1733876 | 1736772 | 1736772 |
| .data | 50148 | 50148 | 50148 |
| .bss | 48840 | 48928 | 48928 |
| ELF file including debug sections | 3458320 | 3495824 | 3495824 |
| 3DSX file | 1954552 | 1959032 | 1959040 |
| CameraRuntime ARM symbol size | 30288 | 30376 | 30376 |

The baseline was rebuilt immediately before integration, including accepted
M4.10B API extraction. Full-to-full growth: text +1592, rodata +2896, bss +88,
3DSX +4488, ELF +37504 (debug information included). New persistent selector
storage is 96 bytes; replacing three old ARM fields with one pointer saves
8 bytes, giving net runtime growth of 88 bytes. Existing shared query scratch
is unchanged. Four-byte alignment is retained for generated data/packets.

GCC stack-usage measurements with the build's ARM/options plus `-fstack-usage`:
`cameraRuntimeMove` 232, `cameraRuntimeUpdateView` 544, `bridge_bz_update` 488,
prepare-selected 224, free-B finish implementation 504 (+24 wrapper), camera
finish 192 bytes. These are individual frames, not a measured hardware peak.
Nested existing contact/segment/math frames are additional; no 8,000-byte
contact scratch is placed on the stack. No per-frame heap or packet copies.

## Scope and hardware checks

Projection, 40-degree FOV, native aspect/clip policy, RH-to-LH conversion,
REVERSED culling, input handedness and renderer data are unchanged. Water/manual
modes, scripted overrides, active viewport transitions and dynamic providers
remain unsupported. No generic wall-sticking cure is claimed.

Hardware checklist:
1. Spawn on plateau: node32; walk/jump/land without a camera reset.
2. Visit the OPA wall/node11 area: verify zone entry and exit visually.
3. Traverse node38 and overlapping zones in both directions; stop and turn.
4. Cross zoom-to-zoom and zoom-to-free boundaries, including during a jump.
5. Verify both tutorial/full bridge layouts, player collision, free-B contact,
   four Circle Pad directions and Y suppression remain correct.

Stop after software validation. No manual-camera controls are added.

Validation: 369 tests, OK with six explicit existing skips. Both forced normal
builds completed with zero warnings. Diff/cached/new-file whitespace checks
are clean; model/render and bridge generated headers match pre-task SHA256.
All pre-existing tracked fixtures remain unchanged. Nothing staged or committed.
