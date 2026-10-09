# Canonical 034D / 0003 host pose evaluator

The evaluator was independently validated in M4.3B. M4.3C links this exact
evaluator into the viewer through `platform/3ds/source/walk_animation.c`.
There are no transitions, callbacks, runtime 006F evaluation or movement changes.
The existing 006F static bake remains the idle source.

Export an optional packet (from repository root):

```sh
.venv/bin/python -B -m tools.banjo3ds.pose_binding \
  assets/model/034D.model.bin assets/anim/0003.anim.bin /tmp/banjo-pose.bin
```

`pose_binding.py` accepts only the canonical SHA-verified assets. It captures
raw XYZ and the active **RSP matrix record at G_VTX**, retaining cache entries
across displaylist returns and the CPU/RSP asymmetry of SKINNING. Records are
absolute parent-composed matrices, not a fresh parent multiplication at BONE.
The packet contains 723 used loads and 2085 corner indices in canonical order.
The binding exporter itself does not modify rendered vertices or draw data.

## Packet and memory contract

B3P3 version 1 is big endian, without alignment padding:

| Section | Bytes |
| --- | ---: |
| Header: magic + seven u32 fields | 32 |
| Skeleton translation factor, f32 | 4 |
| 60 skeleton records: pivot XYZ f32, bone s16, parent s16 | 960 |
| 723 loads: raw XYZ s16, matrix record u16 | 5784 |
| 2085 corner load indices, u16 | 4170 |
| Original 0003 animation bytes | 1132 |
| **Total packet** | **12082** |

Matrix record `0xffff` denotes model base. All other records are 0..59.
Skeleton/binding including factor is 10918 bytes. Animation has 47 channels,
234 keys and frame range 0..120. The exporter does not generate a second
copy of channels or matrices in the packet.

Later versions append raw animation bytes and change the version word.
v2 adds 006F, v3 adds 0002 and 000C, and v4 adds 0008 (28022 bytes).
v5 appends crouch clips 0001, 010C and 0116 after the unchanged v4 bytes
and is 36994 bytes. Indices 0..4 remain walk, idle, creep, run and jump.
Indices 5..7 are crouch enter, turn/recovery and no-input. The viewer
export stays on v4; `export_crouch_packet` is the opt-in v5 generator.
Sampling still uses the same channel, quaternion and skeleton path.

Caller-owned `BanjoPose` is 16876 bytes: 4360 bone transforms, 3840 matrices,
8676 posed XYZ. No heap allocations, static mutable state, or global scratch.
The matrices and transforms remain exposed to allow independent validation.
The ARM compiler's `-O2 -fstack-usage` reports 224 bytes for evaluate and
24 for spline: at most 248 bytes of evaluator-owned nested stack for this
build, excluding compiler/libm helper internals and the caller's frame.
Do not treat this as a universal total stack bound or as measured 3DS runtime
performance. Packet plus output workspace is 28958 bytes; the packet can
remain read-only rather than being copied to RAM.

## Numerical contract

Use `-ffp-contract=off -fno-fast-math -fexcess-precision=standard`.
`banjo_pose_evaluate(packet, size, phase, output)` accepts finite normalized
phase **[0,1]**, not elapsed time. It returns false for invalid structure or
phase; output is unspecified after failure. It is a trusted exporter-packet
interface, not an arbitrary animation loader.

The implementation follows `animationfile.c:85` channel selection,
`code_B9770.c:241` Catmull-Rom, `code_BE2C0.c` quaternion conversion,
`mlmtx.c` matrix arithmetic and `code_630D0.c` skeleton composition.
It uses libultra's finite sin/cos polynomial rather than host trig functions.
109 slots reset to identity; Euler evaluation is Roll -> Yaw -> Pitch.

The geometry comparison follows M3.5's existing numerical contract:
float32 absolute matrices; apply diagnostic view Z=-100 before signed-16.16
truncation; affine accumulation with raw integer positions; undo Z=-100;
pack final XYZ as float32. This is reference-compatible local geometry, not
an assertion of bit-exact N64 RSP clipping or projection. Double accumulation
and libultra trig are deliberate; do not replace them with a native float
matrix multiply without reevaluating the contract.

The original loop controller (`anctrl.c:22-39`) computes the fractional part
of timer + dt/duration: exact 1 maps to 0. This evaluator has no clock or
controller. Direct evaluation at 1 also equals 0 for this clip because its
endpoint pose closes. Interpolation still differs immediately before/after
the boundary; there is no epsilon or endpoint snapping.

## Independent tests

`tests/walk_pose_reference.py` uses extracted original C routines and the
independent geo/RSP interpreter. It imports no production evaluator/binding.
`tests/fixtures/walk_0003_golden.json` freezes eight phases with bone and
geometry hashes, bounds and six load samples. Hash formats:

- Bones 0..108: big-endian `>10f`, quaternion XYZW / scale XYZ / translation XYZ.
- Geometry: canonical triangle order, three corners, `>3f` XYZ, no padding.

`test_walk_pose.py` compares all transforms, all matrices, all load positions
and the complete corner stream at `-O0` and `-O2`, with exact packed float32
comparisons. Additional key and midpoint phases exercise both interpolation
paths. Binding is independently checked with symbolic matrix-record tags
and reproduces the existing 006F golden without adding runtime 006F support.
M4.2 full-export byte identity is asserted separately.

## M4.3C viewer integration

The generated header appends the 12082-byte packet; its preceding M4.2 data
remains byte-identical. Only actor vertices [9408,11493) change at runtime,
and only their first three float fields. UV/RGBA and all map data stay intact.

An accepted, nonzero horizontal movement step advances normalized phase by
`dt / duration` and takes the fractional part. Duration follows slow-walk's
original extrapolating map, then its clamp:
`clamp(((speed-80)/70)*(0.6-1.3)+1.3, 0.3, 1.5)` seconds.
Speed is measured from accepted X/Z displacement / frame dt. This retains
M4.2 movement speed; low speeds still use 0003 rather than adding creep.
A rejected step, neutral input or Y-orbit restores the static idle XYZ once
and resets phase to zero. No blend or runtime idle evaluator is involved.

The main loop writes after blocking `C3D_FrameBegin(C3D_FRAME_SYNCDRAW)`,
then flushes the actor's 50040-byte VBO range with `GSPGPU_FlushDataCache`
before drawing. The original constant vertex array supplies idle positions.
There is no second VBO and no write to map vertices.

For hardware profiling, watch these ELF debugger symbols while moving:

- `banjoPoseLastUs`: last evaluator + corner-copy CPU interval, microseconds.
- `banjoPoseMaxUs`: maximum such interval since launch.
- `banjoPoseUpdateCount`: number of measured movement updates.

Timing uses `svcGetSystemTick()` / `CPU_TICKS_PER_USEC`; GPU waiting and
cache flushing are outside the measured interval. No on-device timing has
been measured by the host tests. Validate performance and appearance on 3DS
before considering optimization. Host golden equality is not a substitute
for observing the ARM build's output on the device.
