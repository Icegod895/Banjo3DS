#include "player_crouch.h"
#include "player_ground.h"
#include "player_input.h"
#include <math.h>
#include <string.h>

enum { BTN_Z = 1, BTN_A = 8, BTN_B = 9, BTN_C_LEFT = 10, BTN_C_DOWN = 11, BTN_C_UP = 12, BTN_C_RIGHT = 13 };
enum { BS_JUMP = 5, BS_FALL = 0x2F, PHYS_LOCKED = 3, PREV_ANIM_IDLE = 0x6F };
enum {
    ABILITY_BARGE = 1u << 0,
    ABILITY_CLAW = 1u << 4,
    ABILITY_FLAP = 1u << 8,
    ABILITY_ROLL = 1u << 12
};
enum { V4_PACKET = 28022, ENTER_BYTES = 2176, TURN_BYTES = 2576, NOINPUT_BYTES = 4220, V5_PACKET = 36994 };

static int32_t button_count[14], release_count[14];
static int buttons_ready, yaw_ready, blocked, frame_ready, frame_context;
/* Cleared at the start of playerCrouchFrame, before the crouch hook. Set when
 * this frame's enter or step raises sfx_count. A missed hook stays silent. */
static int sfx_latched, sfx_seen;
static int last_requested, block_reentry, seen_starts, posed_crouch;
static uint32_t learned;
static PlayerRuntime *bound;
static float blend_source[109][10];

