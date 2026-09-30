# M4.8B.8: persistent static-map floor provider

Host-tested, NOT integrated in the viewer. `floor_state.c` consumes borrowed,
validated B3Q1 model descriptors through the unchanged `bq_segment`. It does not
use `movementFloor`, floor-following, actor physics or camera formulas.

## Original state, initialization and lifetime

Primary definitions: `include/structs.h:110`, `src/core2/code_94A20.c:25`.
The N64 object is 0x60 bytes; a native host pointer must not be mistaken for its
32-bit layout. Production uses model ID 0/1/2 (none/OPA/XLU), not a native pointer.
Below, function suffixes name `func_8031...` in code_94A20.c. Constructor writes
all documented initial values; `BA7C` reinitialization changes ONLY mode/count.

| Offset/type | Initial value | Writers | Readers, lifetime and effect |
|---|---|---|---|
| 00 pointer | NULL | BD98/BE58 | C5DC external model getter; retained until next accepted ordinary hit or no-floor reset |
| 04 triangle, 12 bytes | unspecified | BD98 when triangle non-NULL | C5F4 external getter; persists even after no-floor reset, not used by internal classification |
| 10 triangle, 12 bytes | unspecified | BE98 when triangle non-NULL | C5EC external special getter; persists after no-special reset |
| 1C float[3] | zero | C618 before update | query origin and classification; saved as previous at update end; pre-grounding candidate, not final player position |
| 28 float[3] | zero | C44C end | BF08 reads previous Y to extend special-query upper bound; X/Z retained but not internally read |
| 34/38/3C float normal | (0,1,0) | BD98/BE58 | C5AC external getter, caller grounding/steepness; retains previous value in branches not accepting/resetting ordinary result |
| 40 float posX | -9000 | BD98/BE58 | floor_getXPosition, classifier, state2/state4; persistent ordinary floorheight |
| 44 float posY | -10000 | BE98/BEE0 | floor_getYPosition, classifier, special-window queries; persistent special height |
| 48 float posZ | 56 | C608/C5FC | state2 ordinary upper offset; caller resets to56, RBB-specific150 outside Spiral Mountain |
| 4C u32 flags | 0 | BD98/BE58 | C59C external getter; retained ordinary flags (query branches also inspect fresh hit flags) |
| 50 s16 surface | 0 | BD98/BE58 | C5A4 external getter; ordinary surface code |
| 52 s16 | unspecified | no relevant writer | no relevant reader; padding/unused here |
| 54 u32 filter | 0 | C638 before update | ordinary segment filters, normally marker mask0x400000 for this player |
| 58 u8 ordinary valid | 0 | C44C clear, BD98 set, state4 restores5A | getters/classifier; validity is NOT equivalent to a triangle hit |
| 59 u8 special valid | 0 | C44C clear, BE98 set, state4 restores5B/grace | getters/classifier |
| 5A/5B u8 previous valid | 0 | C44C copies58/59 before clearing | state4 restores skipped query's validity; per candidate call, not per frame |
| 5C u8 grace | unspecified | B9B0 entering4 sets1, state4 hit sets1/miss clears | state4 special-query miss grants one valid grace update; always initialized before read |
| 5D u8 countdown | 5 | B9B0 entering1, C44C decrement | repeats initial upward probe for five candidate calls; retained across modes2/3/4 until exhausted |
| 5E u8 mode | 1 | B9B0 | C44C dispatch and initialization; mode0 exists only during constructor |
| 5F u8 | unspecified | no relevant writer | no relevant reader |

For **internal height/state arithmetic alone**, previous X/Z, copied triangle
records, model pointer, stored normal/flags/surface and padding do not feed the
next branch decision. However normals and metadata are public outputs and can
feed the *caller's* next candidate. They are deliberately preserved, rather than
claiming a reduced closed-loop-equivalent object. No speculative field removal.
Original unused storage is canonical zero in snapshots until a meaningful write;
this is not a claim that Rare zero-initialized it.

