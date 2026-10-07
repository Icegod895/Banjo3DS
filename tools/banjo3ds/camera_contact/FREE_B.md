# M4.9B.6: complete static free-B phase composition (host only)

The viewer still calls `banjo_camera_update()` without contact. Neither
`main.c`, `camera_runtime.c`, the Makefile nor generated data was changed.
`free_b.c` is outside the viewer's source directories. This work proves a
composition boundary, not a camera-collision integration or hardware result.

## Original ordering and the minimal API

`src/core2/nc/dynamicCamB.c:66–95` is authoritative:

1. `C0370` saves the unchanged previous camera position; `C0490` computes
   focus; orbit/distance/height compute the **unsmoothed** desired position.
   `C0394` preserves it independently.
2. `BE190` performs position smoothing, including the VI×5 internal steps
   and position accumulator (`dynamicCamera.c:838`).
3. `BE60C` compares pre/post-contact positions componentwise exactly
   (`dynamicCamera.c:940`). `BE484` mutates its separate previous-position
   copy through sphere pushout; this is **not** rollback's previous position.
4. Only effective position change executes `BC84C(1)` obstruction handling.
   Its fifth qualifying hit resets the counter before attempting recovery.
   Successful `BC640` sets position and clears both smoothing accumulators
   (`dynamicCamera.c:91–195`). Failed recovery leaves them intact.
5. When recovery did not succeed, `C03BC` may restore the unchanged previous
   position; it does not clear either smoothing accumulator.
6. Only the contact-changed branch executes `C04B0`: recompute orbit from the
   resulting position relative to focus. Then calculate look angles from that
   position. Successful recovery directly sets rotation to those angles
   **before** ordinary `BD904` rotation smoothing (`dynamicCamera.c:674`).
7. Commit position, rotation, focus/lead/orbit, accumulators and query state.

`camera.h` now exposes `BanjoCameraPhase`, `banjo_camera_prepare()` and
`banjo_camera_finish()`. Prepare finishes exactly at step 2 and preserves
previous/desired positions. Finish performs steps 6–7. The caller keeps input,
math and zoom data constant between phases. No camera formula was changed.
Unchanged public `banjo_camera_update()` invokes prepare/finish without contact;
all old original-source camera traces remain bit-exact. The `BanjoCamera`
layout remains 104 bytes.

`bc_free_b_update()` composes these phases with the unchanged M4.9B
`bc_state_b()`. Its contact-local `BcState` borrows/copies the already present
camera accumulators; no duplicate persistent accumulator state is introduced.
The explicit target input remains the original collider-center target, not an
invented replacement using camera focus. Failure commits no camera, post-state
or trace; scratch is unspecified. The caller validates B3Q1 with `bq_open()`.

Node32 continues to run the original zoom path without contact. Its real setup
flags are `0x75652082`, bit 0 clear. Unsupported zones remain rejected by the
existing evaluator; no fallback or new mode is supplied.

## Rollback history and edge behavior

Original `dynamicCamB.c:23–40` uses local static `D_8037DB9C`, separate from
previous position, desired position, contact pushout, smoothing and the
obstruction counter. `BcFreeBState.previous_rollback_dot` represents it.

The two differences are normalized with original `ml_vec3f_normalize`
(`src/core1/ml.c:190`): float32 squared sum; if nonzero, multiply by the
float32 reciprocal square root; otherwise leave the vector unchanged. Dot is
the left-associated three products/sums. There is no epsilon. Both `+0` and
`-0` compare false to `< 0`; a zero difference stays zero. The old history may
still trigger rollback when the new dot is zero or positive.

Rollback occurs iff `q < 0 || previous_rollback_dot < 0`. Store `q` after the
check even on rollback. History changes **only** when this routine executes.
Initialize it once for a fresh reference lifetime (original zero-initialized
static); do not reset it on B-init/re-entry. Original B-init (`:57`) only sets
gains/focus mode and recomputes orbit. Tests explicitly execute negative q,
original B-init, positive q that still rolls back, then positive q that keeps
the correction. An actual node32→B schedule also preserves negative history.
Recovery leaves this history unchanged; it resets precisely the original
counter/accumulators. Counter preservation on no-effective-change is tested.

## Independent proof and frozen schedules

`tests/free_b_reference.py` compiles original camera, contact, grid/triangle,
math and libultra functions extracted by the existing independent oracles.
It replaces only the old no-contact stubs, unifies duplicate original utility
definitions and adds observations. It imports no production camera/contact
algorithms. Original assets populate native reference structs; production uses
the existing B3Q1 packets. The local static rollback scalar is exposed for
observation without changing its arithmetic, execution condition or lifetime.

`free_b_corpus.py` specifies **23 schedules, 3,490 complete updates**. Each
frame compares camera XYZ/rotation/focus/lead, both accumulator vectors,
stable trigger position, orbit, mode/node/preset, separate history/counter,
previous/desired/smoothed positions, post-contact/recovery and final positions,
look target, rollback flags and all M4.9B contact observations.
`trace.corrected` means the output of contact **and conditional recovery**, but
before rollback; `final_position` is after rollback. Intermediate contact query
observations remain in `trace.contact` and the unchanged M4.9B fixtures.