static void buttons_up(void) {
    memset(button_count, 0, sizeof button_count);
    for (int i = 0; i < 14; i++) release_count[i] = 1;
    buttons_ready = 1;
}
static void note(int index, int down) {
    if (down) {
        if (release_count[index]) {
            button_count[index] = 1;
            release_count[index] = 0;
        } else if (button_count[index] < 2) {
            button_count[index] = 2;
        }
    } else {
        button_count[index] = 0;
        if (release_count[index] < 2) release_count[index]++;
    }
}
static int context_from_gait(uint8_t gait) {
    switch (gait) {
    case BANJO_GAIT_CREEP: return BANJO_CROUCH_CREEP;
    case BANJO_GAIT_SLOW: return BANJO_CROUCH_SLOW;
    case BANJO_GAIT_WALK: return BANJO_CROUCH_WALK;
    case BANJO_GAIT_FAST: return BANJO_CROUCH_FAST;
    default: return BANJO_CROUCH_IDLE;
    }
}
static int crouch_now(void) {
    CrouchView v;
    banjo_crouch_view(&v);
    return v.active && v.state == BANJO_CROUCH_STATE;
}
static void note_sfx(int count) {
    if (count > sfx_seen)
        sfx_latched = 1;
    sfx_seen = count;
}
static void fill_input(CrouchInput *in, const BanjoJumpMotion *m, const BanjoHorizontal *h,
                       float dt, int should_fall) {
    int context = frame_ready ? frame_context : context_from_gait(bound->locomotion.gait);
    memset(in, 0, sizeof *in);
    in->dt = dt;
    in->stick_distance = h->intent.magnitude;
    in->stick_angle = h->intent.desired_yaw;
    in->velocity_x = h->velocity[0];
    in->velocity_z = h->velocity[1];
    in->horizontal_velocity = sqrtf(h->velocity[0] * h->velocity[0] + h->velocity[1] * h->velocity[1]);
    in->target_speed = h->target_speed;
    in->context = context;
    in->prev_state = context;
    in->provisional = context;
    in->prev_anim = PREV_ANIM_IDLE;
    memcpy(in->button_count, button_count, sizeof button_count);
    memcpy(in->release_count, release_count, sizeof release_count);
    in->can_beak_barge = (learned & ABILITY_BARGE) != 0;
    in->can_claw = (learned & ABILITY_CLAW) != 0;
    in->can_flap_flip = (learned & ABILITY_FLAP) != 0;
    in->can_roll = (learned & ABILITY_ROLL) != 0;
    in->can_trot = 0;
    in->can_wonderwing = 0;
    in->can_egg = 0;
    in->should_fall = should_fall;
    in->transformation = 1;
    (void)m;
}
static void apply_view(BanjoHorizontal *h, bool *jump, int was_active, int should_fall,
                       const CrouchView *v, int *lock_mode, float *facing, int *use_facing) {
    if (was_active && v->requested != BS_JUMP) *jump = false;
    if (v->active && v->state == BANJO_CROUCH_STATE) {
        bound->locomotion.gait = BANJO_GAIT_IDLE;
        if (v->physics_type == PHYS_LOCKED && !should_fall) {
            *lock_mode = BANJO_HORIZONTAL_LOCKED;
            h->target_speed = v->target_speed;
            if (v->target_yaw_set) {
                h->heading = v->target_yaw;
                h->ideal_yaw = v->target_yaw;
            }
            h->visible_yaw = v->yaw;
            *use_facing = 1;
            *facing = v->yaw;
        }
        return;
    }
    if (!was_active) return;
    bound->locomotion.gait = BANJO_GAIT_IDLE;
    if (v->state == BANJO_CROUCH_IDLE) {
        h->target_speed = 0.0f;
        h->ideal_yaw = v->yaw;
        h->visible_yaw = v->yaw;
        h->heading = v->yaw;
        *use_facing = 1;
        *facing = v->yaw;
        return;
    }
    if (v->state == BS_JUMP || v->state == BS_FALL) return;
    /* The host machine has already left crouch. Do not play the move, and do
     * not re-enter on the following held-Z frames (that would restart 0001). */
    h->target_speed = 0.0f;
    *jump = false;
    block_reentry = 1;
}
static void before_ground(BanjoJumpMotion *m, BanjoHorizontal *h, float dt, bool *jump,
                          int should_fall, int *lock_mode, float *facing, int *use_facing) {
    CrouchInput in;
    CrouchView view;
    int was_active;
    if (!bound || blocked || !m || !h || !jump || !lock_mode || !facing || !use_facing) return;
    if (!yaw_ready) {
        banjo_crouch_reset(m->actor.yaw, m->actor.yaw);
        yaw_ready = 1;
        sfx_seen = 0;
        sfx_latched = 0;
    }
    was_active = crouch_now();
    if (!m->grounded && !was_active) return;
    if (!was_active && block_reentry) {
        if (button_count[BTN_Z] == 0) block_reentry = 0;
        else return;
    }
    fill_input(&in, m, h, dt, should_fall);
    if (!was_active) {
        int sel = banjo_crouch_select(&in);
        last_requested = sel;
        if (!(sel == BANJO_CROUCH_STATE && m->grounded)) return;
        banjo_crouch_enter(&in);
    } else {
        banjo_crouch_step(&in);
    }
    banjo_crouch_view(&view);
    last_requested = view.requested;
    note_sfx(view.sfx_count);
    apply_view(h, jump, was_active, should_fall, &view, lock_mode, facing, use_facing);
}
static int clip_for(int32_t index) {
    if (index == 1) return BANJO_CLIP_CROUCH_ENTER;
    if (index == 0x10C) return BANJO_CLIP_CROUCH_TURN;
    if (index == 0x116) return BANJO_CLIP_CROUCH_NOINPUT;
    return -1;
}
static bool animate(PlayerRuntime *s, const uint8_t *packet, size_t size, float dt) {
    CrouchView v;
    int clip;
    (void)dt;
    if (!s) return false;
    /* One grounded crouch-to-idle edge. Gait already calls this clip 006F, so
     * the updater would keep the crouch phase. Seed the rendered pose here
     * and let that updater advance phase by dt/5.5 and factor by dt/0.2. */
    if (s->jumpActive || !playerCrouchActive()) {
        if (!s->jumpActive && posed_crouch && s->motion.grounded) {
            banjo_crouch_view(&v);
            if (v.state == BANJO_CROUCH_IDLE) {
                memcpy(s->gait.source, s->gait.pose.bones, sizeof s->gait.source);
                s->gait.phase = 0.0f;
                s->gait.factor = 0.0f;
                s->gait.gait = BANJO_GAIT_IDLE;
                s->gait.initialized = true;
            }
        }
        posed_crouch = 0;
        return false;
    }
    banjo_crouch_view(&v);
    clip = clip_for(v.anim_index);
    if (clip < 0) return false;
    if (!s->gait.initialized) {
        if (!banjo_pose_sample(packet, size, BANJO_CLIP_IDLE, 0, s->gait.pose.bones)) return false;
        if (!banjo_pose_apply(packet, size, &s->gait.pose)) return false;
        s->gait.initialized = true;
        s->gait.gait = BANJO_GAIT_IDLE;
        s->gait.phase = 0;
        s->gait.factor = 1;
    }
    if (v.anim_starts != seen_starts) {
        memcpy(blend_source, s->gait.pose.bones, sizeof blend_source);
        seen_starts = v.anim_starts;
    }
    if (!banjo_pose_sample(packet, size, (BanjoClip)clip, v.anim_timer, s->gait.pose.bones)) return false;
    banjo_pose_blend(s->gait.pose.bones, blend_source, s->gait.pose.bones, v.anim_blend);
    if (!banjo_pose_apply(packet, size, &s->gait.pose)) return false;
    s->gait.initialized = true;
    s->gait.gait = BANJO_GAIT_IDLE;
    s->gait.phase = v.anim_timer;
    s->gait.factor = v.anim_blend;
    posed_crouch = 1;
    return true;
}

