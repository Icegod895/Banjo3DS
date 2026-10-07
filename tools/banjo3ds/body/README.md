# M4.9E.2 — isolated ordinary Banjo body/floor composition

This module is not in the 3DS Makefile, player runtime or camera runtime. The
accepted E.1/E.1B code and all existing collision providers are unchanged.
Input is a real post-physics XYZ candidate. There is no input/speed/gravity,
state-selection, animation, save-state, slide or dynamic-provider implementation.

## Original order and boundaries

`src/core2/bsmethods.c:282–296` orders state update, physics, position offset,
then `func_80293F0C`. That function (code_C4B0.c:302) captures current candidate,
previous player position and their float32 difference, then calls
`func_80293668` (line 115). Normal mode 1 uses height offset **80** and radius
**35**, initialized at lines 253–277. Ordinary stand/walk/jump does not replace
that shape; climb, flight and transformed shapes are outside this contract.
The ordinary marker mask is 0x400000 (ba/marker.c:1005). Body queries add
0x1E0000, yielding **0x5E0000**. Special marker-dependent extra bits are excluded.

The exact body loop is:

```
original physics candidate, original requested XYZ difference
    |
previous FEET -> 44FC0 (sphere at previous feet +80Y)
    |               previous and fallback may differ afterward
    +-- optional +100/-500 line above/below pushed previous feet
    |
up to five iterations:
    candidate and mutable previous copied from preceding iteration
    if |candidate - mutable previous|² > (2*35 - 4)²:
        44E54 -> 44D94 -> world line (+80Y, extend endpoint by 34)
        discard hit/correction if normalized movement dot normal > 0
        preserve candidate Y for 0 <= normalY < 0.02
    9350C: persistent floor query + original E.1 floor resolution
    save this iteration's grounded flag
    current-center = mutable previous feet +80Y
    candidate-center = floor-corrected feet +80Y
    world moving-sphere(radius=35, bisection steps=3)
    miss -> stop (accept the current floor-corrected candidate)
    hit -> retain original hit identity/normal and increment contact count
        third-iteration A/B/A: combine current and preceding normals
        third-iteration A/A/A: plane projection / 36-unit reposition / requery
        descending, not grounded, abs(normalY)<0.01: separate plane/requery path
        normalY>0.999: closest TRIANGLE EDGE correction in horizontal plane
        otherwise nonzero normal: original 450DC normal correction
    repeat with the corrected FEET candidate (same requested DY, same parity)

five hits/exhaustion -> stored fallback position, NOT last corrected candidate
post-loop stuck-ground override, then negative vy -> -1 if grounded
update three-frame stuck counter; retain final provider history
```

`func_80244FC0` (core1/code_72B0.c:94) first computes
`fallback = previous + sphereNormal * 35`, and copies this into `previous`.
Its optional `44CD0` line may subsequently raise **previous**, but does not
change **fallback**. The input physics difference is not recomputed after this
mutation. This distinction is observable in the corner fixtures.

The >66 gate is **strict squared 3D displacement**, recalculated each iteration;
it is not horizontal speed or dt. The line extension is radius-1 = **34**, not
the camera's 35-unit extension. Its Y offset is removed after the line result.

## The primitives are not interchangeable

World wrappers in `code_999A0.c:106–187` iterate registered providers, preserving
mutable endpoints. This layer supplies ONLY the static map provider:
`mapModel.c:450` line, `:518` moving sphere, `:540` sphere. They process OPA then
XLU. A moving/line endpoint modified by OPA is passed on to XLU. Only the line
wrapper has the special OPA-skip mask test; the ordinary body mask does not match
it. No dynamic/cube/actor transforms or provider ordering are fabricated.

The existing proven B3Q1/bridge query implementations preserve raw occurrences,
cell order, winding, flags, normals and failure domains. They are called directly:
`bridge_sphere`, `bridge_segment`, `bridge_moving`, `bridge_floor_update`.
There is no new geometry export, deduplication, coordinate matching or copied
vertex/triangle buffer. Bridge coordinates are read through `bridge_component`.

Player moving-sphere calls go directly to `func_80320C94`: **there is no
segment-length <= radius gate** here. The camera's `8024575C` gate must not be
imported into this player loop. The primitive still requires endpoint overlap
before its original three-step bisection. It keeps the last clear endpoint,
not an analytic time of impact (code_5FD90.c:609–660).

The body response is not direct assignment of the sphere endpoint. `450DC`
(core1/code_72B0.c:118) computes:

