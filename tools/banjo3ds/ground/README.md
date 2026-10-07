# M4.9E.1: isolated normal ground-contact / falling phase

This document records the isolated E.1 correctness contract. E.1B now connects
it to the player runtime; see [RUNTIME.md](RUNTIME.md) for that integration.
The formulas and independent E.1 fixtures below remain unchanged.

## Exact boundary, not a replacement collision solver

The source order is `bsmethods.c:func_80295C14`: state update, physics, position,
then `code_C4B0.c:func_80293F0C`. The normal body loop `func_80293668` calls
`func_8029350C` before sphere contact. That floor phase is independently
executable. It does NOT require a body contact to decide ordinary support loss.
The *whole* original update can repeat it up to five times with body-corrected
candidates. This layer does not fabricate those candidates.

Caller order:

1. `bg_state_update`: check PREVIOUS position/floor height, before horizontal
   response/state selection. Return 1 when ordinary locomotion requests FALL.
2. Evaluate existing horizontal physics externally. Pass post-response X/Z
   velocity to `bg_candidate`; never pass intent or accepted displacement.
3. `bg_candidate`: original normal gravity/position arithmetic, including
   float32 candidate-minus-previous for requested displacement.
4. `bg_query_resolve`: existing persistent B3Q1 floor supplier, then original
   floor resolution and ordinary final contact velocity adjustment.

Only the body-free ordinary normal/fall path is modeled. The caller must not
claim this reproduces frames requiring body correction, water-state handling,
the three-frame stuck/forced-ground override, dynamic providers or slide states.
The `falling` member is an entry latch, not a complete animation/landing state
machine. Ground reacquisition is output; no landing animation or gait choice is
made here. A future owner must manage gameplay-state exit explicitly.

## Original numerical contract

- Normal default gravity `-2700.0f`, terminal velocity `-4000.0f`.
- `vy += dt * gravity`, clamp, then multiply velocity by dt and add to position.
  dt is caller-owned; this phase adds no cap or substeps.
- Horizontal velocity is an external input. No speed/response/yaw modification.
- Query: ordinary SM upper=56, marker filter=0x400000, caller frame parity.
  `bq_floor_update` / `bridge_floor_update` preserves all original persistent
  query modes, history, filters, >500 splitting and no-hit height -9000.
  Six stationary query calls in fixtures establish diagnostic starting history;
  they are not a proposed runtime spawn cadence.
- Clear grounded before testing the returned normal/height.
- If `!(normalY < 0.432)`, candidateY <= height snaps to height and grounds.
- Otherwise downward follow requires previous grounded AND requestedDY < 0.
  If `normalY < 0.9`, candidateY must be strictly < height+30; otherwise < height+5.
- 0.432 and 0.9 are original **double literals**, not float replacements. In
  particular float32(0.9) is below the original 0.9 comparison boundary.
- No general normal filter in the segment query itself. Surface may be returned
  and then rejected for grounding. X/Z never changes in this isolated phase.
- On confirmed ordinary contact, negative vy becomes -1; nonnegative vy is kept.
- `player_shouldFall`: strict `60.0f < playerY - previousFloorHeight` during the
  state update, not immediately after the new floor query. Source walk/stand
  states can override this request with other moves; those inputs are excluded.
- `bsjump_fall_init` for normal locomotion: asset 00B0, smooth transition enabled,
  transition .3, duration .38, airborne physics type. No velocity assignment or
  jump impulse. Jiggy/backflip special cases are outside this ordinary fixture.
  Switching physics type to AIRBORN itself does not reset velocity/gravity.
- Initialization from another move with a non-default gravity is not supported
  by this normal-ground fixture. The existing jump implementation is untouched.

State-2 floor ranges are normally +56/-1300 plus special queries; state 3 is
+100/-1300 with additional mask; state 4 is +60/-390 with parity/history. These
are the existing independently proven provider, not duplicated in ground.c.
Query errors propagate; they are not converted into an ordinary miss or fall.
Provider domain checks (including +/-20000 finite candidate bounds) remain.

## Independent proof

`tests/ground_reference.py` compiles original decomp floor/segment routines,
`func_8029350C`, `player_shouldFall`, `bsjump_fall_init`, and `baphysics_set_type`.
Candidate math is the verbatim vertical/position tail of
`__baphysics_update_normal`, with already-evaluated X/Z velocity supplied.
Animation calls are recorded, unrelated ordinary-state inputs are fixed, and
host pointer width is adapted. Production code is never imported by the oracle.
Original bridge actor/mesh callbacks generate its published bridge coordinates.

10 real-map schedules / 226 updates plus 224 isolated snap/normal boundary
cases are frozen. Tests compare every byte of phase state/frame and all 120
bytes of persistent floor state (including retained triangle identities), at
-O0 and -O2. Extra checks cover 60-unit transition boundaries, no jump impulse,
terminal velocity, zero dt, reacquisition, both published bridge states and
provider failure. Existing full floor-state tests retain all range/mode coverage.

Fixture packing: phase scalars big-endian `>5f2I12fI` followed by the existing
120-byte canonical little-endian floor snapshot (no pointers, zero padding).
Boundary hash packs raw canonical little-endian State (28 bytes) + Frame (52).
No fixture is constructed from production output.

At the audited plateau ledge, update 0 accepts Z=400.000122, Y=1799.233276,
vy=-46.000004, floor=1468 and clears grounded. Update 1 requests FALL from the
previous >60 separation, then reaches Z=408.333466/Y=1797.716553 with vy=-91.000008.
The transition does not insert a jump or cancel horizontal movement.

The steep and wall schedules are explicitly named LIMITATION. They still pass
through steep surfaces or intrude into the original player-volume boundary:
matching this isolated phase does NOT establish a safe complete collision solver.

## Cost / integration guard

ARM O2, armv6k/hard-float, existing numerical flags, Wall/Wextra/Werror:
- BgState: 28 bytes; BgFrame: 52 bytes caller scratch.
- Persistent floor supplier: existing 120 bytes if a separate instance is needed.
- ground.o .text: 704 bytes; .rodata/.data/.bss: 0 (literals included in .text).
- GCC stack usage: state update 0, candidate 40, resolve 8, query wrapper 32 bytes.
  Add the unchanged floor/query supplier call chain to the wrapper's stack; these
  numbers are not a whole-player stack bound. No heap allocation in this layer.
- E.1 alone had no viewer binary/data change. E.1B links this module; see RUNTIME.md.

The future integration boundary is the current grounded candidate/floor decision,
not horizontal physics or the jump path. Natural ledge falling must be separated
from solid-contact blocking; attaching this phase alone cannot fix the proven
missing player body/volume response. E.1B integrates only this boundary; body response remains absent.
