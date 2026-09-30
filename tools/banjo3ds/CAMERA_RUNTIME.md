# M4.8C — bounded Rare-camera viewer integration

The formulas in camera.c, floor_state.c, floor_bridge.c and segment.c are
unchanged. The model header/export, movement floor representation and pose
packet are unchanged. This is the static Spiral Mountain provider boundary,
not Rare's complete player collision loop or dynamic actor collision.

## Runtime schedule

`cameraRuntimeMove` begins one bridge frame, calls `playerRuntimeMoveObserved`,
handles the existing explicit diagnostic relocation event, ends the bridge
frame, then evaluates terrain-under-camera and the camera. There is no heap
allocation, packet copy or triangle decode cache in this path.

The observer runs in jump.c at precisely these existing proposal points:

* Ground: after horizontal response, before `movementFollowFloor`.
* Air/takeoff/contact frame: after horizontal response and gravity integration,
  before `banjo_jump_sweep` modifies the endpoint.

There is one ordinary callback for a valid positive-dt update. dt=0 has none;
the bridge clock still advances once. Assertions and independent B.9 traces
protect that count and placement. No callbacks run for internal 14-unit floor
substeps, accepted/rejected final positions or landing contacts. Diagnostic void
recovery alone performs the existing explicit reinit + relocated-destination
event, with the same frame parity. Reinit retains original floor history.

The old player/jump entry points remain available with a null observer. Player
structures, velocity/physics arithmetic and animation APIs are unchanged.

## Initialization and timing

New viewer/player lifecycle fully initializes the bridge with parity seed 0.
The viewport seed matches B.9: player+(0,375,-850), rotation (340,180,0), preset 2.
The player Y used for this seed is NOT published as a floor-provider result.
No artificial candidate is submitted during initialization. Before the first
real successful floor/camera update there is no rendered Rare view. At the
normal (0,1800,0) start, that update selects node32 through all 150 actual setup
triggers. The init function does not assign node32 itself.

Physics dt remains the existing osGetTime-derived seconds, capped at .05.
Camera VI count is the delta of `C3D_FrameCounter(0)` at Citro3D's unchanged
default 60Hz frame rate, bounded to its proven [1,15] interface. This counter
is incremented by Citro3D's VBlank0 callback; no callback is replaced. The VI
count is deliberately not inferred from the already capped dt. Bridge parity
advances once per simulation update, not once per VI or floor call.

## View, projection and controls

`cameraRareView` applies inverse original camera yaw/pitch and then
`diag(1,1,-1,1)`. It publishes the finite view matrix together with REVERSED
winding parity. `rendererCullMode` remains the only per-draw N64/PICA mapping.
No shader sign fix, index reversal or geometry change is used. SORT receives
the actual Rare eye while retaining the existing subtree traversal.

Presentation policy: Mtx_PerspTilt, 40-degree vertical FOV, native top-screen
aspect 400/240, positive near=10 and far=20000. These fixed clips are the
diagnostic B.8 projection-test values, not Rare's dynamic clip system. The
`BANJO_CAMERA_ASPECT` macro keeps the independently tested BK aspect
1.35185182 selectable. No aspect correction is applied inside camera.c.

Movement remains camera-relative using yaw only. Conversion to the existing
movementDirection convention uses `cameraMovementInput`: yaw is
`180 - originalCameraYaw`, pad Y is unchanged and pad X is reflected. The yaw
conversion alone matches forward but produces the negative of Rare camera-right.
For Rare yaw r, right=(cos r,-sin r), forward=(-sin r,-cos r) in world XZ;
the legacy debug basis at 180-r has right=(-cos r,sin r). This single input-basis
reflection corrects that mismatch without changing the RH→LH view or culling.
Debug input is passed through unchanged. Pitch never enters movement input.
O0/O2 regressions cover all four stick cardinals at yaw 0/90/180/270 through
actual ground/takeoff physics and tilted projection, with Y suppression checks.

Normal build: automatic camera only. The old Y-orbit/D-pad/L/R/X camera controls
do not mutate Rare camera state. Y still suppresses player intent exactly as
before, with physics, gravity, floor cadence and automatic camera continuing.
A edge and START exit are unchanged. This is a temporary viewer policy, not a
new N64 camera-control mapping.

Diagnostic build: `make -B -C platform/3ds BANJO3DS_DEBUG_CAMERA=1` retains the
old orthographic debug controls and NORMAL parity. The floor bridge still runs.
Rebuild without that option to restore the default automatic Rare view.

## Failure boundaries

Packet hashes are enforced by the build generator and tests. `bq_open` validates
both immutable packets before runtime use; BqModel only borrows their pointers.
Four-byte-aligned const byte arrays preserve every B3Q1 byte and occurrence.

Unsupported triggers preserve the last camera/view. A segment selecting more
than 100 cells remains an explicit failure; no alternate query is substituted.
The ordinary terrain miss remains cameraY-600. The floor object's -9000 result
remains visible to Fbase. Neither case silently selects the debug camera.
`cameraRuntimeStatus` exposes WAIT/query failure/unsupported/invalid states to a
debugger. A failed update does not publish a new view. Initial packet failure
exits with status 1; no partially initialized world queries run.

Finite camera position/focus/rotation and view entries are checked before view
publication. No camera collision, pushout, additional modes or player solver
are introduced. Holding a view outside the supported trigger domain is an
intentional limitation, not a claim of complete Spiral Mountain camera support.

## Acceptance evidence

`test_camera_runtime.py` compiles the actual integrated code at -O0/-O2 and
compares all 15 existing B.9 runtime schedules: 3960 simulation frames, 3881
floor submissions and 3720 camera snapshots. Full floor-state and camera hashes
match the existing goldens, including rejected proposals, -9000, Y-held input,
apex/landing, reinit/recovery and node32's final zoom update before B.
Tests verify packet bytes/alignment/borrowed pointers, finite RH->LH matrices,
camera-relative cardinals, projection XY versus original projection, integrated
culling parity and explicit query failure. The existing geometry parity corpus,
physics/pose/animation/map/SORT regressions remain required.

Hardware/Azahar acceptance has not yet been performed for this integration.
