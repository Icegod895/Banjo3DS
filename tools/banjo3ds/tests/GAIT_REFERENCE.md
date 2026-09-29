# M4.5B independent multi-gait contract

No viewer integration. `gait_reference.py` imports only test reference helpers;
production never imports it. `fixtures/gait_golden.json` is generated exclusively
from the original-C channel/quaternion/matrix/blend oracle and independent
canonical 034D geo/RSP traversal. Regenerate explicitly with:

```
.venv/bin/python -B tools/banjo3ds/tests/gait_reference.py tools/banjo3ds/tests/fixtures/gait_golden.json
```

Do not regenerate expected values from the production evaluator. Tests compare
the frozen file to the independent oracle and production at both `-O0`/`-O2`.

## Pose coverage and packing

0002 and 000C: phases 0, 2^-20, .25, .5, .75, 1-2^-20, 1-2^-24, 1.
All poses use 49 calls, 695 triangles, 723 loads and 2085 corners. Phase 1
is byte-identical to phase 0 for both clips. Four SHA256 streams per snapshot:

- 109 transforms: big-endian `>10f`, quaternion XYZW, scale XYZ, translation XYZ.
- 60 matrices: `>16f`, Rare row-major, before RSP signed-16.16 quantization.
- 723 loads: `>3f`, transformed position in G_VTX load order.
- 2085 corners: `>3f`, unchanged triangle/corner order.

Animation SHA256/byte size/header/channel/key counts are recorded in the fixture.
Existing M3/M4 goldens are not replaced.

## Transition coverage

Source phase .37, initial factor 0, then eight updates of .025 seconds through
factor 1. Each row records actual destination phase, factor, frozen source hash,
destination hash and all four output hashes. Source/destination *gaits* are
explicit because WALK and FAST both use 000C.

Cases: IDLE->CREEP, CREEP->IDLE, CREEP->SLOW, SLOW->CREEP, SLOW->WALK,
WALK->SLOW, CREEP->WALK, CREEP->FAST, SLOW->FAST, FAST->SLOW, IDLE->WALK,
WALK->IDLE, IDLE->FAST, FAST->IDLE.

Interruption: CREEP->SLOW, interrupt after three updates (factor .375), then
SLOW->WALK. The new source is the mixed pose; the advancing SLOW phase is
preserved. No old source clip is evaluated again.

Original phase entry rules from `src/core2/bs/walk.c:117,190,262,339`:

- SLOW->CREEP, WALK->SLOW, SLOW->WALK, FAST->WALK, WALK->FAST preserve phase.
- Other changes reset to 0; unchanged gait keeps phase.
- No half-cycle or frame-count conversion.

The M4.4 reference supplies exact float32 scale/translation blend, original
shortest-path quaternion handling, identical copy, original acos lookup,
libultra sine and near-equal fallback. No normalization is added. Endpoints
explicitly copy source at factor<=0 and destination at factor>=1.

## Banjo3DS policy (not Rare physics)

Accepted speed / 150, clamped to [0,1]. No accepted movement or nonpositive
speed selects IDLE immediately. Bands: CREEP (0,.2], SLOW (.2,.5], WALK
(.5,.75], FAST (.75,1]. There is no extra idle deadzone.

For existing movement only: strict upshift above boundary+.02, strict downshift
below boundary-.02; equality keeps state. Multi-band jumps are allowed. Tests
exercise adjacent representable speed values below, at, and above every
float32 threshold, including division-by-150 rounding.

Duration endpoints are respectively 1.8->1.2, 1.3->.6, .92->.58, .54->.44.
Within each band, clamp normalized u to [0,1], interpolate in float32, then
clamp duration to [.3,1.5]. Idle loops at 5.5s. Fixture speeds 15/60/90/150
cross hysteresis in both directions; durations are independently calculated
with explicit float32 arithmetic in the test oracle.

Transitions take .2s; dt is capped at .05s. Destination advances each update.
WALK<->FAST is rate-only, preserving phase, factor and frozen source even during
an unfinished clip transition. All other clip changes freeze the latest mixed
pose and use the original phase entry rules above.

## Data / integration boundary

B3P3 v3 retains the 10950-byte shared prefix and binding offsets. The former
reserved word at offset 28 stores two big-endian u16 lengths (888,948). Raw
clips follow in order 0003,006F,0002,000C. Total: 26234 bytes, +1836 over v2.
The v1/v2 functions/packets remain available and unchanged for the live viewer.

The controller lives in `tools/banjo3ds/gait/`, outside the viewer's source
search directories. It updates only its own pose/state, never vertices or GPU
state. BanjoGaitState is 21248 bytes (uint8 gait replaces the old bool), with
one current pose and one frozen bone buffer; no additional skeleton or binding.
No movement, collision, camera, renderer, VBO policy or generated viewerdata
changes are part of this step.
