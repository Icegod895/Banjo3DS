# M4.10B: host-only Spiral Mountain camera zones

M4.10B established this layer host-side. M4.10C now connects it through the
existing runtime boundary; see `platform/3ds/CAMERA_ZONES.md`. It selects normal,
dry Banjo's setup zones, supplies their parameters to the existing camera math,
and uses the existing static free-B contact composition. No camera formula,
contact threshold, player collision, bridge publication, projection or culling
rule changes.

## Source contract

- `src/core2/code_A5BC0.c:865`, `__codeA5BC0_initPropPointerForCube`: camera
  props are stored backwards within each loaded cube.
- `src/core2/gccube.c:797,1557`: x-fastest cube storage and linear cube visitation.
  `func_8030688C` (1685) appends to the first intersecting same-node group;
  `__code7AF80_concatElementsAndRemoveEmpty` (1492) merges connected groups and
  compacts empty entries without reordering survivors. Its nonempty enemy-list
  guard is satisfied by the actual setup's 27 enemy-boundary records.
- `gccube.c:1917,1968`: try the cached local trigger, other triggers in that
  group, then the first eligible group. Group history is therefore observable
  in overlaps. A disabled node cannot select any of its triggers.
- `src/core2/code_9290.c:29`: refresh stable query XYZ when stable or explicitly
  requested; otherwise ordinary jumping retains the old position. Convert XYZ
  to signed integers by truncation toward zero. For the supported dry mask 1,
  membership requires `py - 150 < ty <= py + 150` and strictly
  `(px-tx)^2 + (pz-tz)^2 < radius^2`. The vertical limits are asymmetric.
- `src/core2/code_9BD0.c:38,66,182,235,242`: type 4 changes the distance profile;
  type 3 selects state 0x11/mode 9 and reloads zoom parameters. A zoom exit sets
  mode 2 but runs one final state-0x11 update. The next frame initializes B.
  Zoom-to-zoom does not reinitialize smoothing. A zoom selection retains the
  previously selected distance profile; leaving all zones selects profile 0.
- `src/core2/nc/dynamicCam11.c:26,72`: existing zoom evaluation and parameter
  getters. All 27 zoom node payloads in this setup have collision bit 0 clear.
  Node 11 is a zoom node, not free state 0xB.
- `src/core2/code_35520.c:138`: Spiral Mountain profiles 0/1 provide the three
  radius/height pairs. Node 38 selects profile 1. No manual preset cycling is
  implemented here; the caller supplies the existing camera preset 1..3.

The setup contains 150 camera triggers, 26 referenced node IDs, and 27 merged
camera groups. Node 14 has two disconnected groups. There are 107 dry-eligible
triggers (101 zoom triggers plus six node-38 triggers), selecting 24 zoom nodes
and the profile node. The setup also retains water-only/unreferenced payloads;
that does not imply support for water or special player states.

## API and ownership

`setup.read_zones(path)` accepts the existing canonical setup asset and returns
ordered groups plus node payloads. It writes no generated viewer artifact.

`BzData` borrows immutable trigger/group/node arrays. `bz_init` initializes a NEW
`BzState` with every node enabled. It is not a substitute for every original
camera reset: keep this instance across B/zoom changes. `bz_enable` changes one
node's eligibility; `bz_select` performs cached selection alone.

`bz_update` is one host-side transaction. It refreshes the camera's stable
position when requested, selects a node/profile, prepares the camera through
position smoothing, and invokes the unchanged contact/finish composition.
Selection and camera are committed only on success. Invalid input or unsupported
node types fail instead of guessing a different camera mode. Data is trusted
canonical setup output, not an arbitrary unvalidated packet. Pure selection
requires finite, bounded map coordinates.

Ownership/lifetime:

| Owner | State | Lifetime |
|---|---|---|
| BzState | group/local cache, profile, last zoom, node enables | world instance, retained across transitions |
| BanjoCamera | stable XYZ, camera/focus/orbit, position/angular accumulators | existing camera instance |
| BcFreeBState | obstruction counter and previous rollback dot | existing post-contact instance, never aliased with zone state |
| BzData | borrowed ordered setup arrays | immutable world data |
| caller | B3Q1 views, contact scratch, trace, math tables | existing borrowed providers/storage |

`banjo_camera_prepare_selected` extracts the already-existing mathematical body
from the old bounded node32 selector. `bc_free_b_finish_phase` extracts the
already-existing post-prepare contact/finish body. The old public entry points
still perform their old selection/prepare and call these bodies. Their goldens
remain exact. The bridge source-inclusion namespace gains the corresponding
symbol alias; it does not change the overlay algorithm. These are shared source
refactors, not activation of this zone layer in the viewer.

