# M4.4B: independent 006F / 0003 transition reference

Only test code and a golden fixture are added. Production, viewer, packet,
geometry selection and existing fixtures remain unchanged.

## Source contract and independence

`transition_reference.py` extracts the original functions at test time:

- `src/core2/code_B3580.c:64`: boneTransformList_interpolate.
- `src/core2/code_BE2C0.c:88,133`: SLERP and shortest-sign selection.
- `src/core1/ml.c:13,37`: lookup table and ml_acosf_deg.
- `src/core2/anctrl.c:9,22`: blend-factor/time advancement.

It reuses the independent original-C channel/matrix and geo/RSP references,
not production animation, exporter, binding or decoder code. Original libultra
sine, float/double expression boundaries and disabled FP contraction are
preserved. Both -O0 and -O2 must reproduce the same frozen hashes.

Translation and scale use `source + (destination-source)*factor` in float32.
Identical quaternion components copy directly. Otherwise shortest-sign
selection compares squared lengths of (source-destination) and
(source+destination), using <= for the unchanged-sign case. The original
SLERP uses its original 0.00001 thresholds and sine-zero/near-equal linear
fallback. There is no post-blend normalization.

## Resolved acos lookup memory

The source declares 90 entries, but the algorithm starts lowerIdx at 91 and
can read index 90. Do not replace this with host acos or a theoretical table.
The original decompressed US 1.0 ROM supplies the missing memory evidence:

- core1 mapping: `decompressed.us.v10.yaml:143`, ROM 0xf19250, VRAM 0x8023da20.
- table symbol: `build/us.v10/banjo.us.v10.map`, VRAM 0x80276cbc.
- original ROM offset 0xf524ec; first 360 bytes match the declared 90 floats.
- following words at 0xf52654 and 0xf52658 are both 00000000.
- SHA256 of 368 observed bytes:
  `8f26f71954c2aa61fe69082169b66ecc440395f9b186a1d74848828d12c8bb74`.
- decompressed ROM SHA256:
  `8b7289cf26bf64035fccff51df17a43a8dca02e03264186cca069099454caec9`.

The helper instruments accesses, retaining original comparisons/arithmetic,
but models those observed words safely instead of performing host C undefined
array overreads. Access outside the 92 observed words is rejected. A test
verifies the original bytes when the local decompressed ROM is available;
it does not require distributing that ROM. Real idle phase .625 exercises
index 90. At exactly dot=0, the original upperIdx==90 branch returns 0
**degrees**; its sine-zero fallback becomes linear. This oddity is preserved,
not corrected or normalized. Other selected scenarios reach at most index79.

## Minimal-port controller fixture

- Idle -> walk: freeze idle phase .37; destination 0003 starts phase0,
  duration .6 seconds (the existing full-speed slow-walk duration).
- Walk -> idle: freeze walk phase .625; destination 006F starts phase0,
  duration5.5 seconds.
- Tail-lookup case: freeze idle phase .625 -> walk phase0.
- Interruption: interrupt the first case after three .025-second updates
  (factor .375); freeze that mixed pose and start destination idle at phase0.

These source sample times are diagnostic choices, not original spawn/state
entry claims. Transition duration .2 seconds is the original reset default.
Eight dt=.025 updates give factors .125, .25, ..., 1; the initial snapshot
records factor0. Float32 destination phase advances on every update, including
while factor<1. Both destinations loop here as a bounded minimal-port fixture;
the full original stand/appendage/event sequence is intentionally absent.

The source is a copied tuple of VALUES, with no source clip/time in transition
state. Interruptions cannot reevaluate or resume the old clip. Destination
phase continues after factor1; source phase never advances.

### Endpoint distinction

The explicit requested factor0 contract copies the frozen values, preserving
bits including signed zero. For both primary fixture sources, the raw original
blend at factor0 also matches exactly. Intermediate factors use the original
blend routines.

At factor1, use the destination pose at the **current** destination phase.
This matches `code_2240.c:87-92`: original runtime skips interpolation when
factor>=1. Calling the raw blend at factor1 is NOT equivalent bit-for-bit:
the regression demonstrates floating-point subtraction/addition differences.
Shortest-path quaternion sign handling can also change representation. No
endpoint epsilon, renormalization, or forced phase0 is used.

## Golden packing

`fixtures/transition_006f_0003_golden.json` contains 37 snapshots (including
an interruption provenance snapshot), four SHA256 streams per snapshot:

1. Bones0..108, >10f each: quaternion XYZW, scale XYZ, translation XYZ.
2. Matrix records0..59, >16f each, unquantized original Rare row-major order.
3. 723 transformed loadentries, >3f XYZ in G_VTX load order.
4. 2085 trianglecorners, >3f XYZ in canonical traversal order.

No padding. The last two retain the established camera-Z/fixed16.16/local-XYZ
reference semantics. Every geometry evaluation asserts 49 calls, 723 loads
and 695 triangles; invalid cache references already fail independent traversal.
This is not a claim of hardware-exact RSP projection/clipping.

## Performance reconnaissance only

Current production `pose.c:90-103` accepts only 0003, not 006F. Every accepted
0003 update validates all234 keys. Its channel() at line41 then linearly scans
until the applicable interval. A naive multi-clip extension would validate all
2996 idle keys per update; an inspection of actual idle key positions gives
81/840/1516/2221 extra next-key comparisons at phases0/.25/.5/.75 (phase1 uses
end shortcuts). These are operation counts, not measured CPU microseconds.

The original `animationfile.c:111-122` already uses binary interval search.
One-time validation of immutable exported assets plus channel offsets and
binary key search can preserve the same `(int)frame` comparisons, endpoint
branches, flag bits, neighbor knots and all arithmetic. An offset-only channel
directory is324 bytes for idle (81 u32), or512 bytes for idle+walk. Offsets are
not a replacement for keys. No such optimization is implemented here.

## Minimum future state

A frozen109x10-float source costs4360 extra bytes. Destination evaluation can
reuse the existing4360-byte bone array and blend it in place before the usual
60 matrices and723 XYZ are computed. Numeric workspace then grows from16876
to21236 bytes. Additional controller state is a blend factor and destination
clip identity; the existing phase can be reused, with .2 stored as a constant.
Exact struct size depends on the chosen fields/alignment. No second skeleton,
load binding, VBO, source-animation clock or per-vertex blend is necessary.
