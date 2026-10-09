#ifndef BANJO_PLAYER_CROUCH_H
#define BANJO_PLAYER_CROUCH_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "player_runtime.h"
#include "../../../tools/banjo3ds/crouch/crouch.h"
/* Native crouch integration. The Rare machine in crouch.c owns selection,
 * coast, facing and animation phase. This file supplies buttons, the locked
 * horizontal response, and v5 pose sampling. Attacks, Talon Trot, flap flip,
 * beak barge, eggs and wonderwing stay requests. */
void playerCrouchInstall(void);
void playerCrouchSetAbilities(uint32_t mask);
void playerCrouchReset(float yaw);
void playerCrouchFrame(PlayerRuntime *s, uint32_t logical_held, int fp_blocked);
bool playerCrouchActive(void);
/* 1 when this frame's crouch enter or step raised sfx_count. Otherwise 0. */
int playerCrouchSlideSfx(void);
int playerCrouchRequested(void);
int playerCrouchState(void);
void playerCrouchCopy(CrouchView *out);
/* Prefix is the unchanged 28022-byte v4 packet. Clips are raw 0001, 010C, 0116.
 * Writes one 36994-byte v5 packet and returns that size, or 0. */
size_t playerCrouchActivate(uint8_t *out, size_t cap,
    const uint8_t *prefix, size_t prefix_len,
    const uint8_t *enter, size_t enter_len,
    const uint8_t *turn, size_t turn_len,
    const uint8_t *noinput, size_t noinput_len);
#endif