Coverage includes the existing 13 real-world camera schedules; negative history
across node32/B; uninterrupted OPA/XLU/shared-wall approach, tangent motion,
recovery and subsequent ordinary smoothing; near-wall recovery failure;
obstruction miss/reset; unchanged position preserving counter/history; mutable
previous sphere pushout without effective final position change; and complete
chains at independently identified **real 14CF OPA and 14D0 XLU walls**.
Synthetic schedules isolate branch behavior; they are not gameplay trajectories.
Real wall fixtures explicitly seed a finite incoming smoothing accumulator and
stored orbit, then run uninterrupted original updates. Collider-center inputs
are explicit diagnostic data; no dynamic actor is simulated.

Measured coverage: 474 effective changes/obstruction queries, 321 rollbacks
(297 negative-dot and 24 historical-negative/now-nonnegative cases), three
successful recoveries, 33 failed recoveries, and 20 previous-position pushouts.
The OPA/XLU approaches reach counters `1,2,3,4,0` on frames 62–66; failed
recovery reaches that boundary on frames 81–85, trying all eleven directions.
Tests also verify direct recovery rotation and zero accumulators before normal
subsequent updates. No tolerances: original and production match at `-O0` and
`-O2`, with FMA disabled and float32 operation order preserved.

Canonical per-frame packing (big-endian, no padding):
`>22f4ifI19f11I9f`. Camera state precedes history/counter, phase observations and
contact observations. All 3,490 frames are hashed; selected checkpoints are
stored readably in `tests/fixtures/free_b_golden.json`.

| Stream | SHA256 |
| --- | --- |
| Canonical schedule inputs | `7b51ead367f4957d04e1f28d6fcc904c50f62cfb3cb07e633f2eaa5dbd9aa7ff` |
| Complete state/phase outputs | `b67e1a2f62e6b483bed2e7662fe2c2c005646e99843e9856e6a0373759a9740c` |

## Viewport boundary and limitations

`dynamicCamera.c:383–390` applies `func_802C22C0` after the dynamic-camera
update. We compile its actual body from `src/core2/code_3B2C0.c:33` and call it
after **every** reference update. `func_802C2258` initializes `s_state=0`;
the original routine immediately returns in that state. Exact byte comparison
proves camera position/rotation are unchanged on every fixture frame. No active
transition trigger is called. This proves only the inactive path: active
viewport transitions remain explicitly unsupported.

Scope is normal, non-water, non-snap, non-file-select Banjo, node32/free B,
untransformed static map providers, explicit existing terrain/player-floor
inputs and collider-center input. Dynamic actors, their transforms/provider
order, additional camera modes, active viewport transitions and full gameplay
camera lifecycle are not reproduced. Existing query capacity failures stay
explicit. No new collision primitive, player physics, projection, culling,
camera tuning or runtime integration is included.

## Memory and ARM cost

Measured with devkitARM GCC 16.1.0, `-O2 -Wall -Wextra -Werror`, existing ARMv6K
hard-float/function-section flags, `-ffp-contract=off -fno-fast-math
-fexcess-precision=standard`, and `-fstack-usage`:

- Additional persistent post-state: **8 bytes** (counter 4, rollback dot 4).
  The history specifically adds **4 bytes** beyond the existing logical counter.
  Existing camera remains 104 bytes; angle lookup stays 20,002 bytes.
- Transient phase: **140 bytes**; observer trace: **156 bytes**. The existing
  caller-owned contact scratch stays **8,000 bytes**; no packet/cache copy.
- Old camera object `.text`: 5,612; refactored: **6,424** (**+812 bytes**).
  `.rodata` remains 24; `.data/.bss` remain zero. New `free_b.o` `.text`:
  **928 bytes**, `.rodata/.data/.bss` zero. Total new object code: **1,740 bytes**
  over the old camera plus existing contact code, before final link pruning.
- Stack frames: prepare 272, finish 192, compatibility update 176,
  composition 488, rollback 40 bytes. Compatibility path's conservative C
  call-chain bound is **488 bytes** versus old 344 (both include vector's 40).
  Complete contact composition bound: **1,624 bytes** =
  `488+328+192+96+112+288+32+88`. Excludes caller-owned scratch/trace and
  C-library/compiler-helper internals; not a measured hardware high-water mark.
- No heap allocation, per-frame or per-query. Undefined-symbol audit contains
  no allocator. Existing packets remain **143,964 + 14,580 bytes**, unchanged.

The already-built ELF/3DSX and generated header remain byte-identical; no viewer
build was requested or performed. On a future rebuild the compatibility wrapper
has the code/stack cost above, but its camera behavior remains bit-exact. The
new contact composition is not linked or executed by the viewer.

Validation: complete suite **290/290**, old camera/contact goldens unchanged,
new reference/production comparisons at both optimization levels, ARM warning-
free objects, tracked/untracked whitespace checks. Nothing staged or committed.
