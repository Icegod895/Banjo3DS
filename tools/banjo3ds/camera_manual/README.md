# M4.10D-B: normal manual camera, host only

This records the D-B checkpoint. The subsequent authorized D-C neutral-input
runtime integration is documented in [RUNTIME.md](RUNTIME.md). The subsequent
D-D physical mapping and input policy are documented in [CONTROLS.md](CONTROLS.md).

No file in the accepted viewer/runtime, camera, zones, contact, player, bridge,
exporter or generated-data path was changed. `camera_manual` is **not** in the
3DS Makefile's source directories. No new hardware button mapping exists.

## Boundary and ownership

`bm_init` creates a cold host instance. `bm_update` receives an already computed
player/floor/terrain sample, dt and VI count, held **logical N64** R/C-left/
C-right/C-down bits, original bainput enable bits 0/1/5, the collider-center
target, existing zone data and borrowed validated B3Q1 OPA/XLU models.

`BmState` owns the internal camera, selector cache/enablebits, B rollback dot
and shared obstruction counter, R and C scalar state, focus-mode selector,
applied distance profile, zoom timer, and the separate visible viewport plus
its transition state. It is NOT reinitialized on zone/manual state changes.
`BmTrace` and the existing 8,000-byte `BcScratch` are caller-owned temporary
storage. There is no heap allocation or copy of collision packets/vertices.
Query failure returns false without committing state/output (scratch is work
storage). Finite normal camera inputs retain the existing camera input domain.

The evaluator privately includes the unchanged accepted camera/contact source
under renamed entry points to reuse its proven math/primitive implementation.
The new orchestration and recovery-variant selection are separate. This keeps
all accepted source files and their viewer objects unchanged; it does not claim
that duplicate, dead private functions belong in a future linked runtime. The
object-size measurements below explicitly include those functions. Shared
private math can be given a link boundary in a separately approved integration.

## Original call order and semantics

| Behavior | Original source |
|---|---|
| Held counter / edge | `src/core1/joy.c:161`, `src/core2/bakey.c:67,75` |
| C edges and individual enables | `src/core2/bainput.c:20–29,60` |
| Timer decrement, stable zone lookup, mode dispatch | `src/core2/code_9BD0.c:242`, `src/core2/batimer.c:18` |
| Zone priority and profile selection | `src/core2/code_9BD0.c:66` |
| R entry, R target refresh, return | `src/core2/code_9BD0.c:182,200`, `src/core2/nc/dynamicCam13.c:20–88` |
| C request gate/retarget, update | `src/core2/nc/dynamicCamA.c:24–157` |
| Gate: extended line then gated moving sphere | `src/core2/nc/dynamicCamera.c:279` |
| R orbit response, C angular/radial response | `src/core2/nc/dynamicCamera.c:716,754,778` |
| Recovery variants and shared counter | `src/core2/nc/dynamicCamera.c:91,135` |
| Viewport transition | `src/core2/code_3B2C0.c:20,33`, `src/core2/nc/dynamicCamera.c:383–390` |

One normal update:

1. Decrement zoom timer once; refresh stable player probe only when stable;
   run original cached zone selection and apply the node/profile.
2. Dispatch camera **mode**. Modes 2, 4, 7 and 9 differ from dynamic **states**
   B, 13, A and 11. A selected zoom node wins over manual input.
3. Process R hold / fresh C edges with the original mode-specific priority.
   Snapshot viewport on R-state initialization, before this frame's lead update.
4. Snapshot previous camera position; update shared forward lead once; execute
   the selected dynamic camera state once. B uses the accepted full contact/
   rollback composition; zoom uses the accepted node evaluator; R/A use their
   original positional, contact and rotational ordering.
5. Copy internal camera position/rotation into visible viewport output; apply
   the R-triggered viewport transition to the copies, never the internal state.

### R, mode 4 / state 0x13