Production preserves the logical96 bytes plus24 diagnostic bytes for retained
ordinary/special `(role, occurrence, cell)` identities. No-hit resets model and
height but not copied triangle/provenance, matching original record retention.

## Exact update cadence and missing runtime inputs

- `src/core2/bsmethods.c:281` (`func_80295C14`): state/physics update precedes
  `func_80293F0C`, then later orientation/animation work.
- `src/core2/code_C4B0.c:295`: collision modes1/3/4 enter the candidate solver;
  mode5 enters it before climb correction; mode2 skips it. Mode3 can first
  clamp candidate to specialheight-70. Upper offset is normally56.
- `code_C4B0.c:116,167`: `func_80293668` loops at most FIVE times. First candidate
  comes from physics position; later candidates inherit prior collision
  corrections. A long-displacement sweep may modify it BEFORE the floor call.
- `code_C4B0.c:85`: `func_8029350C` sets candidate and marker filter, updates the
  floor object, then applies normalY>=0.432 and grounding/snapping. Thus this
  slope threshold is NOT segment eligibility. Sphere/wall processing follows
  and may generate another candidate/floor call in the same collision update.
- After the solver, other code can restore/correct final actor position without
  rolling back floor history. Teleport/reinitialization can cause extra calls.
- `src/core1/code_0.c:113`: parity is `gGlobalTimer & 1`; it stays identical for
  every candidate call within one game frame. It is not incremented per query.
- `code_C4B0.c:518`: explicit reinitialization invokes BA7C; does not clear
  previous positions/heights/records/validity. New allocation is a full init.

Consequently the API is **one candidate callback**, not `getFloorY(x,z)` and not
`update(finalActorPosition)` once per rendered frame. Grounded/airborne are not
floor-object inputs or mode numbers. Jump/apex/landing affect query candidates;
only original mode classification and query results change floor modes.

Current Banjo3DS does not supply Rare's pre-floor volume-sweep result, iterative
sphere/wall corrections, collision-mode dispatch, marker-dependent mask changes,
or original game-frame parity/lifecycle callbacks. These missing inputs block
an *exact original runtime cadence*, not the independently tested provider.
No substitute cadence is installed here.

## Query/state contract

Source: code_94A20.c:60,88,109,130,160,222,245,289.

- Initial countdown probe: **unsplit** Y-100 to Y+7000, special0xF800FF0F.
  Special hit chooses3; miss chooses2, then that handler executes immediately.
- State2: special query `max(previousY-candidateY,150)+10` to -5. Ordinary
  upper (normally56) to -1300. Special-flag hit (`0x1E0000`) triggers a second
  ordinary query upper to -450 with those bits added to filter. Negative
  ordinary normal without0x10000 triggers a new query from hit-relativeY-1
  to hit-relativeY-1300, also with0x1E0000. See source for acceptance branches.
- State3: +100 to -1300, filter|0x1E0000; accepts nonnegative returned normal.
  Miss/negative normal **retains previous ordinary height**, with validity clear.
  Special query centers on stored specialheight +/-50; then classification.
- State4: if candidateY-floorheight<=120, do both query paths. Otherwise odd
  parity performs ordinary +60 to -390, filter|0x1E0000, restores previous special
  validity. Even parity performs specialheight +/-70, restores previous ordinary
  validity. Special miss can consume exactly one grace; then classification.
- Classifier: no specialvalid ->2; no ordinaryvalid ->4; special below candidate
  ->2; special-floor<-20 ->2; >100 ->4; otherwise3. Equality boundaries retained.
- Split helper only: for abs(endOffset-startOffset)>500, query first500, then
  on miss query from499 to original end. Exactly TWO segments, not recursive
  500-unit stepping; one-unit overlap. Never change this to movement substeps.
- Explicit ordinary no-hit: height=-9000, normal up, modelNULL, flags/surface0,
  **valid=1**. Special no-hit setsheight=-10000, **specialvalid=1**.
