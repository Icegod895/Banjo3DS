# M4.11-B crouch host reference

Isolated transcription of original crouch selection, coast, yaw, and animation
control. The 3DS runtime calls this module for crouch. `crouch.c` still does
not sample bones or play attacks. Attacks, flap flip, beak barge, and Talon
Trot remain request ids only.

`python3 -B -m unittest discover -s tools/banjo3ds/tests -p test_crouch.py -v`

The oracle compiles the original function bodies. Production is compared with
that oracle at `-O0` and `-O2`. `zone_position` is accepted and unused: the
walk speed map stays in the caller, which passes `target_speed`.

## Not independently verified

- The `ml_acosf` sine table is filled with host `sinf`, not the libultra polynomial.
- `anctrl_setDuration` anti-tamper is forced passing, so durations do not gain 3 seconds.
- Bone poses for clips `0001`, `010C`, and `0116` are not sampled, and the B3P3 packet is unchanged.
- Surface-sfx sample ids and puff particle parameters are call counts only.
- Previous-state end methods are not run. Stand end touches appendages, eyes, and fidget disarm; fast-walk end touches pitch and roll.
- Non-idle destinations do not run their init, and that frame does not advance yaw or animation.
- `func_8029CA94` clearing `BA_FLAG_F` has no crouch output. Flags are reread from the input.
- First-person, transform, and drone requests use normal Banjo's `BS_98_WALK_DRONE` (`D_80364650[6]`).
- Gait zone changes and `func_802B6D00` are caller inputs, not recomputed here.
