#include "footstep.h"

#include "gait.h"

#include <math.h>

/* func_803246B4 in code_9D640.c calls the high-bit or map matcher and then
 * drops the return. The N64 footsteps are the matcher result, so this port
 * returns that value. A stored flags word of 0 is silence before either table.
 * Type 4 is only the open interval (0, 60) of floorY - playerY. A grounded
 * snap sets those equal, so the interval does not fire. */

static const struct {
    int map_id;
    int type[5];
} MAPS[] = {
    {0x01, {1, 7, 6, 5, 1}},
    {0x02, {1, 5, 6, 1, 1}},
    {0x07, {2, 5, 6, 1, 1}},
    {0x26, {1, 5, 1, 1, 1}},
    {0x0B, {1, 9, 10, 8, 1}},
    {0x0D, {8, 11, 1, 1, 1}},
    {0x12, {2, 6, 1, 1, 1}},
    {0x13, {6, 1, 1, 6, 1}},
    {0x14, {6, 1, 1, 1, 1}},
    {0x15, {6, 1, 1, 1, 1}},
    {0x16, {6, 1, 1, 1, 1}},
    {0x1A, {6, 1, 1, 1, 1}},
    {0x1B, {1, 7, 6, 12, 5}},
    {0x21, {1, 9, 10, 8, 1}},
    {0x22, {1, 9, 10, 8, 1}},
    {0x23, {1, 9, 10, 8, 1}},
    {0x27, {3, 5, 3, 1, 1}},
    {0x31, {9, 10, 5, 6, 1}},
    {0x46, {3, 1, 1, 1, 1}},
    {0x72, {1, 8, 11, 3, 5}},
    {0x6F, {1, 3, 3, 1, 1}},
    {0x40, {1, 6, 5, 3, 7}},
    {0, {0, 0, 0, 0, 0}}
};

static const struct {
    uint32_t key;
    int type;
} HIGH[] = {
    {0x80000000u, 1},
    {0x80000100u, 10},
    {0x80000200u, 9},
    {0x80000300u, 6},
    {0x80000400u, 5},
    {0x80000500u, 3},
    {0x80000600u, 7},
    {0x80000700u, 8},
    {0x80000800u, 2},
    {0x80000900u, 11},
    {0x80000A00u, 1},
    {0x80000B00u, 1},
    {0x80000C00u, 1},
    {0x80000D00u, 1},
    {0x80000E00u, 1},
    {0x80000F00u, 1},
    {0u, 0}
};

/* D_80368DF0. Decimal types 10 and 11 are the 0xA and 0xB rows. */
static const BanjoFootRow SOUNDS[] = {
    {0x1, 0x8, 1.0f, 1.2f, 0.05f, 9000},
    {0x2, 0x7, 1.0f, 1.2f, 0.05f, 3000},
    {0x3, 0xB, 1.0f, 1.2f, 0.05f, 11000},
    {0x4, 0x10, 1.0f, 1.2f, 0.05f, 13000},
    {0x5, 0x26, 1.0f, 1.2f, 0.05f, 9000},
    {0x6, 0x6, 1.0f, 1.2f, 0.05f, 7000},
    {0x7, 0x28, 1.0f, 1.0f, 0.05f, 10000},
    {0x8, 0x5, 0.7f, 0.8f, 0.05f, 17000},
    {0xB, 0x10, 0.5f, 0.55f, 0.01f, 16000},
    {0x9, 0x98, 1.0f, 1.1f, 0.05f, 21000},
    {0xA, 0x99, 1.0f, 1.1f, 0.05f, 21000},
    {0xC, 0x123, 0.85f, 0.89f, 0.05f, 21000},
    {0xD, 0x3F2, 0.96f, 1.04f, 0.02f, 10000},
    {0xE, 0x10, 1.2f, 1.35f, 0.05f, 13000},
    {0xF, 0xDC, 0.95f, 1.1f, 0.05f, 16000}
};

_Static_assert(BANJO_GAIT_IDLE == 0 && BANJO_GAIT_CREEP == 1
    && BANJO_GAIT_SLOW == 2 && BANJO_GAIT_WALK == 3
    && BANJO_GAIT_FAST == 4, "gait ids");
_Static_assert(BANJO_FOOT_AI_RATE == 22000, "footsteps use the N64 AI clock");

static int foot_high(uint32_t flags)
{
    uint32_t key = flags & 0x80001F00u;
    int i;

    for (i = 0; HIGH[i].key != 0; i++) {
        if (HIGH[i].key == key)
            return HIGH[i].type;
    }
    return 1;
}

static int foot_map(int map_id, uint32_t flags)
{
    int sub = 0;
    int i;

    /* Later bits replace earlier ones, matching func_80324624. */
    if (flags & 0x200u)
        sub = 1;
    if (flags & 0x400u)
        sub = 2;
    if (flags & 0x800u)
        sub = 3;
    if (flags & 0x1000u)
        sub = 4;
    for (i = 0; MAPS[i].map_id != 0; i++) {
        if (MAPS[i].map_id == map_id)
            return MAPS[i].type[sub];
    }
    return 1;
}

/* libultra alCents2Ratio. ratio = 2^(cents/1200), one multiply per set bit. */
float banjo_foot_cents_ratio(int cents)
{
    float x;
    float ratio = 1.0f;

    if (cents >= 0) {
        x = 1.00057779f;
    } else {
        x = 0.9994225441f;
        cents = -cents;
    }
    while (cents) {
        if (cents & 1)
            ratio *= x;
        x *= x;
        cents >>= 1;
    }
    return ratio;
}

