# M4.9D.3B: published bridge geometry for player collision

## Data boundary and lifecycle

The former player path read `banjo_floor_vertices` directly, independently of
the D.2 B3Q1/render overlay. This left mesh 499's walking surface at its original
Y even when the tutorial bridge had been moved down by 5000.

`cameraRuntimeMoveQueries()` now constructs a borrowed `MovementOverlay` from
`&CameraRuntime.world_bridge`. It passes that descriptor explicitly through
player/jump integration to the two vertex-reading algorithms: floor sampling
and swept landing. It contains the D.3A generated binding, count, borrowed state
pointer and applied-offset reader. No second BridgeState or global current-world
pointer exists. Original public entry points still use NULL (base geometry).

For a bound movement vertex, the only transformation is:

```
Y = (s16)(u16)((s32)immutableBaseY + (u16)sharedBridge.mesh[slot].applied)
```

This matches the original absolute vertex callback. X/Z, indices, flags,
surface, winding, triangle order, slope eligibility, +/-30 window, 14-unit
substeps, fail-closed acceptance and swept landing calculations are unchanged.
No coordinate matching or handwritten movement vertex/triangle IDs occur in C.
Only the generated rows select membership. Mesh 498 has no rows.

Original ordering remains (`src/core2/gsworld.c:315..338`, D.1 reconstruction):

1. Actor decision schedules offsets.
2. Player queries read the preceding **applied** offsets: support check,
   floor-follow, swept landing and diagnostic safe-floor revalidation.
3. Persistent camera floor/query/contact consumers read those same offsets.
4. Mesh tick publishes the requested offsets.
5. Rendering reads the newly published state after the existing GPU wait.

Thus publication intentionally changes what the next simulation update sees.
Neither player nor camera queries are moved after publication to force visual
same-frame agreement. The initial update can still query original geometry;
after its publication, tutorial queries no longer see the removed walking top.
Progress changes, deferred despawn, later ignored bit changes and fresh-map
reset remain D.2 behavior. Diagnostic player recovery does not reset the bridge.

## Generated input

The normal Makefile now generates `build/generated_bridge_movement.h` and its
audit sidecar using the unchanged D.3A generator. The existing binding bytes and
hashes are unchanged. The canonical rows are sorted by movement index, checked
in the integration test; their endpoints permit a cheap exclusion before
scanning the sixteen sparse rows. No indices are hand-entered at runtime.

The base collision arrays remain immutable: 4537 vertices / 3145 triangles,
64962 bytes of existing payload. There is no whole-buffer or whole-packet copy.
Only three six-byte FloorVertex values are read locally for a triangle. There
is no persistent transformed cache and no per-frame/query heap allocation.

## Independent checks

`test_bridge_player_collision.py` uses the independent source-index parser and
original actor/mesh C reference from D.1 to materialize expected geometry in
test storage only. The production sparse overlay is compared against those
coordinates at both host -O0/-O2 with strict float flags and warnings-as-errors.

- Every movement vertex compared, including all 16 bound vertices; mesh 498
  absent. Base vertex and triangle bytes unchanged after calls.
- All ten bound triangles, at original and shifted heights, for floor and sweep.
  Exactly 3042..3045 remain upward walking faces at their published heights.
- All 3135 unaffected triangles: floor and swept outputs bit-identical.
- Full PlayerRuntime state compared against the same solver given independently
  transformed geometry, before publication: ground movement, landing, progress
  change, despawn, reinit, takeoff, Y suppression and safe-floor recovery.
- Existing D.2 original query/render/camera comparison still passes, including
  the three seeded 14D0 contact schedules. No contact algorithm changed.

Hardware-regression probes after publication:

| Probe | tutorial / 0 | all abilities / 0x9DB1 |
| --- | --- | --- |
| floor XZ=(0,-1800), previousY=1576 | no hit | Y=1576 |
| floor-follow Z=-1800 to -1825 | rejected | Y=1576 |
| swept feet Y=1600 to 1540 at XZ=(0,-1800) | no hit | Y=1576 |

One old test-only candidate observer searched for the former floor-follow call
spelling. Its injection now names the overlay variant and asserts one matching
site. Candidate schedules and all frozen fixture bytes remain unchanged.

## Validation and measured costs

Full suite: **318/318**, including five new tests at -O0 and -O2. Both forced
normal Rare-camera builds succeeded with -Wall -Wextra -Werror, zero warnings:

```
make -B -C platform/3ds BANJO3DS_DEBUG_CAMERA=0 BANJO3DS_LEARNED_ABILITIES=0
make -B -C platform/3ds BANJO3DS_DEBUG_CAMERA=0 BANJO3DS_LEARNED_ABILITIES=0x9DB1
```

Final default binary is full abilities; the tutorial copy is
`platform/3ds/build/banjo3ds-tutorial.3dsx`. No new button/save policy.

| Section | pre-task full build | D.3B full build | delta |
| --- | ---: | ---: | ---: |
| .text | 143840 | 145840 | +2000 |
| .rodata | 1733724 | 1733820 | +96 |
| .data | 50148 | 50148 | 0 |
| .bss | 47024 | 47024 | 0 |
| .3dsx file | 1943696 | 1945796 | +2100 |

Tutorial: .text=145832, other listed data sections equal; .3dsx=1945788 bytes.
The file-size delta includes relocation/format overhead, not just payload.
Binding alignment 2, no padding; new adapter object text=52, rodata=96 bytes.
No additional persistent state: ARM CameraRuntime=28472, PlayerRuntime=42644
bytes, both unchanged. Borrowed overlay descriptor=16 bytes on the stack.

ARM GCC -O2 -fstack-usage own frames, compared with hash-verified pre-task source:

| Function | old | new |
| --- | ---: | ---: |
| cameraRuntimeMove | 136 | 160 |
| player move core | 152 | 152 |
| observed/overlay jump entry | 32 | 40 |
| jump step core | 144 | 144 |
| floor-follow | 80 | 88 |
| floor query | 36 | 96 |
| sweep core | 96 | 128 (+8 wrapper) |
| bridge descriptor / applied-offset reader | absent | 0 / 0 |

Summed own frames for the ordinary ground floor-follow path: 580 -> 680 bytes;
airborne sweep: 560 -> 632. These are path estimates excluding libm and the
separate candidate-observer/camera-query subpaths, not whole-program peak-stack
measurements. Existing camera/contact scratch storage is unchanged.

Generated model/camera/render-bridge headers, D.3A binding/audit, both B3Q1
packets and all frozen fixtures remain byte-identical. Counts remain 12600
render vertices, 97 textures, 469 materials, 510 draws (436/28/46), 36 geo nodes,
four SORT nodes and a 28022-byte posepacket.

No camera-wall tuning, physics changes, staging, commit or push. Hardware
acceptance is still required for both bridge configurations.
