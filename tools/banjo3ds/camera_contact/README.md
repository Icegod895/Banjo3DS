# M4.9B: static camera contact, not viewer integration

This module implements the static-map part of the corrected camera-contact
contract. It is deliberately outside the 3DS Makefile's source directories.
The running viewer still does **not** execute this pipeline. Its current wall
behavior cannot be attributed to this code. No camera tuning is included.

## Original sources and five distinct operations

Line numbers refer to the NTSC decomp in this repository.

1. **Sphere contact:** `src/core2/code_5FD90.c:705`,
   `collisionList_intersectSphere`. Bounds use `radius + 0.5`; plane distance
   must be strictly inside `radius - 0.5`. Projected barycentric edges are
   inclusive; vertex/edge squared-distance tests are strictly `< radius²`.
   Every eligible occurrence contributes its normalized normal, including
   repetitions across cells. Return the last matching occurrence and normalized
   normal sum. This routine does not apply moving-sphere backface filtering or
   its `0x10000` normal flip. A cancelling normal sum remains zero.
2. **Moving sphere:** `code_5FD90.c:412,510,612`, FastCheck/Iteration/main.
   Capture the original cell/occurrence stream for the expanded segment box.
   Without `0x10000`, discard triangles whose normal points with the velocity;
   with the bit, orient the normal toward the start. Test overlap at the
   **endpoint first**. If absent, return no hit, even if an analytic sweep would
   cross geometry. Otherwise set the endpoint to the start and perform the
   specified number of midpoint tests; keep the last non-overlapping point,
   not an analytic time of impact. Normals/identity follow the last overlapping
   iteration. `src/core1/code_72B0.c:284` gates the wrapper with
   `radius < distance(start,end) -> no query`; equality executes it.
3. **Line contact:** reuse the unchanged, independently proven B.7
   `bq_segment`. Source: `code_5FD90.c:214` and `mapModel.c:450`.
   Strict segment endpoints, inclusive triangle edges, existing winding/normal
   semantics and progressive endpoint shortening remain intact.
4. **Contact correction:** `nc/dynamicCamera.c:867,881,905`:
   `BE258(previous,35)` queries/pushes **previous**, not desired. It permits one
   `+1.5 * normal` push; C condition ordering executes a second sphere query
   before checking the iteration limit. Then `BE484` extends the desired line
   endpoint by **+35**, queries it, and subtracts the same vector even on a miss.
   The gated radius35/three-iteration moving query sees that resulting segment.
   A hit runs the original `BE384` normal projection correction, then the second
   extended line/subtraction. Both previous and desired are mutable outputs.
5. **Conditional state-B obstruction:** `dynamicCamB.c:81` calls
   `dynamicCamera.c:135` (`BC84C(1)`) only when BE60C's exact component comparison
   says the contact-corrected camera changed. The target is explicitly supplied
   `func_8028EC64()` output (`code_7060.c:430`, player position plus current
   collider-center offset), not camera focus/lead. Counter offsets are zero,
   -90-degree/100-unit side, +90-degree/100-unit side, +100Y, zero. The target
   ray caps at 1500 units. Only an executed hit increments; miss resets; no
   execution preserves the counter. The fifth hit resets it **before** recovery.
   `BC640` tries exactly `0,-25,25,-50,50,-80,80,-120,120,-140,140` degrees.
   Recovery uses the original line-extension helper (+40, subtraction on hit
   only), gated radius40/four-iteration moving query, and strict distance
   `> max(150,targetDistance-100)`. Success changes camera position and zeroes
   the position/angular smoothing accumulators; failure still leaves count=0.

Map wrappers: `mapModel.c:515` moving, `:535` sphere, `:450` line. OPA runs before
XLU and shares the mutable endpoint with it. Only the line wrapper skips OPA
when XLU exists and `(filter & 0x80001F00) == 0x80001F00`. No such skip is applied
to sphere/moving. Flags otherwise reject by nonzero intersection with filter.
Camera correction uses `0x009E0000`.

Grid behavior is the original float-bounds selector (`code_5FD90.c:35`): truncate
coordinate to integer, C integer division, then subtract one for any negative
coordinate, including exact negative grid multiples. Clamp and traverse z/y/x
in original cell/occurrence order. Global-norm rejection is unchanged. No
deduplication or sorting. Native B3Q1 vertex/record blocks are borrowed and read
bytewise in big-endian order; packet alignment is not required.

## API boundary and deliberate exclusions

`bc_sphere`, `bc_moving`, `bc_gated`, `bc_contact`, and `bc_state_b` are separate.
The last name means **contact plus conditional obstruction**, not a complete B
update. It does not implement the subsequent `C03BC` direction-reversal rollback
and its previous-dot history (`dynamicCamB.c:23`), `C04B0` orbit reheading, camera
smoothing or final look rotation. Those require a future integration contract.
It does not silently pretend they have run. The caller supplies the pre-contact
camera positions and collider-center target and invokes only on enabled paths.
The snap/file-select skip in `BE60C` is not invented as an extra input/state here.

Node32's actual 071D setup flags are **0x75652082**, bit0 clear. The getter
`code_33310.c:118` controls `dynamicCam11.c:59,78`: no contact call for that node.
This is independently checked against the original setup parser.

