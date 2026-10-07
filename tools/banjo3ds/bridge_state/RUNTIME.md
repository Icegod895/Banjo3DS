# M4.9D.2: bridge overlay in the existing viewer

This connects the unchanged D.1 actor/mesh and coordinate-read contracts to
`CameraRuntime`. It does not change contact, free-B, camera or floor mathematics.
See [README.md](README.md) for original source evidence, mesh membership and the
independent actor/mesh goldens.

## Policy and lifecycle

The viewer has no save/ability subsystem. The explicit temporary build input is
`BANJO3DS_LEARNED_ABILITIES`, default **0x9DB1** (all nine required abilities).
For the tutorial configuration use a forced build with
`BANJO3DS_LEARNED_ABILITIES=0`. This is Banjo3DS test plumbing, not original
save-state integration. `cameraRuntimeSetLearnedAbilities` changes only that
input; it cannot resurrect the despawned actor.

| Committed state | Mesh 497 | Mesh 498 | Mesh 499 |
| --- | ---: | ---: | ---: |
| Before all required abilities | original Y | original Y | original Y - 5000 |
| All required abilities | original Y - 5000 | original Y - 5000 | original Y |

Each valid `cameraRuntimeMove` performs:

1. Original `bridge_actor_tick`: read progress, schedule transforms/despawn.
2. Existing player update and genuine pre-collision floor callbacks, camera
   terrain query and camera/contact update, using the **previously published**
   mesh coordinates.
3. Original `bridge_mesh_tick`: publish the transformed mesh coordinates.
4. In `main.c`, after `C3D_FrameBegin(C3D_FRAME_SYNCDRAW)` waits for previous GPU
   use, publish the matching Y values into the existing VBO and flush that range.

This preserves Rare's actor-before-camera / mesh-after-camera ordering. A frame
that schedules a mesh change intentionally queries the old state before mesh
publication, then renders the new state. All queries after publication read the
same new coordinates as rendering. No extra floor/camera queries are introduced.
Unsupported camera zones do not prevent the scheduled world tick. Invalid
runtime arguments do not run a world tick.

Fresh `cameraRuntimeInit` constructs a new bridge actor/state from immutable
base packets. The caller must supply the explicit progress input again. Player
void recovery and floor reinitialization preserve the world bridge lifecycle;
clearing progress after despawn does not replay the actor. No new map reload,
progress events, buttons or gameplay state machine are added.

## Query and rendering boundary

`BridgeModel` borrows a packet and the runtime `BridgeState`; there is no decoded
vertex block or packet copy. The existing D.1 namespaced query variants are now
linked into the viewer. Two additional compile-time wrappers reuse the unchanged
floor-state/cadence algorithms, routing their segment queries through that same
coordinate reader. Camera terrain, line, sphere, moving-sphere and complete
free-B composition therefore see identical bridge coordinates. Bounds, grid,
cell/occurrence order, indices, surface flags and every other coordinate remain
unchanged, including Rare's original unreconstructed grid after a mesh moves.

A separate build-generated `generated_bridge.h` binds original source vertex
IDs to the existing expanded map VBO. `generated_model.h` and its generator are
unchanged. Independent raw F3DEX traversal proves:

- 32 mesh source vertices: 134..165;
- 20 raw collision occurrences, 10 unique triangles (D.1 manifest unchanged);
- 48 rendered triangle corners: local XLU 162..209, full VBO 11655..11702;
- rendered source IDs 138..165 (28 unique vertices);
- mesh 497's IDs 134..137 have **no emitted render triangles** in this asset.
  Their query transformation remains required and is tested.

`bridge_render_y` writes only Y, from immutable original Y plus the committed
D.1 signed-16 offset. X/Z, UV/RGBA, vertex count, draw/material state and indices
are untouched. It validates the entire binding before any write. Invalid
bindings stop rendering instead of displaying a mismatched state. Absolute
publication catches up correctly after skipped draw frames and never accumulates
offsets. Flush size is **48 * 24 = 1,152 bytes**, only when Y actually changes;
there is no additional GPU allocation or per-frame heap allocation.