float banjo_foot_key_ratio(int key_base, int detune, int omit_detune)
{
    int cents = key_base * 100 - 0x1770;

    if (!omit_detune)
        cents += detune;
    return banjo_foot_cents_ratio(cents);
}

float banjo_foot_output_rate(float table_pitch, int key_base, int detune, int omit_detune)
{
    return (float)BANJO_FOOT_AI_RATE * table_pitch
        * banjo_foot_key_ratio(key_base, detune, omit_detune);
}

void banjo_foot_reset(BanjoFootState *state)
{
    if (!state)
        return;
    state->rng = BANJO_FOOT_PITCH_SEED;
    state->unk1E = 0;
    state->ready = 1;
}

int banjo_foot_source(const BanjoFootState *state)
{
    if (!state)
        return 0;
    return state->unk1E;
}

int banjo_foot_surface(int map_id, uint32_t flags, float floor_y, float player_y)
{
    float gap;

    if (flags == 0)
        return 0;
    gap = floor_y - player_y;
    if (0.0f < gap && gap < 60.0f)
        return 4;
    if (flags & 0x80000000u)
        return foot_high(flags);
    return foot_map(map_id, flags);
}

int banjo_foot_row(int type, BanjoFootRow *row)
{
    int i;

    if (!row)
        return 0;
    for (i = 0; i < (int)(sizeof SOUNDS / sizeof SOUNDS[0]); i++) {
        if (SOUNDS[i].type == type) {
            *row = SOUNDS[i];
            return 1;
        }
    }
    return 0;
}

int banjo_foot_gait_marks(int gait, float marks[2], int feet[2])
{
    if (!marks || !feet)
        return 0;
    if (gait == BANJO_GAIT_CREEP) {
        marks[0] = 0.47f;
        marks[1] = 0.97f;
        feet[0] = 4;
        feet[1] = 3;
        return 2;
    }
    if (gait == BANJO_GAIT_SLOW || gait == BANJO_GAIT_WALK || gait == BANJO_GAIT_FAST) {
        marks[0] = 0.4f;
        marks[1] = 0.9f;
        feet[0] = 4;
        feet[1] = 3;
        return 2;
    }
    return 0;
}

float banjo_foot_unit(unsigned *rng)
{
    unsigned x;

    if (!rng)
        return 0.0f;
    x = *rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    if (x == 0)
        x = BANJO_FOOT_PITCH_SEED;
    *rng = x;
    return (float)(x >> 8) * (1.0f / 16777216.0f);
}

float banjo_foot_vary(float center, float jitter, float unit)
{
    float range = jitter * 0.5f;
    float low = center - range;
    float high = center + range;

    return low + unit * (high - low);
}

/* Forward anctrl_isAt. The port phase only moves forward, including a wrap
 * back through 0. Landing on the mark does not fire; the next step past it does. */
static int foot_crossed(float old_phase, float new_phase, float mark)
{
    if (!isfinite(old_phase) || !isfinite(new_phase) || !isfinite(mark))
        return 0;
    if (old_phase == new_phase)
        return 0;
    if (old_phase < new_phase)
        return old_phase <= mark && mark < new_phase;
    return old_phase <= mark || mark < new_phase;
}

static int foot_emit(BanjoFootState *state, int type, int foot,
    BanjoFootPlay *out, int count, int capacity)
{
    BanjoFootRow row;
    float unit;
    float center;
    int source;

    if (!banjo_foot_row(type, &row))
        return count;
    if (state->unk1E) {
        source = 1;
        center = row.pitch_a;
    } else {
        source = 0;
        center = row.pitch_b;
    }
    unit = banjo_foot_unit(&state->rng);
    if (count < capacity) {
        out[count].sfx_id = row.sfx_id;
        out[count].type = type;
        out[count].foot = foot;
        out[count].source = source;
        out[count].loudness = row.loudness;
        out[count].pitch = banjo_foot_vary(center, row.jitter, unit);
        out[count].rate = (float)BANJO_FOOT_AI_RATE * out[count].pitch;
        count += 1;
    }
    state->unk1E ^= 1;
    return count;
}

int banjo_foot_observe(BanjoFootState *state, const BanjoFootFrame *frame,
    BanjoFootPlay *out, int capacity)
{
    float start;
    float marks[2];
    int feet[2];
    int nmarks;
    int type;
    int count = 0;
    int i;

    if (!state || !frame || !out || capacity < 2)
        return 0;
    if (!state->ready)
        banjo_foot_reset(state);
    if (!frame->animated || !frame->grounded || frame->crouch || frame->jumping
        || !frame->floor_valid || !frame->initialized_after)
        return 0;
    nmarks = banjo_foot_gait_marks(frame->gait_after, marks, feet);
    if (nmarks <= 0)
        return 0;
    /* Phase at the start of this gait update, after a clip-change reset and
     * before dt/duration. Same rules as banjo_gait_update_selected. */
    if (!frame->initialized_before) {
        start = 0.0f;
    } else if (banjo_gait_clip((BanjoGait)frame->gait_after)
        != banjo_gait_clip((BanjoGait)frame->gait_before)) {
        start = banjo_gait_start_phase((BanjoGait)frame->gait_before,
            (BanjoGait)frame->gait_after, frame->phase_before);
    } else {
        start = frame->phase_before;
    }
    type = banjo_foot_surface(frame->map_id, frame->flags, frame->floor_y, frame->player_y);
    for (i = 0; i < nmarks; i++) {
        if (foot_crossed(start, frame->phase_after, marks[i]))
            count = foot_emit(state, type, feet[i], out, count, capacity);
    }
    return count;
}