Entry installs position gains 5/8, rotation gains 8/15, focus mode 6, starts the
0.5-second viewport transition, measures the current orbit and zeroes its
angular velocity. Target orbit is normalized **visible player yaw + 180**.
Held R refreshes it; release freezes it until shortest angular error is strictly
less than 4 degrees. The manager then changes mode to 2, still executing one
last state-13 update; B initializes on the following normal update.

Orbit response uses original `802BDB30(800,160,100)`, including signed near-range
mapping, strict overshoot and float/double constants. Radius and Y converge with
`(target-current)*dt*2`. Contact is the proven previous-position sphere / +35
line / gated moving-sphere chain. Obstruction variant **0** executes only after
an effective contact change; successful recovery recomputes R's orbit and clears
its angular velocity. Pitch uses shortest difference times dt*4; yaw is the
fresh look yaw. Stored smoothing accumulators remain distinct from these scalar
R controls and are cleared only by actual recovery.

### C rotation, mode 7 / state 0xA

Fresh enabled left/right edges request -45/+45 degrees. Held C does not repeat.
Left is attempted first; a rejected left permits a right attempt on the same
frame. The request computes radius, current orbit, target, zero angular step,
and clears completion **before** the 9-degree preview gate. Rejection preserves
these request-side writes. It does not clear the radial-step history.

C init is empty: focus mode is inherited. Thus a C request immediately after
zoom exit uses focus mode 1; a request after R inherits mode 6. These are tested,
not normalized to B's focus mode 2.

C update uses the original scalar angular response (50/3) and VI*5 radial
response (.01/.008). Effective contact marks completion. Obstruction always
runs on an active C update, even when contact did not change position: variant
2 for positive remaining angular difference, otherwise variant 3. Recovery
clears the original smoothing accumulators, sets completion and directly sets
look rotation. Ordinary rotation uses dt*4 pitch and old-yaw + shortest yaw
error. A completed A update returns early; the mode manager returns to mode2,
then enters B on the next normal frame. R does not preempt active mode7.

Variants 2/3 test the original 18 angles 0..340 by 20 degrees (negative for 3),
minimum `max(150,distance-100)`. Variant0 tests only 0 degrees, minimum150.
All retain the original shared five-hit counter and miss reset. Candidate
queries retain extended-line/gated-sphere ordering and mutable OPA→XLU endpoints.

### Zoom and zones

C-down is an enabled edge, not held repeat. Initial cooldown is .5s; accepted
cycle resets it to .4s. The original timer decrements before edge evaluation,
with no epsilon. Spiral Mountain's two profiles both have a far preset:

| Profile | Near (radius,height) | Medium | Far |
|---|---|---|---|
| 0 | 550,175 | 850,375 | 1100,675 |
| 1 / node38 | 800,375 | 950,525 | 1100,675 |

Preset cycles 1→2→3→1. Profile application precedes manual input: changing the
preset affects distance on the following update. Zoom nodes suppress manual
requests, preserve shared histories, and stay collision-disabled. Zone exit
performs its final zoom update. Held R may take control next frame; a C edge
ignored inside a zone is not queued. Zoom→zoom replaces node parameters without
resetting smoothing. The R viewport transition can continue across zone entry.

## Independent proof and fixtures

`tests/manual_reference.py` compiles original R/A functions, angle/radial
helpers, mode manager, bainput predicates, bakey edge/held readers, batimer and
viewport transition. It extends only the existing **original-decomp** zone and
contact oracles. No production camera/manual/contact algorithm is imported into
that translation unit. Adapters supply normal dry player inputs, normal held
counter evolution, static map providers and no-op camera audio.

`tests/manual_corpus.py` supplies 43 deterministic histories, **7,360 updates**.
Every update is compared as `>53f13i8I9f`, no padding: internal camera/rotation,
focus, lead, smoothing, stable probe, B/R/C orbits, timer, viewport offset/time/
output, applied profile/gains, rollback history, mode/state/selector identifiers,
completion, obstruction counter, held buttons and primitive/correction observers.
All intermediate frames, not only stored checkpoints, enter each SHA256.

