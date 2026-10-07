# M4.9D.3A: sparse bridge movement provenance

This supplies data for a later player collision overlay. It does not install
that overlay or change the current runtime behavior: the D.3 hardware bug is
still present until that integration is implemented.

## Identity chain

`floor_collision.collision_models()` now exposes the existing host-side layout
step used by `scene_collision()`: source records deduplicated by the complete
ordered `(a, b, c, surface, flags)` tuple, sorted used source vertex IDs, their
global movement remap, and the model's global triangle base. This shares the
actual export computation; it is not a separately guessed copy of the remap.
The generated collision format and data are unchanged.

`movement_binding.provenance(opa, xlu)` reads mesh membership directly from the
14D0 mesh list. Only mesh IDs 497/498/499 select the scope. No observed movement
vertex or triangle number, source vertex range, coordinate value, or measured
count is an authoritative implementation input.

For each source mesh vertex, the actual export remap supplies either a movement
vertex ID or an explicit exclusion. Selected deduplicated records supply the
movement triangle ID, original ordered corner IDs, remapped corners, surface
and flags. Each selected raw record in each original cell is linked back by its
complete record identity to that movement triangle. Duplicate occurrences are
retained in the audit in original cell/local order.

The resulting canonical values, asserted only in tests:

| Mesh / BridgeState slot | Original 14D0 IDs | Movement IDs | Movement triangles | Raw occurrences |
| --- | --- | --- | --- | --- |
| 497 / 0 | 134–137 | 4346–4349 | 3040–3041 | 119–120, 153–154 |
| 498 / 1 | 150–165 | none | none | none |
| 499 / 2 | 138–149 | 4350–4361 | 3042–3049 | 121–128, 155–162 |

All indices are zero-based. The occurrences belong to 14D0 cells 17 and 18.
They resolve to ten unique movement triangles and sixteen movement vertices.
All sixteen source vertices of mesh 498 are explicitly listed as excluded in
the audit. Original vertices 138 and 150 have identical XYZ but different mesh
identity, demonstrating why coordinate matching would be incorrect.

## Separate generated artifacts

From the repository root:

```sh
.venv/bin/python -B -m tools.banjo3ds.bridge_state.movement_binding \
  assets/model/14CF.model.bin assets/model/14D0.model.bin \
  platform/3ds/build/generated_bridge_movement.h \
  platform/3ds/build/generated_bridge_movement.json
```

No Makefile or runtime includes this output yet. Both artifacts are generated
in the existing ignored build directory; the generator/tests are source files.

The C header contains only a `uint16_t[16][3]` binding. Columns are:

1. global movement vertex index;
2. original 14D0 vertex index;
3. slot in the existing `BridgeState.mesh` array (0/1/2 = 497/498/499).

The eventual consumer can choose the correct existing mesh offset from this
slot. No Y offsets, alternate ability policy or second bridge state are added.
Version/count macros and source/export hashes in comments document the exact
dataset without adding resident strings. JSON is the host-side audit, including
the absent mesh, all triangle identities and every occurrence. It is not runtime
collision data and contains no copied map XYZ.

| Artifact | Exact size | SHA256 |
| --- | ---: | --- |
| Header text | 1,518 bytes | `e59a6a7fb4daccdb2f8b95c98e3c42d89a5aae79a40e6dab9f97ea022e3a353a` |
| Audit JSON | 8,681 bytes | `c910350c4661645eb20f159b593ea0acf3d8fed3a33203f7347a851d5bf994d7` |
| C array payload | 96 bytes, alignment 2, no padding | not linked yet |

Runtime RAM, stack and binary growth in D.3A are **zero**. There are no runtime
C/build changes and no forced 3DS rebuild. `generated_model.h`, existing camera
data, bridge render binding, ELF and 3DSX remain unchanged.

## Independent proof and guards

The test-only reader parses original mesh/vertex/cell/record blocks independently
of `floor_collision.py` and the binding generator. It retains first-record and
source-index identity while constructing the expected sparse mapping.

Tests cover the complete chain, including winding/surface/flags and all twenty
occurrences. Two counterfactual asset variants reject hardcoded output-index or
coordinate-based approaches:

- adding a referenced OPA vertex and unique record shifts both XLU export bases;
- permuting 14D0 source vertex IDs in records, meshes and vertex storage preserves
  physical geometry while changing the required provenance.

Unchanged `movement.c` is compiled at host `-O0` and `-O2`. Its actual floor rules
accept precisely **3042–3045** among the ten mapped triangles. Mesh 497 is vertical;
the four lower mesh-499 triangles have reversed winding and fail the existing
normal rule. No floor flags, threshold, sampling or stepping rule is changed.

CLI generation is repeated and compared byte-for-byte. Host C compilation checks
the 96-byte payload with `sizeof`. The existing collision-export text retains:

`0199b14f719357a42ae0ab61d3bfebd4705db9418e79ff8699521130b5e405c7`

The existing `generated_model.h` retains:

`4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`

This step does not connect movement, jump or floor-following to `BridgeState`.