- Mode5 is an empty handler in source; no relevant original caller enters it.
  Production preserves dispatch behavior, but no gameplay equivalence claim for
  fabricated mode5 scenarios. Proven reachable corpus modes are1/init,2,3,4.

Ordinary calls go through the world dispatcher (`code_999A0.c:106`); exact special
mask goes directly to map (`code_94A20.c:71`). Here only static-map providers are
registered in the independent harness. Dynamic actors/transformed providers are
explicitly excluded. The actual game actor roster/poses are not simulated, so
these trajectories are not claimed to be unaffected by actors in a running game.
No movement-collision fallback exists. Existing segment bounds/order/filters/
strict crossings/normal semantics are unchanged.

API guards: valid B3Q1 descriptors, finite candidate components within +/-20000,
finite upper within +/-10000, parity0/1, mode1..5. Invalid input/query returns-1
and leaves state unchanged; the existing100-cell query guard is propagated.
These are bounded API protections, not newly attributed Rare gameplay behavior.

## Independent evidence and camera-input acceptance

`tests/floor_state_reference.py` compiles original code_94A20.c directly, plus
original map/triangle routines from the existing independent segment reference.
No production floor/query imports. Host ABI allocation uses sizeof(host struct),
not literal0x60 with an8-byte pointer. Normal-triplet pointer spelling is adapted
for host compiler object-size diagnostics; arithmetic/control flow are unchanged.
Triangle-copy/query observers expose retained provenance and actual query ranges.

`floor_state_golden.json` freezes every normalized full120-byte state, source
hashes, query-stream hashes and reached modes. Packing is explicitly big endian.
The19 schedules include plateau, walking/fullspeed, jump/apex/descent/landing,
129/130/131 thresholds, slopes, edges/void, stacked/special surfaces, negative
normal/two-sided/filter cases, states3/4/parity/grace, split, repeated same-frame
calls and reinitialization. Real14D0 special-surface probes supplement isolated
synthetic state-machine cases; both use the same unchanged original query.

`tests/floor_camera_inputs.py` compiles the CURRENT player runtime into a temporary
host library with observer-only writes immediately before grounded floor-following
or airborne sweep. Six240-frame real-map trajectories feed those observed
candidates separately to original and production floor providers. Original and
production camera calculations then receive the independently compared floorheight
and real camera-terrain query at the current camera position. Camera-input
fixture hashes pack each original camera state as `>22f4i`, followed by the
canonical big-endian120-byte original floor snapshot. Node32 walk/jump/
landing, delayed node32 exit, free-B walk/fullspeed jump/landing are checked.
The source observer does not edit a repository source or change any physics.

**Acceptance boundary:** both suppliers and camera outputs match for these
explicit schedules at-O0/-O2. The test intentionally does NOT assert that one
observed current-runtime candidate equals Rare's full iterative collision cadence.
Stable input uses current grounded state for this host trajectory harness; it is
not a proof of the entire original player_isStable gameplay predicate. Dynamic
collision providers remain absent. Camera mathematics are unchanged.

## Memory and integration status

- Persistent floor provider120 bytes:96 logical +24 diagnostic provenance.
- Two existing B3Q1 descriptors72 ARM bytes; borrowed packet residency158544 bytes
  unchanged. No extra packet/export/header data and no heap allocation per update.
- ARM-O2 floor_state.o text4744 bytes, data/BSS0 (before linking helpers).
- Compiler frames: update416 + query104 + local segment128; existing segment
  chain104+296+8 => summed1056 bytes, excluding libm/memcpy/compiler helpers.
  This is a conservative compiler-frame sum, NOT measured hardware peak RAM.
- Both floor suppliers now exist as host-proven production modules. They are not
  yet a complete Rare-equivalent live camera-input pipeline: exact candidate
  cadence/parity/lifecycle integration remains unresolved as described above.

No viewer, movement, animation, camera-math, query primitive, B3Q1 or generated
header changes. No staging or commit.
