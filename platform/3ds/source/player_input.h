#ifndef BANJO_PLAYER_INPUT_H
#define BANJO_PLAYER_INPUT_H
#include <stdint.h>
#include <stdbool.h>
/* Port-side logical state, NOT an N64 wire-format/controller emulator.
 * The low four bits are the proven BM_* manual-controller interface. */
enum {
    PI_N64_R=1, PI_N64_CLEFT=2, PI_N64_CRIGHT=4, PI_N64_CDOWN=8,
    PI_N64_CUP=16, PI_N64_Z=32, PI_N64_A=64, PI_N64_B=128,
    PI_START=256
};
/* Explicit 3DS presentation/input policy, not Rare constants or calibrated
 * hardware limits. Independent Schmitt axes allow diagonal C buttons. */
enum { PI_CSTICK_PRESS=40, PI_CSTICK_RELEASE=25 };
typedef struct {
    uint32_t held, consumed_faces;
    int8_t cstick_x, cstick_y;
} PlayerInputState;
typedef struct {
    uint32_t held, pressed, released, manual;
    bool jump_pressed, suppress_movement;
} PlayerInputFrame;
/* Zero-init on viewer start. Call once after hidScanInput with physical held
 * keys and raw hidCstickRead dx/dy. No key-repeat or virtual direction bits.
 * Merge sources before edges; consumed R-combo faces rearm only on release. */
PlayerInputFrame playerInputUpdate(PlayerInputState *,uint32_t physical_held,
                                  int16_t cstick_x,int16_t cstick_y);
#endif