`fixtures/camera_manual_golden.json` is generated solely by this original oracle,
after reference/production comparison. Combined history hash:

`091e285b262b4d1fbcaf4450fabc37baa3dd58da3b45a324e498a537e85d4a6f`

Coverage includes R convergence/release/tracking, angle wraps, C hold/retarget,
failed left+right requests, enable masks, zoom cooldown/hold, profile0/1, jump
stable probe, overlapping zones, zoom interruptions/exits, real-map node11 and
bridge locations, OPA/XLU/shared-wall contacts, recovery variants0/2/3, and failed
18-candidate recovery. Diagnostic disabled-zone cases explicitly change node
**enablebits**, not selector code; collider targets and seeds are explicit inputs.
Separate tests exercise each recovery variant's success/miss/failure at the
five-hit boundary and compare position, accumulators, counters and trace bits.

No-input histories also compare directly to the accepted zone oracle, including
negative rollback history and nonzero obstruction counters. Existing fixtures
are never regenerated by this task. All comparisons require float32 bit equality
on both host -O0 and -O2; no numerical tolerances are introduced.

## Costs and integration boundary

Measured with devkitARM ARMv6K hard-float -O2, function/data sections,
ffp-contract=off, no-fast-math, standard excess precision, -Wall -Wextra -Werror:

| Resource | Bytes |
|---|---:|
| Complete caller-owned BmState | 344 |
| Existing camera + zone + post state included above | 208 |
| Added persistent manual/viewport state | **136** |
| Optional caller-owned BmTrace | 224 |
| Borrowed existing contact scratch | 8,000 |
| Borrowed existing camera angle lookup | 20,002 |
| manual.o `.text` / `.rodata` | 13,060 / 88 |
| contact.o `.text` / `.rodata` | 10,372 / 44 |
| Both objects `.data` / `.bss` | 0 / 0 |
| Largest own ARM frame: bm_update | 992 |
| bm_gate / bm_obstruction frames | 136 / 240 |

Unlinked object total is **23,564 bytes**, including unused renamed private APIs;
it is NOT a measured future ELF/3DSX growth. Existing query/free-B calls add stack
below those frames (for example free-B finish 504+24, segment 104+296+20, moving
query 112+288+32+88). Reserve a measured complete-call-path stack budget during
integration; these per-function figures are not a hardware high-water reading.
No viewer link/build changes were made, so this milestone adds **zero bytes to
the current viewer**, and no runtime heap/collision-copy behavior changes.

The future integration boundary is one controller update in place of the
current automatic zone dispatch, using existing authoritative player/floor/terrain
inputs and the already published borrowed world/bridge providers. It must retain
one shared zone cache, B history/counter and scratch. Rendering must use the
**visible viewport**; source movement uses the previous visible viewport heading
(`src/core2/bastick.c:139`, `src/core1/viewport.c:416`), which must remain distinct
from the current internal camera during a transition. Keep the accepted RH→LH
and culling boundary unchanged. A separately approved 3DS input policy is still
required; no button choice is made here.

## Explicit exclusions

No scripted override/modes 1/8/10/12, underwater, first-person, transformed
players, snap mode, file-select camera, outer scripted viewport transitions,
manual collision heuristics or dynamic actor providers are emulated. This proof
uses static B3Q1 geometry; future bridge/provider routing must use the accepted
coordinate-reader boundary, not a packet copy. Foot/body/floor inputs are supplied
by the existing contracts, not recomputed by this module. No player motion is
simulated or modified by manual input tests.

Focus-mode6's original snapshot/clear arrays D_8037DB48/DB58 have no readers in
the decompiled source; their unused storage is omitted. Normal mode6's actual
focus getter is the same proven lead focus as mode2. Full save/map lifecycle and
gameplay-specific input suppression beyond the explicit enablebits remain outside
this normal-camera host boundary. Audio/event output is outside the pose/state
comparison. No claim is made about hardware runtime cost or acceptance.
