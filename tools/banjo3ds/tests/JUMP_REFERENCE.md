# M4.6B jump contract (host-only checkpoint)

Historical checkpoint description: M4.6C subsequently connects these proven
modules through `platform/3ds/source/player_runtime.c`, using packet v4.
References below to an unchanged v3 viewer describe M4.6B, not M4.6C.

Nothing in this layer is connected to main.c, the generated viewer header,
movement.c, the live gait controller or the 3DS Makefile.

## Independent animation oracle

`jump_reference.py` imports NO production animation/exporter code. It parses
0008 itself and uses the existing original-C channel, quaternion, blend and
matrix oracle, followed by the independent geo/RSP traversal. Normative snapshots
are frozen in `fixtures/jump_golden.json`; tests never rewrite that file.

Asset SHA256: `b4984d8cfe4aed530a7fb1d62221619b1babac4f79c1697aa85d71ea4847f7e8`.
1788 bytes, frame range 0..45, 35 channels, 410 keys. Samples include 0, .3,
.3+2^-20, .4, .5042, .6, .6667, .75, 1-2^-20, 1-2^-24 and 1, converted to
float32. The exact inclusive endpoint 1 is NOT remapped to 0; their poses differ.

Each snapshot hashes 109 transforms (`>10f`, XYZW/scale/translation), 60 original
row-major matrices (`>16f`, before RSP fixed-point quantization), 723 transformed
loadpositions (`>3f`) and 2085 corners (`>3f`, triangle order). The independent
traversal asserts 49 calls, 723 loads and 695 triangles for every snapshot.

Transitions cover 006F/0003 -> 0008 and 0008 -> 006F/0003, plus an interrupted
idle->jump blend returning to locomotion. Source VALUES are frozen; destination
phase advances. Factors 0/1 copy exact endpoints; intermediate math uses the
original Rare blend/acos/sine reference without added normalization. Production
samples, matrices, loads and corners match every frozen hash at host -O0/-O2.

## Packet / animation state

`export_jump_packet` produces B3P3 v4, 28022 bytes: v3 payload unchanged, header
version changed, canonical 1788-byte 0008 appended. Viewer still exports v3,
26234 bytes. Existing clips have byte-identical evaluated output under v3/v4.
No interpolation or skeletal math changed; only packet validation/descriptor.

`BanjoJumpAnimation` uses 21256 bytes on the tested host/ARM layout: existing
16876-byte pose, 4360-byte frozen source, phase/factor/duration/transition, fixed-width clip,
segment and alignment. No allocation or new pose workspace. `BanjoJumpMotion`
is 36 bytes including actor position/yaw, vy, last-safe position and two flags.
These separate modules can later be connected through TAKEOFF/LANDED/RECOVERED
events; tests exercise a complete plateau jump/contact/return-to-idle sequence.
No live actor currently allocates either new state.

Jump begins at .3, end .5042, duration 1.9, transition .134. On strict phase>end
clamp to end, change duration to 4 and next end to .6667. After that clamp, hold.
No remainder time carries across a subrange and no phase wrapping occurs.
This is the explicit minimal port controller, not the full Rare state machine
(original anchors: bs/jump.c:57-63,108-112; anctrl.c:65-96).

Actual contact invokes nominal existing gait selection using accepted ground
movement: destination starts at zero, transition .2 from the actual mixed jump
pose. Existing gait durations remain authoritative. No landing lock, anticipatory
landing animation, fall clip, variable jump height, events or Rare abilities.

## Physics / collision policy

- A jump request is an edge. A grounded flag alone is insufficient: rerun the
  existing floor query at current X/Z, then require height difference <= .01.
  This explicit contact tolerance is NOT a +/-30 airborne snap allowance.
- vy=710; gravity=-1350; terminal=-4000; dt clamped to .05. Update vy first,
  then candidate position with that updated velocity (semi-implicit Euler).
- Reuse the existing normalization, yaw-only direction and 150 speed. Grounded
  movement delegates to the unchanged movementUpdate. Air movement never calls
  its floor-following/rejection path. Camera mode or horizontalAllowed=false
  suppress only X/Z; they never cancel gravity or contact detection.
- Sweep the entire previous->candidate foot segment, not just a vertical ray at
  the final X/Z. Require decreasing Y, valid upward floor normal, start on/above
  the plane and end on/below, and strictly decreasing signed plane distance.
- Rejectmask 0x005E0000, normalY/length >= .432. With 0x10000, orient a reverse
  normal upward before testing. Degenerate triangles are ignored.
- Triangle edges/vertices are inclusive. Earliest segment fraction wins; exact
  equal fractions retain the lowest exported triangle index. No invented edge
  epsilon. Landing reconstructs floor Y, sets vy=0 and grounded=true; discard
  remaining movement. An ascending t=0 contact cannot land.
- No floor: remain airborne. No moving actors, walls, head or player volume.
- Diagnostic void policy: Y < -1004 (-504 measured scene minimum minus 500)
  restores lastSafeGroundPosition ONLY if previously confirmed and still valid.
  Equality does not recover. Missing/invalid safe floor leaves airborne state.
  This is Banjo3DS policy, not Rare's void/respawn behavior.

The sweep is exact for the tested discrete motion segment, not a continuous
parabolic volume simulation. Abrupt unsupported floor removal, water, slope
sliding and camera/player interactions beyond input suppression remain outside
this contract. No map data or flags were filtered out or regenerated.

## Validation

`test_jump_reference.py`: independent frozen oracle/endpoints/interruption.
`test_jump.py`: both host optimization levels, production four-stream hashes,
subrange clock, landing handoff, unchanged legacy packets, and static collision
cases including real Spiral Mountain plateau, thin/stacked floors, edge/vertex
ties, large descent, rejection flags, slopes, reversed winding, dt cap, camera
input, invalid support and diagnostic recovery.
