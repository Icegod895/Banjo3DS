#ifndef BANJO_FOOTSTEP_H
#define BANJO_FOOTSTEP_H

#include <stdint.h>

/* Grounded walking footsteps.
 * Surface type comes from the winning triangle's flags word, the same word
 * func_80294660 returns into func_802F4420. The s16 surface field is not the key.
 * MAP_1_SM_SPIRAL_MOUNTAIN is 1. Ordinary steps use func_802F4924 (pitch offset 0).
 * Turbo, trot, and long-leg func_802F494C are not part of this walk.
 * The pitch draw is a private xorshift. It is not the retail randf sequence and
 * it does not share the slide voice seed. */

#define BANJO_FOOT_MAP_SPIRAL_MOUNTAIN 1
#define BANJO_FOOT_AI_RATE 22000
#define BANJO_FOOT_PITCH_SEED 0x4D343135u

typedef struct BanjoFootState {
    unsigned rng;
    int unk1E; /* 0 selects pitch B and source unk1D. Rare toggles after a play. */
    int ready;
} BanjoFootState;

typedef struct BanjoFootFrame {
    int gait_before;
    float phase_before;
    int initialized_before;
    int gait_after;
    float phase_after;
    int initialized_after;
    int animated;
    int grounded;
    int crouch;
    int jumping;
    int map_id;
    uint32_t flags;
    float floor_y;
    float player_y;
    int floor_valid;
} BanjoFootFrame;

typedef struct BanjoFootPlay {
    int sfx_id;
    int type;
    int foot; /* walk.c foot index, 4 then 3. It does not choose the NDSP channel. */
    int source; /* 0 = unk1D / NDSP channel 1, 1 = unk1C / NDSP channel 2. */
    int loudness; /* D_80368DF0's last integer. n_alSynSetVol, not a sample rate. */
    float pitch; /* randf2 around pitch A or pitch B. This is unk2C, before keyBase. */
    float rate; /* AI clock times pitch, before the keyBase ratio unk28. */
} BanjoFootPlay;

typedef struct BanjoFootRow {
    int type;
    int sfx_id;
    float pitch_a;
    float pitch_b;
    float jitter;
    int loudness;
} BanjoFootRow;

void banjo_foot_reset(BanjoFootState *state);
int banjo_foot_surface(int map_id, uint32_t flags, float floor_y, float player_y);
int banjo_foot_row(int type, BanjoFootRow *row);
int banjo_foot_gait_marks(int gait, float marks[2], int feet[2]);
float banjo_foot_unit(unsigned *rng);
float banjo_foot_vary(float center, float jitter, float unit);
float banjo_foot_cents_ratio(int cents);
float banjo_foot_key_ratio(int key_base, int detune, int omit_detune);
float banjo_foot_output_rate(float table_pitch, int key_base, int detune, int omit_detune);
int banjo_foot_source(const BanjoFootState *state);
/* capacity must be at least 2. Returns the number of steps queued, 0 when silent. */
int banjo_foot_observe(BanjoFootState *state, const BanjoFootFrame *frame,
    BanjoFootPlay *out, int capacity);

#endif
