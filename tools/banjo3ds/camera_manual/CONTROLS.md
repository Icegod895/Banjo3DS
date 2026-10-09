# M4.10D-D: native controls, pending hardware acceptance

Starting checkpoint: `e0a372bd`. Only the physical-input boundary is new.
`camera_manual`, camera runtime, query/contact math, player physics, bridge,
projection, culling and generated data are unchanged.

## Exact mapping in normal builds

| Logical input | Physical 3DS source | Current consumer |
|---|---|---|
| N64 R | X without shoulder R | Proven held-R camera controller |
| N64 Z | L | None; no crouch/move is implemented |
| C-up | D-pad up / C-stick up / R+X | Logical state only; first-person is unsupported |
| C-down | D-pad down / C-stick down / R+B | Proven zoom-preset edge/cooldown |
| C-left | D-pad left / C-stick left / R+Y | Proven 45° rotation request |
| C-right | D-pad right / C-stick right / R+A | Proven 45° rotation request |
| N64 A | A without shoulder R | Existing jump press-edge |
| N64 B | B without shoulder R | None; no attack/move is implemented |
| Analog movement | Circle Pad | Existing normalization/velocity/player path |
| Exit | START | Existing immediate exit on press |

**Physical shoulder R is only a modifier.** It never generates N64 R.
Unmapped SELECT, ZL/ZR, virtual Circle-Pad directions and libctru's virtual
C-stick key bits are ignored by the translator. D-pad uses `KEY_D*`, not
`KEY_UP/LEFT/...` aliases that also include Circle Pad movement.

Standalone **Y retains D-C movement-intent suppression** (including its existing
jump restriction); airborne gravity and velocity continue under the unchanged
player contract. R+Y is C-left and does **not** suppress movement. No new orbit
or pause behavior is added to the normal camera.

A face button used with shoulder R is consumed until that **face button is
released**. Releasing R while A/B/X/Y remains down cannot suddenly jump, trigger
N64 R or activate Y suppression. R can be pressed around an already-held face
button to start its C chord. Repressing R while the face remains held creates
another deliberate chord; merely releasing R never creates a C press.
This rearming rule is explicit Banjo3DS input policy, not an N64 rule.

## C-stick and merged logical state

`player_input.c` contains integer input translation only. It receives one
physical held-key snapshot and raw signed `hidCstickRead` X/Y per update.
Each C-stick axis has independent Schmitt hysteresis:

- Press positive at `value >= 40`; negative at `value <= -40`.
- Retain positive while `value > 25`; retain negative while `value < -25`.
- Equality at ±25 releases. A strong reversal directly selects the other sign.
- Diagonals produce two directions. Values (30,30) do not initially activate
  either axis: this is a square per-axis deadzone, not a radial mapping.

The 40/25 constants are a documented initial **3DS policy**, not Rare camera
parameters or guaranteed hardware limits. The Circle Pad retains its accepted
radial deadzone 20 and existing normalization; it does not use these constants.
Hardware acceptance must check the C-stick's response on a New 3DS.

D-pad, C-stick and modifier sources are OR-merged **before** held/pressed/released
are derived. Passing a still-held direction between sources generates no new
edge. A real sampled neutral interval followed by a new press does generate an
edge. No repeat timer and no `hidKeysDownRepeat` are used. Simultaneous/opposing
logical C buttons are preserved; Rare's existing left-first/rejection behavior,
zone priority and zoom cooldown resolve them.

The low four logical bits match `BM_R/LEFT/RIGHT/DOWN` (compile-time checked).
C-up, Z, A, B and START are distinct additional logical bits, not N64 wire data.
Only the supported low four bits are passed to `cameraRuntimeManualInput`.
Thus unsupported C-up cannot invalidate `bm_update` or silently become N64 R.

## SDK evidence and update order

Installed libctru headers:

- `include/3ds/services/hid.h`: physical `KEY_*` assignments, separate `KEY_D*`
  and virtual Circle Pad/C-stick bits, signed `circlePosition {s16 dx,dy}`.
- `include/3ds/services/irrst.h`: `hidCstickRead` aliases `irrstCstickRead`.

Inspection of the installed `libctru.a` confirms `hidInit` conditionally invokes
IRRST via `hidShouldUseIrrst`/`APT_CheckNew3DS`; `hidScanInput` calls
`irrstScanInput`. The latter returns early when uninitialized. `irrstCstickRead`
copies the cached packed coordinates; its static cache is initially zero.
No extra IRRST initialization, scan, or service lifecycle is added. Old 3DS
uses the D-pad and modifier alternatives. No Circle Pad Pro support is claimed.

The live order remains: scan HID → START check → unchanged debug-only update →
translate held keys/C-stick → submit logical camera input → movement basis from
**previous visible viewport yaw** → existing player/body/floor/camera update →
bridge publication → render. No camera state or viewport calculation is moved.

Normal builds do not invoke old X reset, D-pad pan or L/R zoom controls.
`BANJO3DS_DEBUG_CAMERA=1` deliberately keeps its accepted raw A/Y/debug controls
and submits neutral manual input. That diagnostic mode has a different mapping;
this milestone does not remove it or make a runtime toggle.

`PlayerInputState` is zero-initialized once with the viewer. Button history is
not reset by jumps, zone changes or diagnostic void recovery. There is no new
save state, gameplay input subsystem or physics consumer for Z/B/C-up.

## Host proof

`test_player_input.py` covers every source/mapping, press/hold/release, all 1,024
combinations of ten relevant physical buttons, modifier order/rearming, source
handover, diagonals/opposing directions, exact thresholds and jitter. All
65,536 signed axis values are checked for each prior polarity at both `-O0`
and `-O2`. The frame struct's C padding is not serialized or compared; semantic
integer/boolean fields are compared exactly.