void playerCrouchInstall(void) {
    playerGroundSetCrouchHook(before_ground);
    playerRuntimeSetCrouchAnimate(animate);
    if (!buttons_ready) buttons_up();
}
void playerCrouchSetAbilities(uint32_t mask) { learned = mask; }
void playerCrouchReset(float yaw) {
    banjo_crouch_reset(yaw, yaw);
    sfx_seen = 0;
    sfx_latched = 0;
    buttons_up();
    yaw_ready = 1;
    blocked = 0;
    frame_ready = 0;
    frame_context = BANJO_CROUCH_IDLE;
    last_requested = 0;
    block_reentry = 0;
    seen_starts = 0;
    posed_crouch = 0;
    memset(blend_source, 0, sizeof blend_source);
}
void playerCrouchFrame(PlayerRuntime *s, uint32_t logical_held, int fp_blocked) {
    static const struct { uint32_t bit; int index; } map[] = {
        {PI_N64_Z, BTN_Z}, {PI_N64_A, BTN_A}, {PI_N64_B, BTN_B},
        {PI_N64_CLEFT, BTN_C_LEFT}, {PI_N64_CDOWN, BTN_C_DOWN},
        {PI_N64_CUP, BTN_C_UP}, {PI_N64_CRIGHT, BTN_C_RIGHT}
    };
    sfx_latched = 0;
    if (!s) return;
    if (!buttons_ready) buttons_up();
    bound = s;
    blocked = fp_blocked;
    frame_context = context_from_gait(s->locomotion.gait);
    frame_ready = 1;
    for (size_t i = 0; i < sizeof map / sizeof map[0]; i++)
        note(map[i].index, (logical_held & map[i].bit) != 0);
}
bool playerCrouchActive(void) { return crouch_now(); }
int playerCrouchSlideSfx(void) { return sfx_latched; }
int playerCrouchRequested(void) { return last_requested; }
int playerCrouchState(void) {
    CrouchView v;
    banjo_crouch_view(&v);
    return v.state;
}
void playerCrouchCopy(CrouchView *out) { if (out) banjo_crouch_view(out); }
size_t playerCrouchActivate(uint8_t *out, size_t cap,
    const uint8_t *prefix, size_t prefix_len,
    const uint8_t *enter, size_t enter_len,
    const uint8_t *turn, size_t turn_len,
    const uint8_t *noinput, size_t noinput_len) {
    if (!out || !prefix || !enter || !turn || !noinput) return 0;
    if (prefix_len != V4_PACKET || enter_len != ENTER_BYTES || turn_len != TURN_BYTES
        || noinput_len != NOINPUT_BYTES || cap < V5_PACKET) return 0;
    memcpy(out, prefix, prefix_len);
    out[4] = 0;
    out[5] = 0;
    out[6] = 0;
    out[7] = 5;
    memcpy(out + V4_PACKET, enter, enter_len);
    memcpy(out + V4_PACKET + ENTER_BYTES, turn, turn_len);
    memcpy(out + V4_PACKET + ENTER_BYTES + TURN_BYTES, noinput, noinput_len);
    return V5_PACKET;
}
