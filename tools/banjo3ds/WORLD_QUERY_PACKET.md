# M4.8B.6 static-map query dataset

This is a second, host-only representation. `floor_collision.py`, movement C,
existing generated model data and viewer behavior are unchanged. No raycast,
player floor-state machine, camera mathematics or collision response is added.

## Source fields and domain

`include/core2/model.h:225,298,310` defines the two preserved blocks. The segment
routine `src/core2/code_5FD90.c:214` reads `BKVertexList.global_norm`, vertex XYZ,
grid min/max, strides, count/scale, cell ranges, triangle indices and flags.
Normals are calculated from source winding; no normal or slope filter is baked
into this representation. Floor wrappers also consume surface (`unk6`), flags
and the identity of the returned model/triangle. Roles, original indices and
raw record offsets preserve static-model identity without storing pointers.

`src/core2/mapModel.c:28,344,364,450` supplies OPA=14CF, XLU=14D0, identity
placement, scale=1. Therefore model and world bounds coincide. The source map
row's separate coarse cube-bound adjustments are not model bounds and are not
read by the segment/floor path; they are not encoded as invented world bounds.
World dispatch can additionally query actors; this dataset represents only
these two static maps, not dynamic collision providers.

All 16 bytes of every original vertex are retained, even though queries need
only XYZ. This avoids a partial layout conversion in the correctness layer.
The vertex header includes min/max, center, local_norm, count and global_norm.
The collision header includes its original two padding bytes. Nothing is
sorted, deduplicated or compacted. Every raw record occurrence is retained,
including occurrences of identical records in different cells.

## B3Q1 v1 binary format

One packet per model. All fields are big-endian, with no implicit native ABI
padding. Header is exactly 64 bytes (`>4sHHIfIIII32s`):

| Offset | Type | Meaning |
|---:|---|---|
| 0 | 4 bytes | `B3Q1` |
| 4 | u16 | version=1 |
| 6 | u16 | role: 0 OPA, 1 XLU |
| 8 | u32 | source asset ID |
| 12 | f32 | world scale=1; zero translation/rotation implicit in v1 |
| 16 | u32 | original vertex-block asset offset |
| 20 | u32 | original collision-block asset offset |
| 24 | u32 | vertex-block byte length |
| 28 | u32 | collision-block byte length |
| 32 | 32 bytes | source asset SHA256 |
| 64 | bytes | original vertex block |
| 64+vertex bytes | bytes | original collision block |

Vertex block: original 24-byte header, then `count` original 16-byte N64 Vtx
records. Original indices refer directly to these records.

Collision block: original 24-byte header, then `geo_count` records `>2h`
(start,count), then `tri_count` records `>4hI` (a,b,c,surface,flags). Each cell's
half-open occurrence range is `[start,start+count)`. Source padding is preserved;
there is no added tail padding. Both real packet lengths are multiples of four.
A future little-endian ARM consumer needs explicit BE readers; casting these
bytes to native structs is incorrect.

Grid coordinates are relative to world origin zero, with original cell scale.
Cell ID is `x + y*y_stride + z*z_stride` after subtracting minimum cell indices.
Original integer coordinate division uses truncation toward zero, then subtracts
one for *every negative coordinate*, including exact negative multiples. It
must not be replaced by a conventional floor-division grid.

## Measurements

| | OPA 14CF | XLU 14D0 |
|---|---:|---:|
| Vertices | 4568 | 672 |
| Model/world min | (-8471,-504,-7780) | (-7797,-500,-4057) |
| Model/world max | (8609,6600,8326) | (5184,2538,6437) |
| global_norm | 10301 | 8888 |
| Grid minimum | (-6,-1,-5) | (-3,-1,-2) |
| Grid maximum | (5,4,5) | (1,0,2) |
| Dimensions | 12 x 6 x 11 | 5 x 2 x 5 |
| Scale | 1600 | 3200 |
| y_stride / z_stride | 12 / 72 | 5 / 10 |
| Cells | 792 | 50 |
| Raw occurrences | 5633 | 293 |
| Unique full records (analysis only) | 2945 | 200 |
| Packet header | 64 | 64 |
| Vertex header | 24 | 24 |
| Vertex records | 73088 | 10752 |
| Collision header incl. 2 source padding bytes | 24 | 24 |
| Cell ranges | 3168 | 200 |
| Triangle occurrences | 67596 | 3516 |
| Total serialized bytes | 143964 | 14580 |

