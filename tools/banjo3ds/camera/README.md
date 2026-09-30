# M4.8B: bounded original camera correctness layer

Host-testable C. The original M4.8B layer changed no player, movement,
animation, collision, shader or generated model code. The separate
[M4.8C viewer adapter](../CAMERA_RUNTIME.md) now links these unchanged formulas.
Supports normal non-water Banjo, no scripted override/manual camera, free
dynamic state `0xB` and Spiral Mountain zoom-node 32 (`0x11`).

## Data and API

`setup.py:read_spiral_camera()` reads canonical `071D.lvl_setup.bin` (SHA256
`a0531b7207fad05bc8f22569b9c6148b469f9d37df10f71bf68871619180bba2`). It walks
the tagged cube section, not a pattern search. It returns all 150 real camera
triggers and the actual node32 fields at 0x2491. It does not modify assets or
generate a viewer header. Input outside this pinned asset is rejected.

The actual trigger at 0x11BA is center `(25,1925,-18)`, radius 443, node32,
normal-player mask1. Query XYZ is truncated to signed integers. Vertical tests
are `y+150 >= triggerY` and `y-150 < triggerY`; horizontal distance is strictly
less than radius. The retained query position changes only on `stable=true`,
which represents Rare's `player_isStable`, not merely a fabricated airborne
height test. Init supplies the initial probe explicitly.

Other map-camera states/profiles are deliberately unsupported. A new region
containing another active camera node returns false without modifying state;
new overlaps with other node IDs are conservatively refused, not arbitrated in
a guessed setup ordering. Existing node32 membership has priority as in Rare's
current-group lookup. This is not a general reconstruction of all trigger-group
ordering. Node32's connected trigger region and no-zone paths are the supported
domain. Neither unsupported profile38 nor other zoom nodes silently become B.

Call `banjo_camera_math_init` once for a shared lookup workspace. Init takes an
explicit viewport eye/angles, player position and floor. It starts at B's init
hook, zero lead/step buffers, preset2. It is not the game's complete map-entry
camera initialization. Update consumes new player position, visible yaw,
player floor, a separate floor-under-camera sample, dt and VI count. The current
viewer camera and SORT proxy eye are not read or changed.

`floor_under_camera` is an explicit future query interface. There is no fake
camera collision using player floors. Fixtures supply an unobstructed flat
floor. Original missing-ray behavior would supply old-camera-Y minus 600.
Node32 flags bit0 is off; passing a collision-enabled node is rejected.

## Original formulas / ordering

- `src/core2/code_9290.c:29`: stable probe refresh; normal selection mask1.
- `src/core2/gccube.c:1815,1916,1968`: integer membership and current-group
  preference. `code_A5BC0.c:1403` converts real trigger records.
- `src/core2/code_9BD0.c:62,182,242`: zone selection occurs before camera math.
  Leaving node32 changes mode9 to mode2 but **still executes zoom once**. The
  next update enters B and captures orbit using the then-existing lead. Entering
  node32 executes zoom immediately. Position/angular accumulators are retained.
- `src/core2/nc/dynamicCamera.c:548`: basis focus copies player XZ;
  `G+130 < P.y ? P.y+(80-130) : G+80`. Equality stays in the floor branch.
- `dynamicCamera.c:200`: update forward lead from visible yaw and the previous
  camera rotation/position. Angle/distance maps use 110..180 and 300..450.
  `lead += (target-lead)*.08f` is once per update, even at dt=0.
- `src/core2/nc/dynamicCamB.c:46`: B uses basis+lead, saved orbit; never an
  automatic ideal/physics-yaw follow. Desired eye Y uses G/130 threshold,
  preset height, and separate under-camera floor+35+20.
- Fallback radius/heights: `(550,175)`, `(850,375)`, `(1100,675)`, from
  `src/core2/code_35520.c:20`. Preset is explicit; no C-button controller.
- `dynamicCamera.c:798`: position error -> `3*(.003333*error)` -> step response
  `.003333*8`, executed `5*vi_frames` times, including original overshoot test.
- `dynamicCamera.c:672`: shortest pitch/yaw error -> `error*dt*5`; angular step
  approaches that via `10*(.0333*difference)`; original signed overshoot rules.
- `src/core2/nc/dynamicCam11.c:26`: zoom uses basis without lead. Clamp current
  horizontal radius to close/far, then anchor distance; normalize direction to
  anchor; desired Y=anchorY. At anchor distance <150 use anchor+offset look-yaw.
  Node32 gains and all coordinates come from data, not rounded YAML literals.
- `src/core2/time.c:20`: dt and real VI count are separate. API accepts finite
  dt `[0,.05]` and VI `[1,15]`; it does not infer VI count from dt. Rare can cap
  seconds while retaining a larger VI count. Invalid input preserves state.