## Independent proof

`tests/zones_reference.py` compiles original decomp group creation/merging,
membership, stable-position logic, mode manager, zoom getters/configuration and
profile-table functions together with the existing ORIGINAL-source camera and
contact oracle. It imports no production camera/zone/contact algorithm.

Host adapters replace N64 pointer widths, setup I/O and unavailable manual/water
state. Decomp's omitted node argument and scalar-as-pointer declarations in zoom
configuration are repaired at the ABI boundary; array-address expressions are
made type-correct. The original prop allocator is compiled and executed to
obtain each cube's reversal. Cube traversal follows the original linear index
formula. Independent Python asset decoding supplies raw records/node fields;
original C creates/merges groups. Setup-time allocation in that oracle is not a
production runtime requirement.

Six test methods compare both `-O0` and `-O2`:

- Exact 150-record/26-node/27-group data, every node field, collision-disabled
  flags and node32's order `11BA, C96, 11FD, 11E9`.
- 4,204 membership probes per optimization: strict radius/Y edges, negative
  fractional truncation, overlaps/history and enable-bit changes.
- 13 deterministic schedules / 1,412 complete updates per optimization,
  covering spawn32, trigger `1542` selecting node11 at the OPA diagnosis,
  profile1 and all three presets, every dry trigger in both traversal
  directions, jumps/landing, zoom replacement, exit/re-entry, and static OPA/XLU
  contact contexts. Contact target input is explicitly player XYZ +80 Y, as
  normal runtime supplies; schedules are camera inputs, not a player-physics
  replay. Static raw B3Q1 is used without inventing bridge/progress state.
- Explicit forced refresh while airborne, frozen stable XYZ, preserved counter
  and negative rollback history during zoom, and retained smoothing across
  zoom-to-zoom replacement.

Every update compares packed big-endian float32/int32 camera state, contact
trace, obstruction/rollback state and group/local/profile/last-zoom fields.
`free_b_corpus.packed` defines the inherited state/trace packing; append `>4i`
for zone state. No tolerance. The JSON freezes per-schedule hashes and transition
checkpoints. Both original-reference optimization levels produce the same file.

Setup SHA256:
`a0531b7207fad05bc8f22569b9c6148b469f9d37df10f71bf68871619180bba2`

Ordered semantic group stream SHA256 (big-endian int32 node/count followed by
XYZ/radius/mask for every local trigger):
`834fdafe8529dbbdd7951674c596d9f981b9beea593bb1ee50937604e657cc9a`

Golden JSON SHA256:
`8fd2fcc2cb94e23a624f96d57aadfa02944f0490552b4a0174545079d51d9d1b`

## Measured costs and limits

ARMv6K GCC `-O2`, hard-float, no fast-math/contraction, warnings-as-errors:

- New persistent selector: **96 bytes**; borrowed-data descriptor: **20 bytes**.
- Immutable typed payload: **6,504 bytes** = 150*24 trigger + 27*12 group +
  43*60 node bytes. This is an estimate for a later C export, not an embedded
  packet/header added by this task. No dynamic copy is required.
- Existing camera 104 bytes, post-contact state 8 bytes, contact scratch 8,000
  bytes and math tables remain borrowed/reused, not duplicated persistently.
- New `zones.o`: `.text` 1,624, `.rodata` 48, `.data/.bss` 0 bytes.
- Shared extraction object deltas: camera +56 bytes, free-B +160 bytes, bridge
  namespace free-B +160 bytes. These are object costs, not a linked `.3dsx`
  size claim; no viewer build is performed.
- Largest new own stackframe: `bz_update` 488 bytes; `bz_select` 64. Shared
  prepare-selected 224, finish-phase implementation 504, camera finish 192
  bytes. These are individual compiler stack-usage results, not a guaranteed
  whole-call-chain bound; original contact/math call depth remains additional.
- No production heap allocation, per-frame packet copy or new collision scratch.

Unsupported: water/flying/climbing/special transformations, manual camera
modes, scripted overrides, active viewport transitions, dynamic providers and
other maps. Caller floor/world inputs retain their existing bounded contracts.
No hardware correctness or wall-sticking cure is claimed from this host proof.
The M4.10B proof itself did not change the viewer. Its subsequently authorized
M4.10C integration is documented separately.

Validation: full Python discovery ran 364 tests successfully (six explicit
skips); the six new zone tests pass at both optimization levels. ARM object
compilation is warning-free with `-Wall -Wextra -Werror`. Existing tracked
fixtures and viewer sources are unchanged. Diff/cached checks and new-file
whitespace checks are clean. No viewer build, staging, commit or push.