Total: **158544 bytes** (154.828125 KiB). No packets or asset bytes are committed;
CLI output is explicitly directed to a chosen directory, normally `/tmp`.
No viewer RAM/ROM changes occur in this step. If later embedded as const byte
arrays, payload is 158544 bytes plus linker alignment/descriptors. A `.3dsx`
loads read-only data into application memory too: this is not free ROM-only
storage. No separate writable copy, linear/GPU allocation or decoded scratch
layout is specified here. Hex C source would be roughly six characters per
byte (~951264 characters) plus formatting; no C header generator is added.

## Independent proof and hashes

`tests/world_query_reference.py` uses direct integer byte reads from the assets;
it imports no production parser/serializer. It independently constructs the
packet and semantic stream. `fixtures/world_query_golden.json` freezes source,
packet, vertex-block, collision-block and semantic hashes. Tests do not rewrite
these fixtures. Byte equality covers even unused vertex attributes and padding.

Semantic stream: `>HIf` (role,asset,scale), `>23h` (vertex/grid header fields),
all XYZ as `>3h`, then each cell `>I2h` (cell,start,count) followed by each
occurrence `>I4hI` (raw index,a,b,c,surface,flags). No padding or deduplication.
Raw block hashes separately cover all raw records, regardless of cell coverage.
The actual assets' ranges cover each raw occurrence exactly once.

Tests cover every cell and record, empty/boundary cells, duplicates across
cells, shared vertices/edges and both roles. There are 177/9 cells whose local
order differs from first-occurrence deduplicated order. Cell102 explicitly
retains dedup IDs 15 before 3, whose vertices are (3325,3326,3324) and
(3325,3328,3326). These dedup IDs are regression labels, not packet indices.

The existing combined movement-collision text is frozen separately at SHA256
`0199b14f719357a42ae0ab61d3bfebd4705db9418e79ff8699521130b5e405c7`.

## Deliberately narrow traversal sanity layer

`selected_cells` implements only original `collisionList_getIntersecting_s32`
(`code_5FD90.c:85`). Inputs are already integer padded bounds; tests compare an
independent exhaustive grid enumerator, including negative exact multiples,
clamped boundaries and random boxes. `candidates` visits each range in order,
retains role/cell/raw-occurrence identity and applies flag rejection. With the
supported OPA+XLU pair it also preserves map-wrapper OPA skip for
`(mask & 0x80001F00) == 0x80001F00` (`mapModel.c:450`).

This does NOT claim to reproduce a complete ray's dynamically shortened stream.
The original segment loop rejects by global_norm/bounds, shortens its endpoint
on hits and recalculates bounds/direction. XLU then receives the endpoint
possibly shortened by OPA. The new data preserves everything required for that
future static-map kernel, but the helper does not calculate intersections,
normals, shortened endpoints or final hit selection.

Player floor-state history, update call cadence, no-hit/cache behavior and
world actor providers remain separate work. Camera terrain ray and M4.8B input
suppliers are not implemented here.

## Export and validation

From the repository root:

```sh
.venv/bin/python -B -m tools.banjo3ds.world_query_packet assets/model /tmp/banjo-query-packets
.venv/bin/python -B -m unittest discover -s tools/banjo3ds/tests -v
```

No C code is added; host C optimization and ARM compilation are not applicable
to this Python-only export/candidate-order layer.