No FMA/reassociation/fast-math. Preserve original double literals where present.
Camera angle lookup is `ml_acosf` (despite its name, first-quadrant inverse sine)
and its 10001-entry u16 table initialized using original libultra sin. It is NOT
the animation quaternion acos lookup. Cardinals retain original tiny residuals.

## Projection and Citro3D conversion

Projection checks use original 40-degree vertical FOV. Caller passes aspect:
BK `1.35185182f` and candidate 3DS `400/240` are **both tested**, neither chosen
for the viewer. Test clips 10/20000 are explicit diagnostic constants, not a
dynamic near-plane implementation. Float NDC is not an RSP fixed-point/raster
oracle. State/lookup matches are bit-exact; projected points permit absolute
error `2e-6*max(1,abs(reference))` for algebraically rearranged inverse rotations.

Original viewport stores camera-to-world yaw/pitch. View is inverse yaw then
inverse pitch applied to `(world-eye)`; RH forward is -Z, perspective W=-Z.
The production helper uses these original conventions, not viewer Rx*Ry angles.

To preserve X/Y projection in a future LH view, use
`viewLH = diag(1,1,-1,1) * viewRH` and LH W=+Z; don't negate the eye or blindly
copy original yaw/pitch into current viewer calls. Citro3D maths.h:545 documents
Mtx_PerspTilt's radians, aspect and handedness flag. The installed
libcitro3d.a:mtx_persptilt.o confirms LH W=+Z, tilted X/Y and PICA depth mapping.
Original GL-like NDC depth is -1..+1, while that Citro3D matrix maps near/far to
-1..0: tests intentionally equate X/Y, not the two APIs' depth columns. Tilt is
screen orientation, not an extra gameplay-camera orbit. A future integration
must use the reversed winding parity for this reflected view, retaining the
old mapping only for the proper-rotation debug view; see
[the M4.8B.10 culling proof](../CULLING_PARITY.md). Use real eye for SORT.

## Independent oracle / goldens

`tests/camera_reference.py` imports no production-camera code. It compiles the
original math/smoothing/B/zoom functions, original libultra trig, original
stable-probe update, membership queries and camera-mode update. Manual/water/
collision are stubbed outside scope. Node data/trigger parsing is independent
of `setup.py`. Typed-pointer corrections for host compilation preserve the
original addresses and arithmetic. The narrow node32 handler adapter installs
the real gains and focus mode; no unrelated map modes are emulated.

Original query groups in the oracle are represented as one record each; the
tested paths have unambiguous node32/no-zone membership, so this suffices for
the bounded traces. Broader grouping, script enables and overlapping camera
IDs require an independent extension, not silent reuse of this approximation.

13 scenarios x120 updates = 1560 state snapshots. Ground-turn inputs reuse the
independent M4.7B original-source paths (including original reversal/skid), then
hold their last sample after 60 updates. Jump inputs use explicit flat-floor
710/-1350 integration and stable=false until contact. They do not redefine
production jump physics. Fixtures start from a declared viewport rather than
assuming the camera was already settled. Landing/rest scenarios may share a
hash because their camera inputs are identical; their named assertions cover
different events.

State packing: 22 BE float32 values followed by 4 BE int32 values, no padding.
Fields: eye XYZ, pitch/yaw/roll, focus XYZ, lead XYZ, position-step XYZ,
angular-step XYZ, stable probe XYZ, orbit yaw; mode/state/node/preset. Orbit
direction is determined by the saved yaw through original func_80256E24.
Projection packing: six `>i3f` records per frame (valid,NDC XYZ), three points
(feet, feet+80Y, fixed world landmark), at each of the two aspects. All 9360
projected records are hashed; checkpoints are compared to production within
the stated tolerance. Reference -O0/-O2 hashes must agree exactly.

Golden file: `tests/fixtures/camera_golden.json`. Tests never regenerate it.
Explicit reference-only regeneration:

```
.venv/bin/python -B tools/banjo3ds/tests/camera_reference.py /tmp/camera_golden.json
```

## Memory (ARM ABI)

| Object | Bytes |
|---|---:|
| BanjoCamera persistent state | 104 |
| Shared BanjoCameraMath u16 lookup | 20002 |
| Per-update input | 36 |
| Immutable node32 parameters | 52 |
| One trigger / all 150 triggers | 24 / 3600 |

No heap allocation, hidden mutable globals or per-frame geometry work.
ARM -O2 camera object has 5640 bytes text, zero data/BSS (before linking math
helpers). GCC reports update's own stack frame as 304 bytes; callees/libm are
additional, so this is not a measured total runtime stack bound. Lookup is
initialized once, not each update. No performance optimization is attempted.