```
feetDelta = correctedFeet - previousFeet
sphereDelta = queriedEndCenter - queriedStartCenter
amount = max(5, -dot(normal, feetDelta - sphereDelta))
correctedFeet += amount * normal
```

The repeat-contact and nearly vertical-normal paths use the original plane and
closest-edge helpers (`ml.c:583–639,1312–1360`). Edge projection uses Rare's
quantized `ml_acosf` inverse-sine table and libultra cosine. It is not replaced by
a modern analytic closest-point routine. The production layer borrows the
already-proven 10001-entry math table, without changing camera mathematics.

Body queries do not use a walkable-normal threshold. A triangle rejected as
floor at normalY<0.432 can still provide body contact. Conversely a floor-eligible
triangle can also be a body obstacle. The provider's one-/two-sided, flag and
summed-normal rules remain the existing proven contact contract.

## Reusing E.1 unchanged

Each loop iteration calls `bg_query_resolve` with the same persistent floor
state, the current grounded flag, original requested DY, and unchanged parity.
The floor phase's snapped result becomes the input to body contact. A further
body correction produces a genuine NEW floor candidate on the next iteration.
No queries are fabricated for the final/fallback position.

E.1's standalone API also finalizes negative vertical velocity to -1. The body
composition evaluates it in a temporary `BgState` with vy=0, consumes only its
position/height/contact outputs, and defers the ORIGINAL velocity finalization
until loop end. No floor formula or accepted E.1 API is changed. The input real
vertical velocity is otherwise untouched; a body normal does not invent new
horizontal or vertical physics.

Original persistent fields retained for this normal subset:
- D_8037C279: grounded, supplied/returned through existing BgState.
- D_8037C258: last body normal, 12 bytes (retained on a miss).
- D_8037C280: saturating 0..3 stuck count, represented by uint32.
- Existing original persistent floor object: reused unchanged.

Per-frame D_8037C27D hit count and the last original occurrence/provenance are
visible in the trace. On exhaustion while ungrounded, with a recorded contact
and the ORIGINAL candidate below the mutable previous position, stuck increments
up to 3; otherwise it resets. The old counter==3 forces grounded before the
counter is updated (code_C4B0.c:348–377,462). This is a source rule, not new
anti-fall policy. Water handling, forced position freeze, alternate collider
modes, slope response and slide state selection remain unsupported.

## Independent proof and trace packing

`tests/body_reference.py` compiles the original `9350C`, `93668`, `44CD0`,
`44E54`, `44FC0`, `450DC`, `457C4`, closest-edge/plane helpers and the original
static query/floor routines. Original assets populate native reference structs;
original actor/mesh callbacks publish the bridge coordinates. It imports no
production body/ground/query algorithm. Host changes are pointer-width adaptation,
existing bounded-buffer guards and read-only observers. The previous reference-only
stored-triangle no-op stub is replaced by the original implementation. Uninitialized
normal data on an original miss is excluded from snapshots, never consumed.

The fixed real-map candidates include the audited wall, triangles 91/93/108,
flat floor, walkable uphill/downhill slope, ledge, airborne/landing wall contact,
OPA and XLU faces, repeated/alternating corner contacts, five-iteration exhaustion,
bridge configurations and representable endpoints immediately either side of 66.
Six multi-update schedules retain the floor object, body normal and counter.
Separate counter-entry fixtures cover 0,1,2,3 including forced-ground behavior.

`body_golden.json` freezes canonical little-endian float32/uint32 byte hashes:
result, final XYZ, vy, grounded, counter, full trace, full 120-byte floor snapshot.
No host pointers or unspecified padding enter the hash. Trace records initial,
after-line, after-floor, both queried centers, initial contact normal, final
corrected feet, role/raw occurrence, ground/line/path bits and the complete floor
snapshot for every executed iteration. Unused iteration slots are zero.
Path bits: 1=A/B/A average, 2=A/A/A projection, 4=descending vertical wall,
8=closest-edge, 16=normal correction, 32=line rejected by approach,
64=long-line path executed. All seven bits are exercised by real geometry.

## Limits and later boundary

The known wall and steep failures are explained by omitted body response over
SUPPORTED static geometry, without modifying static data or needing dynamic
providers. This is not proof that all hardware terrain problems share that cause.
Actors/cube providers, their transforms/order, water states and slide/surface
physics are not reproduced. No dynamic scenario is used to justify a static fix.

