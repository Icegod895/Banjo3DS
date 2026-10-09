# M4.10E-B: host-only first-person correctness boundary

No viewer linkage or existing camera changes. `first_person.c` uses no heap,
collision data, camera singleton or production reference helper. Callers supply
finite original-domain values. This is not a replacement player controller.

## API and ownership

* `FpCamera` owns six XYZ/angle vectors, timer and camera state (80 bytes).
* `fp_reset` clears vectors/state, deliberately retains timer; model visibility
  is external and is not reset. `fp_state` handles ENTER/EXIT source lifetimes.
* `fp_target` sets eye/look targets (original misleading `setZoomedOut*` names).
* `fp_view` consumes the existing underlying **post-transition** viewport and
  explicit `FpClock` (24 bytes). It changes only its own state, output viewport
  and external model-visible flag. Underlying internal camera remains untouched.
* `FpLook` (144 bytes, including 64 event bytes) observes normal DroneLook's
  service requests/held history. Animation playback, velocity integration and
  destination-state initialization remain caller-owned. It is intentionally an
  isolated orchestration boundary, not a live PlayerRuntime allocation plan.
* `fp_look_update` runs BEFORE external physics. It samples input XYZ+100, sets
  look targets, and requests entry/exit. A/B/C-up during IDLE request normal idle;
  they do not forward a jump/attack. The caller may resume gameplay while camera
  EXIT is still running. No invented post-physics eye refresh.

The selector's scope is normal dry safe ground, stand/creep/slow/walk/fast,
explicit previous stable flag/vertical velocity, supplied horizontal speed and
post-mapping target speed. It assumes the gait phase gate open, flap-flip learned,
no spring/flight pad, no skid/dangerous ground/script override. It returns the
original requested state; it does NOT execute those other gameplay states.
The exact FP predicate includes the supplied FP-map block and EXIT exclusion.
`stable_flag && vy < 0` is used, not merely a generic grounded boolean.

## Original evidence and numerical contract

* `src/core2/nc/ba/1p.c`: complete camera state machine extracted verbatim.
  ENTER captures internal camera except EXIT->ENTER (captures actual FP pose).
  EXIT uses stored target, not smoothed actual rotation, and an evolving viewport.
  State zero/DONE pass through. Visibility: ENTER distance <40 hides; EXIT >=40
  shows. Setter invocations are observed separately from the visibility value.
* `src/core1/ml.c:531,710,1257`: twice-nested sine easing, clamped mapping,
  timer decrement before interpolation. Position blends over 1s; ENTER angles
  over final .5s, EXIT angles over initial .5s. Not linear or smoothstep.
* `dynamicCamera.c:597`: smoothing reads GLOBAL gains, ignoring its apparent
  10/20/120/200 arguments. Five subiterations per real VI frame, separately from
  scaled/capped dt. Preserve double literals/promotions and float stores.
* `src/core2/bs/dronelook.c`: complete init/update/end extracted verbatim. Eye
  supplied by original `code_7060.c:339` case 5; this is NOT an animation bone.
  Original dry animation table supplies 006F, loop/reset, 5.5 seconds.
* `playerutils.c:109,206,210`: original eligibility/stability/floor proximity.
* `bs/stand.c:51` and `bs/walk.c` update functions: compiled whole for priority
  comparison with explicitly stubbed unrelated gait/audio/animation services.
  Normal fast zone 4 has no first-person check. Stand and walking differ in
  simultaneous A/Z versus C-up precedence. No universal C-up override.
* `dynamicCamera.c:383`: normal dynamic camera, viewport transition, THEN FP.
  This component neither resets nor freezes zone/contact/manual camera state.

Portable sine evaluates the bounded libultra finite polynomial. The oracle
instead compiles the ORIGINAL `lib/ultralib/src/gu/sinf.c` (endian-adapted original
constant bits through the existing independent reference infrastructure).
Both builds use `-ffp-contract=off -fno-fast-math -fexcess-precision=standard
-fno-strict-aliasing`. No tolerance. Original unused parameters/locals are
intentionally suppressed only in the decomp translation unit; production uses
unqualified `-Wall -Wextra -Werror`.

## Independent reference and frozen histories

`tests/first_person_reference.py` imports only independent reference utilities,
never the production FP/camera/controller algorithms. It extracts original
functions/tables; the C adapters bind globals and observe external calls. Dry
world, input, visibility, dt/VI and internal/viewport poses are explicit inputs.
The actual original state-priority functions are compiled, not reimplemented as
an oracle. Ordinary movement side effects during selector evaluation are outside
this boundary and their observer effects are discarded before DroneLook starts.
Sound output and animation reset/start are events; no audio/animation simulator.

`first_person_corpus.py`: 53 histories, 10,410 updates per optimization level:
29 camera histories / 4,470 updates and 24 look histories / 5,940 updates.
Every update compares every field in canonical packing, not just endpoints.
Golden SHA256 per history is frozen from the independent reference. The fixture
also pins all relevant original source hashes. The fixture is NEVER regenerated
by running tests. Future intentional updates must be generated from the original
reference's `first_person_corpus.golden` function, reviewed separately.

Packing (256 bytes/frame, no padding):

1. `>19f`: position, rotation, eye, look, source, source_rotation, timer.
2. `>2i`: camera state, model visibility.
3. `>6f`: output viewport position/rotation; `>i`: visibility setter event.
4. `>6f`: observed velocity, target speed, ideal yaw, animation duration.
5. `>30i`: buttons, active, flag, animation, starts, entries, exits,
   four update modes, last sound, requested state, event count, 16 event slots.

Additional direct selector/predicate cases cover 1,000 combinations per build:
800 stand/gait/input/stability, 80 override/ability, 120 eligibility boundaries.
Independent assertions protect event ordering, velocity clearing, 006F selection,
held input without repeat, no jump on A-exit, floor <25 versus >=25, exact timer
endpoints, nonlinear interpolation, shortest-angle ties, pitch limits, history
re-entry, reset, and internal-camera immutability.

Run: `python3 -B -m unittest discover -s tools/banjo3ds/tests -p test_first_person.py -v`
Full suite: `python3 -B -m unittest discover -s tools/banjo3ds/tests -q`

## Explicit exclusions / future boundary

No water/forms, scripted look-at/interrupts, camera shake or other viewport
effects; no eggs/crouch implementation, skid or complete gait/physics solver.
No new 3DS mapping, raw-stick normalization, rendering visibility integration,
projection/culling changes or camera collision. Stick axes are explicit normalized
original-domain inputs, not a claim that the port radial movement deadzone is the
N64 per-axis normalization. The existing 006F evaluator is not modified/tested
as part of the animation-event boundary.

The next layer would need to consume these gameplay events at the proven
pre-physics boundary, then apply the FP viewport layer AFTER the accepted manual
camera transition, with shared visible viewport for view/SORT/movement heading.
C-down's original LOOK suppression is an orchestration dependency; do not disable
all manual/zone updates. That integration is deliberately NOT performed here.