`test_player_input_runtime.py` feeds all 43 frozen manual-camera histories
through D-pad, C-stick and modifier adapters into the actual runtime. Logical
N64 R+C combinations use X plus D-pad/C-stick because shoulder R consumes X.
Opposing C-stick directions require a second physical source. This explicitly
respects the hardware mapping instead of inventing impossible C-stick states.

Each source yields the original **7,360-frame** packed camera/viewport stream at
both optimization levels: **22,080 updates per optimization level**, identical
SHA256 `091e285b262b4d1fbcaf4450fabc37baa3dd58da3b45a324e498a537e85d4a6f`.
The oracle is the existing compiled original decomp, not the input translator.
It covers zone priority/overlap, node38, transitions/interruption, C gating,
zoom cooldown, R convergence and obstruction variants.

Another 1,440 paired runtime frames per optimization level compare translated
neutral camera input with D-C raw A/Y behavior, including jump/hold, Y suppression,
C-stick center noise, unused Z/B/C-up, wall/ledge/slope/bridge starts and both
published bridge configurations. Player, floor, body, bridge, camera/viewport
and view matrix match exactly. Real runtime tests separately prove R+A cannot
jump or turn into a jump on R release, and R+Y does not suppress player intent.

The old D-C source assertion requiring *literal neutral input in normal builds*
is intentionally replaced by a check for translated input with neutral **debug**
input. Its mathematical/history goldens are unchanged.

Full host suite: **395 tests; 389 passed, six existing historical skips**.
All eleven new tests pass at both host optimization levels. Both normal bridge
configuration rebuilds and the isolated ARM object compile are warning-clean
with `-Wall -Wextra -Werror`. Diff/cached checks and new-file whitespace checks
are clean. All twenty protected fixture/generated-header files retain their
pre-task hashes. No existing golden was regenerated.

Renderer invariants remain 12,600 vertices, 97 textures, 469 materials,
510 draws (436 OPA → 28 Banjo → 46 XLU), 36 geo-nodes, four SORT nodes,
and a 28,022-byte pose packet. Generated-model SHA256 remains
`4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`.

Changed/new files: `platform/3ds/source/main.c`, `player_input.c/.h`;
`tools/banjo3ds/tests/test_camera_runtime.py`, `test_camera_manual_runtime.py`,
`test_player_input.py`, `test_player_input_runtime.py`; this document and the
manual-camera README link. Nothing is staged, committed or pushed.

## Measured costs

Existing ARMv6K `-O2` hard-float, warnings-as-errors. Normal Rare-camera builds
were forced for both bridge inputs; the final artifact is abilities `0x9DB1`.

| Measure | D-C normal/full | D-D normal/full | Delta |
|---|---:|---:|---:|
| `.text` | 169,008 | 169,952 | +944 |
| `.rodata` | 1,736,860 | 1,736,860 | 0 |
| `.data` | 50,148 | 50,148 | 0 |
| `.bss` | 49,072 | 49,080 | +8 |
| ELF including debug data | 3,629,072 | 3,637,012 | +7,940 |
| `.3dsx` | 1,972,020 | 1,972,968 | +948 |

Tutorial D-D: `.text` 169,944, ELF 3,637,008, `.3dsx` 1,972,960; other listed
sections equal the full configuration. Compiler layout accounts for the small
configuration difference. `PlayerInputState` itself is **12 bytes**; linker
padding absorbs four bytes of the added BSS. `CameraRuntime` and `PlayerRuntime`
remain 30,520 and 42,644 bytes. Collision/query scratch is unchanged.

`PlayerInputFrame` is 20 transient bytes. Compiler own stackframes: translator
**40 bytes**, main **344 versus 320 bytes** (+24). These are not hardware stack
high-water measurements. Translator object `.text` is 880 bytes, `.data/.bss`
zero; the persistent instance belongs to main. No heap, packet copy, new
collision storage, float math or per-frame service allocation is introduced.

## Hardware acceptance checklist

1. Verify plateau start, four movement directions, 500-unit/s movement, jump,
   landing and both bridge states still match D-C. START must still exit.
2. In a **free-B area**, hold/release X: original R convergence/viewport blend.
   Test D-pad left/right press, hold and re-press: no repeated 45° requests.
3. Repeat directions and diagonals with the New 3DS C-stick. Center jitter must
   not press buttons; easing back through hysteresis must not repeat requests.
4. Hold a direction while passing between D-pad, C-stick and R chord; no extra
   camera step while the merged direction remains held.
5. Shoulder R+A must rotate without jumping; release R while A stays down:
   still no jump. Release A, press again: normal jump. Repeat with R+X: it must
   not start a new R action. An already-running R action may finish convergence.
6. R+Y rotates without suppressing movement. Standalone Y still suppresses it.
   After R+Y, release Y before testing standalone suppression again.
7. Wait at least the original initial 0.5s timer, then test C-down using all
   three sources. Hold must not cycle repeatedly; respect the original 0.4s
   cooldown for re-presses. Test node38's distinct profiles.
8. Enter/leave zoom zones during requests. Their original priority may reject
   or interrupt manual control; the plateau's zoom zone is not a free-B test.
9. Confirm L/Z, B and C-up have no new gameplay effect. In particular R+B does
   not attack and R+X does not invoke first-person (still outside scope).

Hardware acceptance and any subsequent input-policy adjustment remain separate.
No new camera math, tuning, gameplay moves or physical-device behavior is claimed
beyond the software contract tested here.