A later runtime step would surround the existing E.1 floor phase with this body
loop AFTER unchanged physics, then commit position/contact once. It must first
make the cadence owner admit the 1..5 genuine floor candidates at a single frame
parity; the current one-callback assertion cannot simply remain or be bypassed.
Explicit query failures (invalid domain or original 100-cell/triangle capacity)
remain errors, never ordinary misses. `bp_resolve` commits state/output atomically
on success; caller-owned scratch may change on failure.


## Validation results and measured costs

Baseline suite: **334/334**. Final suite: **341/341** (136.083 seconds).
Production and original reference agree bit-for-bit at **-O0 and -O2**: 65
single-update cases, six schedules / 128 updates, and four stuck-counter entry
fixtures. No tolerance is used. All seven recorded correction-path bits are
exercised by real Spiral Mountain candidates. The lower XLU/corner probes are
isolated geometry diagnostics, not claims about gameplay remaining in ordinary
locomotion while underwater. No dynamic provider is needed for these tests.

Fixture SHA256:
`5cfc9e36bb81b03b16e428fbac25b0e17f945e6a743f1d5a418d84073dbb8535`

Known wall: requested feet (-37.666668,1783.233276,-3776).
First floor phase resolves Y=1784 with grounded=true. The body sphere hits OPA
occurrence 497, normal (0,0,1), and corrects Z to **-3754.125**. Iteration 2
requeries the floor and the body misses. Final vy=-1, grounded=true. Both
compilers and production match every intermediate byte; no triangle-ID branch
exists in production.

| Movement triangle | Original body occurrence | First floor normal Y | Final feet XYZ | Final grounded |
| --- | --- | --- | --- | --- |
| 91 | OPA 1701 | 0.3992017806 | (-3823.450195,1993.773193,-3157.542236) | false |
| 93 | OPA 404 | 0.3898280263 | (-3358.189209,1666.501343,-3356.558350) | false |
| 108 | OPA 260 | 0.2853161991 | (-1297.292358,1335.405396,-3364.907959) | false |

Each has one body hit followed by a second genuine floor query and body miss.
The first floor heights are respectively 2014.666626, 1687.666626 and 1355.666504;
all are rejected as support by E.1. The body normals are independently computed
by the contact primitive, so their last bits need not equal the floor normals.
The exact per-iteration centers, endpoint, floorstate and correction results are
in the JSON fixture. Triangle 91 preserves the specified diagnostic start and
E.1 gravity candidate at Y=1987.916626, rather than treating its expected result
as an implementation input.

The real OPA floor/wall corner includes movement triangles 237/259, sharing
(-113,1784,-3791) -> (0,1784,-3791), with inward normals +Y and +Z. Other corner
fixtures include bridge top/side geometry, repeated same-face contacts and the
XLU occurrence sequence 252 -> 256 -> 252. They expose the original recovery
rules; they do not claim those rules always yield visually ideal movement.

ARM O2, armv6k/hard-float, original numerical flags, Wall/Wextra/Werror:

| Cost | Bytes |
| --- | ---: |
| BpState additional persistent normal/stuck history | 16 |
| BpScratch caller-owned total | 9764 |
| Existing BcScratch within that total | 8000 |
| Five iteration work records | 580 |
| Diagnostic trace within scratch | 1184 |
| Optional separate output trace | 1184 |
| Existing floor object reused | 120 |
| Existing math table borrowed, not copied | 20002 |
| body.o .text (including literals) | 6272 |
| body.o .rodata/.data/.bss | 0/0/0 |
| Largest own stackframe: bp_resolve | 648 |
| edge helper stackframe | 64 |
| plane / shifted-moving helper stackframe | 56 / 56 |

The output trace may be the caller's scratch.trace, avoiding a second trace
allocation. Stack numbers are individual frames, not the sum of the existing
nested floor/segment/contact stack. Queries reuse existing provider code and the
existing contact-scratch format. No per-query/frame heap allocation or complete
collision-buffer copy occurs. Expected later work scales with 1..5 floor phases
and contact iterations; secondary contact paths add queries. Hardware CPU time
is unmeasured because this layer is deliberately not integrated.

All files present at E.2 start remain byte-identical, including the 3DS ELF/3DSX,
generated headers, B3Q1 blocks, E.1/E.1B and all earlier fixtures. Viewer code,
RAM and binary growth from this task: **zero**. Diff and cached checks are clean;
new files are separately checked for trailing whitespace. Nothing is staged.