Original world dispatch (`code_999A0.c:106,129,152`) walks registered providers
and passes mutable arguments through all of them. B3Q1 supplies only untransformed
static OPA/XLU. Dynamic model/actor transforms, provider registration/order,
markers, pumpkin target behavior and full game camera-state lifecycle are not
available from those packets. No dynamic provider or player-floor replacement
is fabricated. Initialize `BcState` to zero once and preserve it between calls;
original camera initialization clears the counter (`dynamicCamera.c:246`).

Public return values: 1 hit/changed, 0 miss/unchanged, -1 outside defined domain.
Outputs/state commit atomically on success; scratch is unspecified on any call.
Models must pass existing `bq_open`; inputs/outputs must not alias. Normal camera
radii/steps are 35/3 and 40/4. Finite coordinate domain is ±1e6; radius is
(.5,10000]; steps 0..32. Original fixed arrays cannot safely represent more than
100 selected cells or moving-triangle occurrences. These are explicit errors,
not truncation or a new collision approximation. Exactly 100 is supported.
The source's `>100` processed-triangle check happens after storing an item, so
101 is undefined original behavior and deliberately excluded from equivalence.

`BqHit.position` is the unchanged sphere center or last clear moving endpoint,
not a fabricated surface contact point. Normal, flags, surface, vertex indices,
model provenance, raw record occurrence and winning cell are returned separately.

## Independent proof

`tests/contact_reference.py` extracts and compiles the original routines and
original libultra sine/cosine; native structs are populated directly from model
assets. It never imports production contact code. Host adaptations only widen
pointer-valued `s32`s, provide the explicit static-only world/target context,
instrument observations and detect excluded buffer overflow. Float arithmetic
and control flow remain source-derived. Reference allocation is setup-only;
production performs no allocation.

Compilation uses `-ffp-contract=off -fno-fast-math -fexcess-precision=standard`.
Both `-O0` and `-O2` compare packed float32, identities, counters, mutable inputs
and outputs, query counts and recovery effects, with **no tolerances**. The
production trig subset independently reproduces the original libultra constants.

Frozen `tests/fixtures/camera_contact_golden.json` covers:

- 1,753 primitive cases (1,702 real Spiral Mountain cases): 569 sphere, 404
  moving, 391 gated moving, 389 line; 1,331 hits: 1,068 OPA and 263 XLU.
- 11 correction/counter schedules, 27 updates, including real OPA wall, XLU
  wall and plateau; successful and failed fifth-hit recovery.
- Tangent/near-tangent, edge/vertex, flags, two-sided normals, radius gate below/
  equal/above, endpoint-overlap failure, grid boundaries, repeated occurrences,
  local order, extended line subtraction and non-executed counter preservation.
- Shared moving endpoint witness: startX=50/endX=15, OPA planeX=0 and XLU
  planeX=10. Shared processing ends at **45.078125**, versus **45.625** if XLU
  incorrectly starts from the original endpoint.
- Duplicate-cell witness sums (2,0,1), not a deduplicated (1,0,1), and returns
  occurrence2/cell1. Overflow tests are explicit domain checks, not goldens for UB.

Canonical packing: primitive `>i6f8i` (result, endpoint, normal, identity);
update `>i6fI6f8I9f` (result, previous/camera, state, trace). No C padding is hashed.

| Stream | SHA256 |
| --- | --- |
| Primitive inputs | `3a3a0b976f099d8c4ab693094726f2e2137c1c7afc48e43887501999c23e11ef` |
| Primitive outputs | `273b6efcc0eceff46bdba69655319a0f1ae06c3cd0a7cda7004ddb0316daacac` |
| Correction/counter outputs | `300fd206b37b2d81853966180582c9579177442a06d8a4e8cec608236102f421` |

## Costs (ARM, -O2, existing floating-point/warning flags)

- Existing immutable packets unchanged: OPA143,964 + XLU14,580 = **158,544 bytes**.
  No extra packet/copy/cache. Two existing ARM BqModel views are 72 bytes total.
- Caller-owned reusable scratch: **8,000 bytes** (100 × 80); logical persistent
  state **28 bytes**, observer/output trace **68 bytes**. Accumulator fields can
  eventually come from existing camera state; not integrated here.
- Contact object: `.text` **8,772**, `.rodata` **44**, `.data/.bss` **0 bytes**.
  Existing segment code is a dependency, not a new duplicate.
- GCC `-fstack-usage`: largest individual contact frame 328 bytes (`bc_state_b`).
  Conservative composed C call-chain maximum **1,136 bytes**, excluding caller
  storage and C-library internals: 328+192+96+112+288+32+88. Do not place the
  separate 8,000-byte scratch on a small per-query stack.
- No malloc/calloc/realloc/free in production or its undefined-symbol list.
- **Current viewer binary/RAM impact: zero**; Makefile, main, generated data and
  existing built ELF/3DSX remain untouched. No hardware performance claim.

Run the new proof with `python -B -m unittest discover -s tools/banjo3ds/tests
-p test_camera_contact.py -v`, and the complete suite without `-p`.