The separate player movement-floor representation and solver remain unchanged,
as required by this milestone. The synchronized collision contract here is the
B3Q1 camera/world-query path; this is not a port of dynamic player collision or
an attempt to change player physics.

## Verification

Six new integration tests run at host `-O0` and `-O2`:

- both progress configurations, despawn/history, reload, all source coordinates,
  immutable borrowed packet storage, renderer/query publication;
- independent F3DEX binding versus all 1,107 actual generated XLU corners;
- atomic invalid-binding rejection and publication after skipped render frames;
- all three `seeded-14D0-109/110/111` schedules, both progress states, 180 updates
  each: **2,160 runtime camera updates** across optimization levels;
- **7,200 actual player/camera runtime updates**, compared with original actor,
  mesh, persistent floor and camera routines: stationary/jump node32, free jump,
  walk, full-speed roundtrip and void recovery. Includes progress changing during
  flight. Query-before-publication is checked against the original mutable world,
  and player state is byte-compared with the physics-only runtime;
- GPU wait/write/flush/draw ordering and explicit normal-build policy.

D.1's existing 1,942-query-per-state corpus and full contact traces remain frozen.
M4.8/B.9 and M4.9C raw-map goldens explicitly use their original raw-map input
(no bridge actor); they are not rewritten to describe transformed geometry.
For example, with the tutorial bridge the old raw `free_jump_landing` floor
trace first differs at zero-based update 47. The transformed-world floor oracle
matches that change exactly; it is not hidden or compensated.

Node32 remains contact-disabled and bit-identical for equivalent inputs;
free-B outside changed bridge geometry retains the prior semantics. This does
**not** establish that general wall-sticking is solved. Dynamic providers,
other meshes/actors, camera modes and active viewport transitions remain outside
scope.

## ARM/build costs

Measured normal Rare-camera forced build, existing `-Wall -Wextra -Werror`:

| Item | Before D.2 | After D.2 | Delta |
| --- | ---: | ---: | ---: |
| CameraRuntime | 28,420 | 28,472 | +52 |
| `.text` | 142,776 | 143,848 | +1,072 |
| `.rodata` | 1,733,620 | 1,733,724 | +104 |
| `.data` | 50,148 | 50,148 | 0 |
| `.bss` | 46,968 | 47,024 | +56 (includes alignment) |
| `.3dsx` | 1,942,520 | 1,943,704 | +1,184 |

Persistent growth: bridge state 40 bytes, two borrowed state pointers 8 bytes,
progress input 4 bytes. Existing 8,000-byte contact scratch is reused. The render
binding occupies 96 bytes of `.rodata`; both packet symbols retain four-byte
alignment and their original 143,964 / 14,580-byte sizes. No complete packet or
vertex-block duplication is added. Unused base query variants are removed by
normal linker section garbage collection; the wrappers do not imply two resident
copies of the full query engine.

ARM `-fstack-usage`: runtime move 136 bytes, update-view 480, free-B composition
488, obstruction/contact 328/192, gated/moving 96/112, moving model 272,
iteration/overlap 32/88. Conservative combined C path bound **2,224 bytes**,
excluding main/caller and library internals (previous reported bound 2,240).
The render writer uses 32 + coordinate-reader 8 = **40 bytes**; it is not nested
inside camera contact. No hardware stack high-water or performance claim is made.

## Protected data

Both hashes verified from the actual final ELF `.rodata`:

- 14CF B3Q1: `59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953`
- 14D0 B3Q1: `500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f`

`generated_model.h` remains
`4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`.
The new 96-byte render-ID binding hashes to
`06e36b137775917e4519f48c37de8cdd6fc43f85b8332567a8deb433e7b886df`.

Render counts remain 12,600 vertices, 97 textures, 469 materials, 510 draws,
436 OPA -> 28 Banjo -> 46 XLU, 36 geo-nodes, four SORT nodes, 28,022-byte
posepacket. Existing fixture files, B3Q1 blocks, generated camera/model data,
player physics, animation and movement collision files remain byte-identical.
