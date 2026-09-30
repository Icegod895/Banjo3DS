# M4.8B.7: static-map segment query

Host-tested production C, not connected to the viewer/build. Input is the
unchanged B3Q1 v1 packet; no movement data, native pointer casts or raw model
files are accepted by the production query. No player floor-state is added.

## Original chain and exact contract

- `src/core2/code_999A0.c:106` dispatches registered world providers. This module
  represents only the static-map provider; actors/dynamic providers are absent.
- `src/core2/mapModel.c:450` invokes `collisionList_intersectLine` on OPA, then
  XLU with OPA's *already shortened* endpoint. XLU replaces the returned result
  only if it hits that remaining segment. Otherwise OPA's hit survives. If XLU
  exists and `(filter & 0x80001F00) == 0x80001F00`, OPA is skipped entirely.
- `src/core2/code_5FD90.c:195,214` truncates start/end coordinates to integers,
  expands bounds by one, and computes float32 direction. Early rejection uses
  `global_norm`: `max <= -radius || radius <= min` on any axis. Despite the
  source's sphere comment, this is the exact axis test, not a new sphere test.
  Stored model min/max bounds are NOT separately read by this routine.
- Original grid selection (`code_5FD90.c:85`) is captured once per model,
  ordered Z/Y/X; negative integer division truncates toward zero then subtracts
  one, also on exact negative multiples. No cell/record deduplication occurs.
- Per triangle: reject `flags & filter`, then triangle AABB against current
  bounds; calculate source-winding cross product. If any component exceeds
  +/-100000, divide all components by 100000 before plane operations.
- Plane crossings are strict (coplanar/start/end on plane rejected), then
  strict `0 < t < 1`. Barycentric edges and vertices are inclusive. No slope
  cutoff or ordinary backface rejection. Flag 0x10000 flips the normal when
  the start is on its negative side. Dominant-axis barycentric calculation and
  all float operation ordering match the original.
- Accepted hits replace endpoint and normalized normal, then recompute bounds
  and direction. Cell selection is NOT rebuilt. Nearest geometric hit normally
  wins, but do not replace this loop with a separate min-t scan: ties and float
  rounding make the mutation/order observable.
- Normal uses original `ml_vec3f_normalize_copy` (`src/core1/ml.c:174`): float
  length-squared, `1.0 / sqrtf(length_squared)` rounded to float, then component
  products. No fast math, reassociation, FMA or invented normal normalization.

`bq_segment` returns 1 on hit, 0 on miss. End and BqHit are untouched on miss.
On hit it reports shortened endpoint/position, normal, model role, raw record
occurrence, last-hit cell, original vertex indices, signed surface and flags.
Occurrence+model identifies the original triangle address without host pointers.
The original stored-triangle debugging side effect (documented unused by the
source) is not exported. There is no hidden mutable global query state.

## Defined-domain guards

Open/validate each borrowed packet once, keeping its bytes immutable and alive.
Endian readers support unaligned buffers. Invalid packet layout is rejected.
Query inputs must be finite and within +/-1e6 (safe integer-bound conversion).
Invalid queries return -1 with no output changes, even if OPA had tentatively
hit before XLU detects an invalid domain.

The original has a fixed 100-pointer active-cell array and no overflow check.
A selection exceeding 100 cells has undefined original behavior. Production
rejects that case, rather than overflowing or claiming an invented original
result. Long multi-cell corpus segments stay within that defined capacity.
The original array is not copied into runtime scratch: fixed initial cell
ranges are enumerated directly, preserving order. Ordinary camera vertical
segments are far smaller. Model descriptors must come from successful bq_open;
start/end/output must not alias.

## Independent reference and evidence

`tests/segment_reference.py` extracts/compiles the original grid, bounds,
intersection, map wrapper, vector normalization, query wrapper and camera
floor function. It imports no production query or packet parser. Original
assets are decoded into native host structs for the original code.

Host-only adaptations: model identity pointer casts use intptr_t; the original
mismatched bool/pointer declaration of func_80245314 is represented as an
explicit non-null comparison in its camera caller. These retain address and
truth semantics. A last-hit-cell observer is inserted after original acceptance.
The reference world dispatcher has only the original static map registered.
Original 100-cell capacity is retained. No intersection math is replaced.

Both reference and production run at -O0 and -O2, with -ffp-contract=off,
-fno-fast-math, -fexcess-precision=standard, -fno-strict-aliasing. All compared
outputs are BIT-EXACT; no tolerances. Six tests cover:

- 4237 deterministic real-asset segment queries: 2518 hits (1839 OPA, 679 XLU),
  1719 misses. Plateau/slopes, source vertices/shared edges, flag classes,
  reversed rays, exact/near endpoints, negative exact padded grid bounds,
  duplicates and randomized multi-cell segments are included.
- 16 explicit minimal OPA/XLU/endpoint/normal/global_norm cases, independently
  supplied as original model blocks and B3Q1 packets. Equal-depth XLU at an
  OPA-shortened endpoint cannot replace that OPA hit; a nearer XLU can.
- 257 real-data camera positions, 219 hits, compared against original camera
  wrapper. Query update path is used (cache early-return flag off).
- Invalid input/capacity guards, unaligned packet bytes, untouched miss/error
  outputs and observable cell102 order sensitivity.

`tests/fixtures/world_segment_golden.json` freezes reference-only outputs,
input/output hashes and original source hashes. Tests never regenerate it.
Output hash packing is `>i6f8i`: hit, endpoint XYZ, normal XYZ, role/raw occurrence/
cell/surface/flags-as-signed-bitpattern/three original indices. On miss normal
and identity retain explicit test sentinels. Camera packing is `>if` hit,height.
Hit position separately must equal the shortened endpoint bit-for-bit.

## Cell102 is now an observable counterexample

Ray: (772.25,2868,-5206) -> (772.25,2568,-5206), filter0.
Original cell102 order (dedup labels 15 -> 3) yields:

- hit (772.25,2768,-5206), raw occurrence62, vertices(3325,3326,3324)
- normal (-0.005202634260058403,0.9040771722793579,0.42733776569366455)

Sorting only that cell by dedup order in a temporary reference asset yields:

- same position, different vertices(3325,3328,3326)
- normal (-0.10927876085042953,0.8855712413787842,0.45146623253822327)

Production always uses the untouched lossless packet and matches original.
The mutated asset exists only in memory; no actual asset is changed.

## Camera adapter

`bq_camera_terrain`: camera+(0,10,0) -> camera+(0,-600,0), mask0x00800000.
Hit returns hitY; only genuine no-hit returns cameraY-600. Invalid is separate
and preserves height. This is the static-world query supplier only, not camera
collision/pushout or the outer camera cache/update policy. No movementFloor use.

## ARM memory/code

ARM ABI (compile-time checked): BqModel=36 bytes, two models=72; BqHit=52 bytes.
No persistent floor/history state or heap allocation. Packets remain read-only,
borrowed: 143964+14580=158544 bytes, unchanged B3Q1 residency if integrated later.
A future 3DS executable would load const packet bytes into application memory;
no GPU/linear allocation or native vertex/triangle copy is required.

-O2 ARM object: text3873 bytes, data0, BSS0, before linker/libm helpers.
Compiler own stack frames: open88, model_query296, bounds8, segment104,
camera_adapter104 bytes. Sum of the adapter->segment->model->bounds frames is
512 bytes, excluding library calls; this is not a measured hardware stack peak.
No performance tuning or viewer build integration is performed.

Player floor-object state/history and its original update cadence still require
independent reconstruction/validation. Dynamic providers, camera pushout and
M4.8C remain outside scope.
