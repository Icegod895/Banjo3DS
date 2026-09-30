# M4.7B horizontal locomotion contract

This module is **not connected to the viewer**. It consumes post-normalization
magnitude and an already resolved world-space desired yaw. It does not change
3DS deadzone, camera-relative input, collision, vertical jump physics, animation
or gait selection. The separate N64 axis helper is an oracle/adapter, not a new
Circle Pad policy. Anti-tamper input attenuation is excluded.

## State and ordering

`BanjoHorizontal` (56 bytes) keeps input intent, target scalar/vector, actual
velocity, candidate displacement, accepted displacement, ideal yaw, visible yaw
and physics heading distinct. `BanjoHorizontalMetrics` is a 24-byte optional
snapshot for a future gait controller; it makes no gait decisions.

1. Set intent (normalized magnitude in [0,1], world yaw in degrees).
2. A future state controller may override `target_speed` for idle entry/skid.
3. At takeoff, replace actual velocity with the current intent's target vector.
4. Step horizontal physics; accepted displacement is cleared, not inferred.
5. The collision caller explicitly reports accepted X/Z displacement. Rejection
   does **not** silently replace physics velocity with zero.

Ground stepping uses the previous ideal yaw before updating ideal/visible yaw;
air stepping retargets movement heading immediately but retains the takeoff
ideal for visible-yaw smoothing. LOCKED is only a primitive for the original
skid contract (ordinary-ground response, fixed heading, no visible-yaw update).
There is no production skid state machine or animation integration.

The ordinary ground/air coefficients are .29/.07. Slopes, special surfaces,
Rare landing handlers, ground gait state transitions and their neutral-yaw
special cases remain caller/state-controller concerns. The skid predicate alone
does not establish eligibility: the original caller must be WALK or FAST.

## Numerical contract

Authoritative source locations in this checkout:

- `src/core1/joy.c:51,146`: axis deadzone 7, saturation X=59/Y=61, integer
  truncation, float `1/80.f` multiplication.
- `src/core2/bastick.c:30,60,79` and `src/core2/bs/walk.c:18,41`: magnitude
  clamp, float zone boundaries .12/.20/.50/.75/1 and target mapping.
- `src/core2/ba/physics.c:38,244`: flat-ground/air response and heading.
- `src/core2/commonParticle.c:79`, `code_15F20.c:16`, `code_C4B0.c:351`:
  ordinary-ground and air coefficient selection.
- `src/core2/yaw.c:42`, `code_12360.c:33`, `bsmethods.c:282`: yaw and ordering.
- `src/core2/bs/jump.c:37`: takeoff replaces actual horizontal velocity.
- `src/core2/playerutils.c:264`, `bs/walk.c:289,376`, `bs/turn.c:12`:
  strict skid gates and animation-phase-driven target ramp.

Do not reassociate the velocity expression:

```
scaled_target  = float(target * c)
scaled_current = float(actual * c)
difference     = float(scaled_target - scaled_current)
ratio          = float(double(dt) / 0.0333333)  // DOUBLE literal
increment      = float(difference * ratio)
actual         = float(actual + increment)
displacement_velocity = actual
if abs(actual) < 0.0001: actual = 0           // DOUBLE threshold
candidate      = float(displacement_velocity * dt)
```

`(target-actual)*c` and a float denominator are not interchangeable with this
sequence. World-heading conversion uses the original double BAD_DTOR constant
and libultra trig polynomial, including tiny cardinal residuals. No FMA,
fast-math, or quaternion/animation work is involved.

`dt` must be finite and in [0,.05]; the module rejects invalid steps rather than
inventing extra simulated time. The original yaw minimum increment is .1 degree
per call, even at dt=0; callers wanting a no-op for a zero-time frame must skip
the step. This edge behavior is tested, not silently changed.

## Independent correctness layer

`../tests/horizontal_reference.py` imports no production code. It extracts and
compiles original decomp C functions, original vector macros, and original
libultra sin/cos into temporary host libraries. Flat terrain and irrelevant
vertical gravity are stubbed. A test-only driver models the necessary idle-entry
and skid ordering; it is not a full Rare physics/gameplay emulator.

`../tests/fixtures/horizontal_golden.json` pins source hashes and 14 traces at
float32 dt=1/60, with checkpoints at frames 6/15/30/60 and 120/180 where relevant.
It additionally checks stop checkpoints 126/135/150. Hash packing is 19 big-endian
float32 fields per frame, in the fixture's `fields` order; no padding. The full
stream includes intent, target, velocity, proposed/accepted displacement, three
yaw concepts, speed metrics, accumulated position and path length.

Fixtures assume unobstructed ordinary flat ground; accepted=candidate. Air
traces change input on the update **after** takeoff, stop at 1 second, and do not
simulate a landing. Neutral-at-takeoff and neutral-after-takeoff are separate.

Both independent reference and production match the frozen streams bit-for-bit
at host -O0 and -O2. This is a source-based numerical contract, not a claim that
the complete NTSC executable/collision system has been replayed bit-exactly.
M4.7A's binary64 diagnostic numbers are checked only to their reported precision.

Run existing plus new tests normally:

```
.venv/bin/python -B -m unittest discover -s tools/banjo3ds/tests -v
```

Reference-only regeneration for review (never automatically in tests):

```
.venv/bin/python -B tools/banjo3ds/tests/horizontal_reference.py /tmp/horizontal_golden.json
```

Production build flags: `-ffp-contract=off -fno-fast-math
-fexcess-precision=standard`, plus normal warning flags. ARM object compilation
is validated separately; no Makefile or generated model changes are needed in
this stage.
