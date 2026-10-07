# M4.9C: static free-B contact in the normal 3DS camera runtime

`FREE_B.md` and `README.md` record the earlier host-only proof checkpoints.
M4.9C now links their unchanged production algorithms into the normal viewer.
The independent references and frozen camera/contact/free-B goldens are unchanged.

## Runtime boundary

The existing `cameraRuntimeMove()` still runs the B.9 pre-collision candidate
observer, floor bridge and parity/lifecycle exactly once as before. After those
existing inputs and the terrain-floor sample are available, it invokes
`cameraRuntimeUpdateView()` once. This calls the proven `bc_free_b_update()`:
prepare through position smoothing, contact, conditional obstruction/recovery,
rollback, orbit/look recomputation, direct recovery rotation and rotation
smoothing. Contact is never applied after rotation smoothing.

The composition selects its contact branch using the state produced by prepare,
not the state at frame entry. Thus node32's final zoom update on zone exit is
preserved, and first free-B contact occurs only on the actual first B update.
Node32 never executes sphere/line/moving contact. Its flags remain `0x75652082`.

`CameraRuntime` owns persistent `BcFreeBState` (8 bytes) and reusable
`BcScratch` (8,000 bytes). `main.c` already stores the runtime statically.
No new heap allocation, packet copy or triangle cache is introduced. Startup
zero-initializes post-state once; B-entry, node changes, jump/landing, floor
bridge reinitialization and diagnostic void recovery do not reset it.
The unchanged composition retains distinct immutable rollback-previous and
mutable sphere-pushout-previous positions.

Camera, post-state and view commit together after successful finite-view
validation. Unsupported triggers preserve the previous published state. A
contact/query failure remains explicit, with no debug-camera fallback. On error
only, a pure noncommitting prepare probe distinguishes unsupported camera input
from query failure; it runs no contact queries and publishes no extra update.

## Original normal-Banjo obstruction target

The explicit target is `(actor.x, actor.y + 80.0f, actor.z)`, not focus/lead.
Evidence:

- `src/core2/code_7060.c:430`, `func_8028EC64`: obtain the collider offset,
  copy player position, then add that offset to Y.
- `src/core2/code_C4B0.c:248`: the getter returns `D_8037C1F8[0]`.
- `:253–275`: normal initialization sets both current and desired offset to
  **80**, radius to 35, without an initial convergence delay.
- `:312`: subsequent convergence leaves equal current/desired values unchanged.
- Other setters are used by transformations, flying or climbing; the supported
  normal stand/gaits/ordinary jump do not change this value.

This supplies an original camera input without porting player-volume collision.
It is deliberately distinct from diagnostic targets supplied by the B.6 corpus
(some use +60). Future transformations would need their actual collider target;
no approximation for them is included here.

## Proof at the runtime boundary

`test_camera_contact_runtime.py` compares the actual runtime update function
against the original-source B.6 oracle for all **23 schedules / 3,490 frames**,
at both `-O0` and `-O2`. It covers OPA/XLU, no effective change, history rollback,
five-hit counters, failed/successful recovery and subsequent ordinary updates.
Existing frozen B.6 hashes are rechecked, not regenerated.

Every no-effective-contact-change frame is also compared byte-for-byte against
the old contact-free update from the identical starting state. Every node32
frame has zero contact calls and the identical old camera result. Camera input,
view conversion, REVERSED parity, debug NORMAL parity and projection policy are
unchanged.

Eight actual movement/floor/camera trajectories are additionally compared with
the independent original camera using the normal +80 target. A parallel
physics-only runtime proves the entire `PlayerRuntime` remains byte-identical.
The existing B.9 candidate/ordinal/parity, movement and floor assertions remain
active. Its frozen contact-free camera hash is checked via a parallel old-camera
evaluation; it is not redefined to include intentional new contact corrections.

No active viewport transitions, dynamic providers, extra camera modes, player
physics changes or camera tuning are implemented. Only static untransformed
OPA/XLU providers are available. Existing fixed-capacity failures remain errors.
Hardware/Azahar visual acceptance is still pending.

## Validation and measured build impact

Full suite: **294/294 passing**, including host `-O0`/`-O2` integration and
original-source comparisons. Forced build:
`make -B -C platform/3ds BANJO3DS_DEBUG_CAMERA=0`, existing warnings-as-errors,
**zero compiler warnings**. Tracked, cached and new-file whitespace checks pass.

ARM `CameraRuntime`: **20,412 -> 28,420 bytes (+8,008)**, allocated in the
existing static `rareCamera`. Scratch is reused, not allocated on the stack.
Trace (156 bytes) and transactional camera/post/view temporaries are local.
The measured runtime object code grows by 280 bytes; unchanged contact/free-B
objects are now linked. The complete image comparison also includes the
accepted B.6 camera phase refactor, which had not been rebuilt into the prior ELF.

| ELF section | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `.text` | 132,632 | 142,776 | +10,144 |
| `.rodata` | 1,733,580 | 1,733,620 | +40 |
| `.data` | 50,148 | 50,148 | 0 |
| `.bss` | 38,960 | 46,968 | +8,008 |
| `.tbss` | 3,080 | 3,080 | 0 |

`.3dsx`: **1,932,332 -> 1,942,520 bytes (+10,188)**. Debug ELF file size:
3,217,132 -> 3,292,976 (+75,844); debug information is not runtime RAM.

ARM `-fstack-usage`: move frame 136, update-view 480, free-B composition 488,
obstruction/contact branch 328+192+96+112+288+32+88. Conservative combined C
call-chain bound: **2,240 bytes**, excluding main/caller and library/helper
internals. This is a compiler-derived bound, not a hardware high-water reading.
Undefined-symbol audit finds no allocator in runtime/contact/composition.

B3Q1 is borrowed directly from the same resident, four-byte-aligned ELF
`.rodata` symbols. Extracted final-ELF packet bytes retain these SHA256 values:

- OPA (143,964 bytes):
  `59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953`
- XLU (14,580 bytes):
  `500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f`

The forced regeneration leaves `generated_model.h` byte-identical:
`4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c`.
Counts remain 12,600 vertices, 97 textures, 469 materials, 510 draws in
436 OPA -> 28 Banjo -> 46 XLU order, 36 geo-nodes/four SORT nodes and a
28,022-byte posepacket. All existing golden fixture files are unchanged.
