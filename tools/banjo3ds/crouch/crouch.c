#include "crouch.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* State ids and asset ids are the original enum values. */
enum {
    BS_IDLE = 1, BS_SLOW = 2, BS_WALK = 3, BS_FAST = 4, BS_JUMP = 5, BS_CLAW = 6,
    BS_CROUCH = 7, BS_EGG_HEAD = 9, BS_EGG_ASS = 10, BS_SKID = 12, BS_FLIP = 0x12,
    BS_BARGE = 0x13, BS_TROT = 0x14, BS_WONDER = 0x1A, BS_CREEP = 0x1F,
    BS_FLY = 0x23, BS_LONGLEG = 0x25, BS_SWIM = 0x2D, BS_FALL = 0x2F, BS_ROLL = 0x31,
    BS_SLIDE = 0x32, BS_NOTEDOOR = 0x34, BS_JIGGY = 0x44, BS_BEE_NOTE = 0x46,
    BS_TIMEOUT = 0x53, BS_MUD = 0x7A, BS_WALRUS_LOSE = 0x80, BS_DRONE = 0x98
};
enum { BTN_Z = 1, BTN_A = 8, BTN_B = 9, BTN_C_LEFT = 10, BTN_C_DOWN = 11, BTN_C_UP = 12, BTN_C_RIGHT = 13 };
enum { ANIM_ONCE = 1, ANIM_LOOP = 2, ANIM_STOPPED = 3 };
enum { CLIP_ENTER = 1, CLIP_IDLE = 0x6F, CLIP_CROUCH_IDLE = 0x10C, CLIP_NOINPUT = 0x116 };
enum { PHYS_NORMAL = 2, PHYS_LOCKED = 3, YAW_DEFAULT = 1, YAW_BOUNDED = 3, ANIM_NORMAL = 1 };
enum { ITEM_EGGS = 0xD, ITEM_FEATHER = 0x10, XFORM_WALRUS = 4, XFORM_BEE = 6 };
enum {
    FLAG_FLIGHT = 1, FLAG_SPRING = 2, FLAG_TIMEOUT = 6, FLAG_JIGGY = 7, FLAG_WADING = 14,
    FLAG_TURBO = 16, FLAG_BOGGY = 20, FLAG_TRANSFORM = 25, FLAG_NOTEDOOR = 26
};

typedef char crouch_input_size_ok[(sizeof(CrouchInput) == 264) ? 1 : -1];
typedef char crouch_view_size_ok[(sizeof(CrouchView) == 156) ? 1 : -1];

static CrouchInput cur;
static float target_speed, target_yaw, entry_speed;
static int target_yaw_set, physics_type;
static float yaw_deg, yaw_ideal, yaw_limit, yaw_percent, yaw_unbounded, facing_threshold;
static int yaw_state, facing_mode;
static float timer_value[8], timer_last[8];
static int phase, state, prev_state, requested, active, anim_update_type;
static int sfx_count, puff_count, footstep_count, last_footstep, anim_starts, fidget, buzzer, item_use;
static uint16_t acos_table[10001];
static int acos_ready;

typedef struct Animation {
    uint32_t index;
    float timer, duration;
} Animation;
typedef struct AnimCtrl {
    Animation *animation;
    float timer, subrange_start, subrange_end, animation_duration, transition_duration, start;
    int32_t index;
    int playback_type, playback_direction, smooth_transition, default_start;
} AnimCtrl;

static Animation anim_store;
static AnimCtrl ctrl;

static float ml_max_f(float a, float b) { return a > b ? a : b; }
static float ml_min_f(float a, float b) { return a < b ? a : b; }
static float mlAbsF(float v) { return v > 0 ? v : -v; }
static float ml_clamp_f(float val, float min, float max) {
    if (val < min) return min;
    if (val > max) return max;
    return val;
}
static float mlNormalizeAngle(float angle) {
    if (angle < 0.0) {
        angle = mlNormalizeAngle(-angle);
        angle = 360.0 - angle;
    }
    if (angle >= 360.0)
        angle -= 360.0 * (int)(angle / 360.0);
    return angle;
}
static float mlDiffDegF(float a, float b) {
    float diff = a - b;
    while (diff > 180) diff -= 360;
    while (diff <= -180) diff += 360;
    return diff;
}
static float ml_map_f(float val, float in_min, float in_max, float out_min, float out_max) {
    float result;
    if (in_max != in_min) {
        if (out_min < out_max) {
            result = (((val - in_min) / (in_max - in_min)) * (out_max - out_min)) + out_min;
            if (result > out_max) return out_max;
            if (result < out_min) return out_min;
        } else {
            result = (((val - in_min) / (in_max - in_min)) * (out_max - out_min)) + out_min;
            if (result < out_max) return out_max;
            if (result > out_min) return out_min;
        }
        return result;
    }
    return out_max;
}
static float ml_mapAbsRange_f(float val, float in_min, float in_max, float out_min, float out_max) {
    if (val < 0) return ml_map_f(val, -in_min, -in_max, -out_min, -out_max);
    return ml_map_f(val, in_min, in_max, out_min, out_max);
}
static float ml_acosf(float x) {
    uint16_t lower = 0, upper = 10000, idx = 10000;
    float x_abs = (x >= 0) ? x : -x;
    uint16_t target = x_abs * 65535.0;
    while ((upper - lower >= 2) && (target != acos_table[idx])) {
        idx = (uint16_t)((upper + lower) / 2);
        if (target < acos_table[idx]) upper = idx;
        else lower = idx;
    }
    return idx * 90.0 / 10000.0;
}
static int heading_from_velocity(const float v[3], float *yaw) {
    float diff[3], h;
    *yaw = 0;
    diff[0] = v[0]; diff[1] = v[1]; diff[2] = v[2];
    h = sqrtf(diff[2] * diff[2] + diff[0] * diff[0]);
    if (h < 0.01) return 0;
    *yaw = ml_acosf(diff[0] / h);
    if (diff[2] < 0) *yaw = 180 - *yaw;
    if (diff[0] < 0) *yaw = 360 - *yaw;
    return 1;
}
static void ensure_acos(void) {
    uint16_t i;
    if (acos_ready) return;
    for (i = 0; i < 10001; i++)
        acos_table[i] = sinf(i * 90.0 / 10000 * M_PI / 180) * 65535.f;
    acos_ready = 1;
}

static float time_getDelta(void) { return cur.dt; }
static int pressed(int b) { return cur.button_count[b] == 1; }
static int held(int b) { return cur.button_count[b]; }
static int released(int b) { return cur.release_count[b]; }
static float stick_distance(void) { return cur.stick_distance; }
static float stick_angle(void) { return cur.stick_angle; }
static float stick_x(void) { return 0.f; }
static int flag_is(int n) {
    switch (n) {
    case FLAG_FLIGHT: return cur.flight;
    case FLAG_SPRING: return cur.spring;
    case FLAG_TIMEOUT: return cur.timeout_flag;
    case FLAG_JIGGY: return cur.jiggy;
    case FLAG_WADING: return cur.wading;
    case FLAG_TURBO: return cur.turbo;
    case FLAG_BOGGY: return cur.boggy;
    case FLAG_TRANSFORM: return cur.transform;
    case FLAG_NOTEDOOR: return cur.notedoor;
    default: return 0;
    }
}

static int timer_decrement(int id) {
    timer_last[id] = timer_value[id];
    if (0.0f == timer_value[id]) return 0;
    timer_value[id] = ml_max_f(0.0f, timer_value[id] - time_getDelta());
    return timer_value[id] == 0.0f;
}
static void timer_set(int id, float v) { timer_last[id] = timer_value[id] = v; }
static float timer_get(int id) { return timer_value[id]; }
static int timer_nonzero(int id) { return 0.0 != timer_value[id]; }
static int timer_zero(int id) { return 0.0 == timer_value[id]; }

static void yaw_set(float v) { yaw_deg = mlNormalizeAngle(v); }
static void yaw_set_ideal(float v) { yaw_ideal = mlNormalizeAngle(v); }
static void yaw_limited(float limit, float percent) {
    float dyaw, val, dt = time_getDelta(), max;
    max = limit * dt;
    dyaw = yaw_ideal - yaw_deg;
    if (180.0f < mlAbsF(dyaw))
        dyaw += (dyaw < 0.0f) ? 360.0 : -360.0;
    val = dyaw * percent * dt;
    val = (val < 0) ? ml_clamp_f(val, -max, -0.1f) : ml_clamp_f(val, 0.1f, max);
    yaw_deg = (mlAbsF(val) <= mlAbsF(dyaw)) ? yaw_deg + val : yaw_ideal;
    if (yaw_deg < 360.0) {
        if (yaw_deg < 0.0) yaw_deg += 360.0;
    } else {
        yaw_deg -= 360.0;
    }
}
static void yaw_limitless(float speed) {
    float dyaw, step;
    speed *= time_getDelta();
    dyaw = yaw_ideal - yaw_deg;
    if (mlAbsF(dyaw) > 180.0f)
        dyaw += (dyaw < 0.0f) ? 360.0 : -360.0;
    step = (mlAbsF(dyaw) > 180.0f) ? speed : ((dyaw < 0.0f) ? -speed : speed);
    if (mlAbsF(step) <= mlAbsF(dyaw)) yaw_deg += step;
    else yaw_deg = yaw_ideal;
    if (yaw_deg < 360.0) {
        if (yaw_deg < 0.0) yaw_deg = yaw_deg + 360.0;
    } else {
        yaw_deg = yaw_deg - 360.0;
    }
}
static void yaw_update(void) {
    switch (yaw_state) {
    case 0: break;
    case 1: yaw_limited(700.0f, 7.5f); break;
    case 2: yaw_limitless(yaw_unbounded); break;
    case 3: yaw_limited(yaw_limit, yaw_percent); break;
    default: break;
    }
}
static void facing_update(void) {
    switch (facing_mode) {
    case 1:
        if (stick_distance() != 0.0f) yaw_set_ideal(stick_angle());
        yaw_update();
        break;
    case 3:
        yaw_update();
        break;
    case 4:
        if (stick_distance() != 0.0f) {
            yaw_set_ideal(stick_angle());
            yaw_set(yaw_ideal);
        }
        yaw_update();
        break;
    case 5:
        if (stick_distance() != 0.0f) yaw_set_ideal(stick_angle() + 180.0f);
        yaw_update();
        break;
    case 6: {
        float x = stick_x();
        float d = (0.03 < (double)mlAbsF(x)) ? ml_mapAbsRange_f(x, 0.0f, 1.0f, 1.0f, 6.0f) : 0.0f;
        yaw_set_ideal(yaw_ideal + d);
        yaw_update();
        break;
    }
    case 7:
        if (stick_distance() != 0.0f) {
            float angle = stick_angle();
            float diff = mlDiffDegF(yaw_ideal, angle);
            if (facing_threshold <= mlAbsF(diff))
                yaw_set_ideal(stick_angle());
        }
        yaw_update();
        break;
    case 0:
    case 2:
    default:
        break;
    }
}

static void anim_set_duration(float arg1) {
    /* Retail IO_READ(0x238) - 0x10000003 is 0, so the +3s branch does not run. */
    if ((0x10000003 - 0x10000003) != 0) arg1 += 3.0f;
    ctrl.animation_duration = arg1;
}
static void anim_set_subrange(float start, float end) {
    ctrl.subrange_start = start - (float)(int)start;
    ctrl.subrange_end = (end != 1.0) ? end - (float)(int)end : end;
}
static void anim_set_start(float start) {
    if (start == 1.0) start = 0.9999989867210388f;
    ctrl.start = start;
    ctrl.default_start = 0;
}
static void anim_goto_start(void) {
    if (ctrl.default_start) {
        if (ctrl.playback_direction) anim_store.timer = 0.0f;
        else anim_store.timer = 0.99999899f;
    } else {
        anim_store.timer = ctrl.start;
    }
    ctrl.timer = anim_store.timer;
}
static void anim_blend_ramp(void) {
    float duration;
    if (!ctrl.smooth_transition) return;
    duration = anim_store.duration;
    if (duration < 1.0f)
        anim_store.duration = ml_min_f(1.0f, time_getDelta() / ctrl.transition_duration + duration);
}
static void anim_start(void) {
    anim_starts++;
    if (ctrl.smooth_transition && anim_store.index != 0) {
        anim_store.index = (uint32_t)ctrl.index;
        anim_goto_start();
        anim_store.duration = 0.0f;
    } else {
        anim_store.index = (uint32_t)ctrl.index;
        anim_goto_start();
        anim_store.duration = 1.0f;
    }
}
static void anim_reset(void) {
    ctrl.playback_type = ANIM_LOOP;
    ctrl.default_start = 1;
    ctrl.timer = 0.0;
    ctrl.start = 0.0;
    ctrl.smooth_transition = 1;
    anim_set_subrange(0.0, 1.0);
    anim_set_duration(2.0);
    ctrl.transition_duration = 0.2f;
    ctrl.playback_direction = 1;
}
static void anim_update_once(void) {
    float step, next;
    anim_blend_ramp();
    ctrl.timer = anim_store.timer;
    step = time_getDelta() / ctrl.animation_duration;
    if (ctrl.playback_direction == 0) step = -step;
    next = ctrl.timer + step;
    if (next < 0.0f) {
        next = 0.0f;
        ctrl.playback_type = ANIM_STOPPED;
    } else if ((ctrl.subrange_end < next) || (0.999999 < (double)next)) {
        if (ctrl.subrange_end < next) next = ctrl.subrange_end;
        if (0.999999 < (double)next) next = 0.9999989867210388f;
        ctrl.playback_type = ANIM_STOPPED;
    } else {
        next = next - (float)(int)next;
    }
    anim_store.timer = next;
}
static void anim_update_loop(void) {
    float delta, tmp;
    anim_blend_ramp();
    ctrl.timer = anim_store.timer;
    delta = time_getDelta() / ctrl.animation_duration;
    if (ctrl.playback_direction == 0) delta = -delta;
    tmp = ctrl.timer + delta;
    if (tmp < 0.0f) tmp += 1.0f;
    tmp -= (float)(int)tmp;
    anim_store.timer = tmp;
}
static void anim_update_subrange(void) {
    float delta, tmp, range, percent;
    anim_blend_ramp();
    ctrl.timer = anim_store.timer;
    delta = time_getDelta() / ctrl.animation_duration;
    if (ctrl.playback_direction == 0) delta = -delta;
    tmp = ctrl.timer + delta;
    if (ctrl.subrange_end <= tmp) {
        range = ctrl.subrange_end - ctrl.subrange_start;
        percent = (tmp - ctrl.subrange_start) / range;
        tmp = ctrl.subrange_start + (percent - (float)(int)percent) * range;
    }
    anim_store.timer = tmp;
}
static void anim_ctrl_update(void) {
    switch (ctrl.playback_type) {
    case 0: break;
    case ANIM_ONCE: anim_update_once(); break;
    case ANIM_LOOP: anim_update_loop(); break;
    case 4: anim_update_subrange(); break;
    case ANIM_STOPPED: anim_blend_ramp(); break;
    default: break;
    }
}
static int anim_is_at(float arg1) {
    float now = anim_store.timer;
    if (now == ctrl.timer) return 0;
    if (ctrl.playback_direction != 0) {
        if (ctrl.timer < now) return ctrl.timer <= arg1 && arg1 < now;
        return ctrl.timer <= arg1 || arg1 < now;
    }
    if (now < ctrl.timer) return arg1 <= ctrl.timer && now < arg1;
    return arg1 <= ctrl.timer || now < arg1;
}
static void play_loop(int clip, float duration) {
    anim_reset();
    ctrl.index = clip;
    anim_set_duration(duration);
    ctrl.playback_type = ANIM_LOOP;
    anim_start();
}
static void play_once(int clip, float duration) {
    anim_reset();
    ctrl.index = clip;
    anim_set_duration(duration);
    ctrl.playback_type = ANIM_ONCE;
    anim_start();
}
static void play_once_at(int clip, float duration, float start) {
    anim_reset();
    ctrl.index = clip;
    anim_set_duration(duration);
    anim_set_start(start);
    ctrl.playback_type = ANIM_ONCE;
    anim_start();
}
static void post_frame(void) {
    facing_update();
    if (anim_update_type == ANIM_NORMAL) anim_ctrl_update();
    else if (anim_update_type != 0) abort();
}
static void set_types(int anim_type, int yaw_type, int mode, int physics) {
    anim_update_type = anim_type;
    yaw_state = yaw_type;
    facing_mode = mode;
    physics_type = physics;
}
static void stand_init(void) {
    play_once(CLIP_IDLE, 5.5f);
    set_types(1, YAW_DEFAULT, 1, PHYS_NORMAL);
    target_speed = 0.0f;
    fidget++;
}

static void phase_turn(void) {
    play_loop(CLIP_CROUCH_IDLE, 0.5f);
    phase = 4;
}
static void phase_noinput(void) {
    play_once(CLIP_NOINPUT, 2.0f);
    phase = 2;
}
static void phase_recover(void) {
    play_once_at(CLIP_CROUCH_IDLE, 0.5f, 0.9999f);
    timer_set(2, 2.0f);
    phase = 1;
}
static void scale_turn(float err) {
    anim_set_duration(ml_map_f(err, 0.0f, 180.0f, 0.5f, 0.2f));
}
static void footsteps(void) {
    if (anim_is_at(0.41f)) { footstep_count++; last_footstep = 4; }
    if (anim_is_at(0.91f)) { footstep_count++; last_footstep = 3; }
}
static int item_empty(int item) {
    if (item == ITEM_FEATHER) return cur.feather_empty;
    if (item == ITEM_EGGS) return cur.egg_empty;
    return 1;
}
static void use_item(int *out, int fail_state, int success, int item, int consume) {
    if (item_empty(item)) {
        buzzer++;
        if (fail_state != -1) *out = fail_state;
    } else {
        if (consume) item_use++;
        if (success != -1) *out = success;
    }
}
static int jump_type(void) {
    if (held(BTN_Z) && cur.can_flap_flip) return BS_FLIP;
    if (flag_is(FLAG_SPRING)) return BS_JUMP;
    if (flag_is(FLAG_FLIGHT)) return BS_FLY;
    return BS_JUMP;
}
static int scripted(int next) {
    if (flag_is(FLAG_TRANSFORM)) next = BS_DRONE;
    if (flag_is(FLAG_NOTEDOOR)) next = (cur.transformation == XFORM_BEE) ? BS_BEE_NOTE : BS_NOTEDOOR;
    if (flag_is(FLAG_WADING)) next = BS_LONGLEG;
    if (flag_is(FLAG_TURBO)) next = BS_TROT;
    if (flag_is(FLAG_TIMEOUT)) next = BS_TIMEOUT;
    if (flag_is(FLAG_JIGGY)) next = BS_JIGGY;
    if (flag_is(FLAG_BOGGY)) next = (cur.transformation == XFORM_WALRUS) ? BS_WALRUS_LOSE : BS_TIMEOUT;
    return next;
}
static int attack_from_speed(int next) {
    if (pressed(BTN_B)) {
        if (225.0f < cur.target_speed) {
            if (cur.can_roll) next = BS_ROLL;
        } else if (cur.can_claw) {
            next = BS_CLAW;
        }
    }
    return next;
}
static int interrupt_tail(int next) {
    if (cur.fp_look) next = BS_DRONE;
    if (cur.should_fall) next = BS_FALL;
    if (held(BTN_Z)) next = BS_CROUCH;
    next = attack_from_speed(next);
    if (pressed(BTN_A)) next = jump_type();
    if (cur.slide) next = BS_SLIDE;
    next = scripted(next);
    if (cur.in_water) next = BS_SWIM;
    return next;
}
static int stand_select(void) {
    int next = 0;
    switch (cur.zone) {
    case 1: next = BS_CREEP; break;
    case 2: next = BS_SLOW; break;
    case 3: next = BS_WALK; break;
    case 4: next = BS_FAST; break;
    default: break;
    }
    if (held(BTN_Z)) next = BS_CROUCH;
    if (pressed(BTN_B) && cur.can_claw) next = BS_CLAW;
    if (pressed(BTN_A)) next = jump_type();
    if (cur.fp_look) next = BS_DRONE;
    if (cur.slide) next = BS_SLIDE;
    next = scripted(next);
    if (cur.in_water) next = BS_SWIM;
    if (cur.should_fall) next = BS_FALL;
    return next;
}
static int crouch_transitions(int next) {
    if (released(BTN_Z)) {
        next = BS_IDLE;
        if (pressed(BTN_B) && cur.can_claw) next = BS_CLAW;
        if (pressed(BTN_A)) next = jump_type();
    } else {
        if (pressed(BTN_C_RIGHT) && cur.can_wonderwing)
            use_item(&next, -1, BS_WONDER, ITEM_FEATHER, 1);
        if (pressed(BTN_C_LEFT) && cur.can_trot) next = BS_TROT;
        if (pressed(BTN_C_DOWN) && cur.can_egg)
            use_item(&next, -1, BS_EGG_ASS, ITEM_EGGS, 0);
        if (pressed(BTN_C_UP) && cur.can_egg)
            use_item(&next, -1, BS_EGG_HEAD, ITEM_EGGS, 0);
        if (pressed(BTN_A) && cur.can_flap_flip) next = BS_FLIP;
        if (pressed(BTN_B) && cur.can_beak_barge) next = BS_BARGE;
    }
    return next;
}
static void set_state(int id) {
    if (id == 0) return;
    requested = id;
    prev_state = state;
    state = id;
    if (id == BS_CROUCH) {
        active = 1;
    } else if (id == BS_IDLE) {
        active = 0;
        stand_init();
    } else {
        active = 0;
    }
}
static void crouch_init(void) {
    float velocity[3], heading, start;
    switch (prev_state) {
    case BS_EGG_HEAD:
    case BS_EGG_ASS:
    case BS_WONDER:
        start = 0.5357f;
        break;
    default:
        start = 0.0f;
        break;
    }
    anim_reset();
    ctrl.index = CLIP_ENTER;
    anim_set_duration(0.5f);
    ctrl.playback_type = ANIM_ONCE;
    anim_set_start(start);
    anim_start();
    anim_update_type = ANIM_NORMAL;
    yaw_state = YAW_BOUNDED;
    yaw_limit = 350.0f;
    yaw_percent = 14.0f;
    facing_mode = 7;
    facing_threshold = 8.0f;
    physics_type = PHYS_LOCKED;
    timer_set(0, 0.7f);
    timer_set(1, 0.2f);
    velocity[0] = cur.velocity_x;
    velocity[1] = 0.0f;
    velocity[2] = cur.velocity_z;
    entry_speed = sqrtf(velocity[0] * velocity[0] + velocity[2] * velocity[2]);
    if (140.0f < entry_speed) sfx_count++;
    if (heading_from_velocity(velocity, &heading)) {
        target_yaw = mlNormalizeAngle(heading);
        target_yaw_set = 1;
    }
    phase = 0;
}
static void crouch_update(void) {
    int next = 0;
    float mapped, err;
    timer_decrement(0);
    timer_decrement(1);
    mapped = ml_map_f(timer_get(0), 0.0f, 0.3f, 0.0f, entry_speed);
    target_speed = mapped;
    if (220.0f < mapped) puff_count++;
    if (160.0f < mapped) sfx_count++;
    err = mlAbsF(mlDiffDegF(yaw_ideal, yaw_deg));
    switch (phase) {
    case 0:
        if (mapped != 0.0f) break;
        timer_set(2, 2.0f);
        phase = 1;
        break;
    case 1:
        if (err != 0.0f) phase_turn();
        else {
            timer_decrement(2);
            if (timer_zero(2)) phase_noinput();
        }
        break;
    case 2:
        if (err != 0.0f) phase_turn();
        else if (ctrl.playback_type == ANIM_STOPPED) phase_recover();
        break;
    case 4:
        scale_turn(err);
        footsteps();
        if (err != 0.0f) break;
        if ((double)anim_store.timer <= 0.5) anim_set_subrange(0.0f, 0.5f);
        else anim_set_subrange(0.0f, 1.0f);
        ctrl.playback_type = 1;
        phase = 3;
        break;
    case 3:
        scale_turn(err);
        footsteps();
        if (err != 0.0f) {
            anim_set_subrange(0.0f, 1.0f);
            ctrl.playback_type = ANIM_LOOP;
            phase = 4;
        } else if (ctrl.playback_type == ANIM_STOPPED) {
            yaw_set_ideal(yaw_deg);
            phase_recover();
        }
        break;
    default:
        break;
    }
    if (cur.slide) next = BS_SLIDE;
    if (cur.should_fall) next = BS_FALL;
    next = crouch_transitions(next);
    if (next == BS_IDLE && timer_nonzero(1)) next = 0;
    if (cur.in_water) next = BS_SWIM;
    set_state(next);
}

static void load(const CrouchInput *in) { cur = *in; (void)cur.zone_position; }

int banjo_crouch_input_size(void) { return (int)sizeof(CrouchInput); }
int banjo_crouch_view_size(void) { return (int)sizeof(CrouchView); }

void banjo_crouch_reset(float yaw, float ideal) {
    memset(&cur, 0, sizeof cur);
    target_speed = target_yaw = entry_speed = 0.f;
    target_yaw_set = physics_type = 0;
    yaw_limit = yaw_percent = yaw_unbounded = facing_threshold = 0.f;
    yaw_state = facing_mode = 0;
    memset(timer_value, 0, sizeof timer_value);
    memset(timer_last, 0, sizeof timer_last);
    phase = state = prev_state = requested = active = anim_update_type = 0;
    sfx_count = puff_count = footstep_count = last_footstep = 0;
    anim_starts = fidget = buzzer = item_use = 0;
    memset(&anim_store, 0, sizeof anim_store);
    memset(&ctrl, 0, sizeof ctrl);
    ctrl.animation = &anim_store;
    ensure_acos();
    yaw_set(yaw);
    yaw_set_ideal(ideal);
}

int banjo_crouch_select(const CrouchInput *in) {
    int next;
    load(in);
    if (cur.context == BS_IDLE) return stand_select();
    if (cur.context == BS_CREEP || cur.context == BS_SLOW) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_MUD;
        return interrupt_tail(next);
    }
    if (cur.context == BS_WALK) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_MUD;
        if (cur.skid && 125.0f < cur.horizontal_velocity) next = BS_SKID;
        return interrupt_tail(next);
    }
    if (cur.context == BS_FAST) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_MUD;
        if (cur.skid && 125.0f < cur.horizontal_velocity) next = BS_SKID;
        if (cur.should_fall) next = BS_FALL;
        if (held(BTN_Z)) next = BS_CROUCH;
        next = attack_from_speed(next);
        if (pressed(BTN_A)) next = jump_type();
        if (cur.slide) next = BS_SLIDE;
        next = scripted(next);
        if (cur.in_water) next = BS_SWIM;
        return next;
    }
    if (cur.context == BS_MUD) {
        next = 0;
        if (!cur.dangerous_ground) next = BS_SLOW;
        if (!cur.zone) next = BS_IDLE;
        return interrupt_tail(next);
    }
    return cur.provisional;
}

void banjo_crouch_enter(const CrouchInput *in) {
    load(in);
    prev_state = cur.prev_state;
    state = BS_CROUCH;
    active = 1;
    requested = BS_CROUCH;
    anim_store.index = (uint32_t)cur.prev_anim;
    crouch_init();
    post_frame();
}

void banjo_crouch_step(const CrouchInput *in) {
    int became_idle;
    load(in);
    requested = 0;
    became_idle = 0;
    if (state == BS_CROUCH && active) {
        crouch_update();
        became_idle = state == BS_IDLE;
    }
    if ((state == BS_CROUCH && active) || became_idle) post_frame();
}

void banjo_crouch_view(CrouchView *out) {
    memset(out, 0, sizeof *out);
    out->state = state;
    out->requested = requested;
    out->phase = phase;
    out->active = active;
    out->target_speed = target_speed;
    out->target_yaw = target_yaw;
    out->entry_speed = entry_speed;
    out->target_yaw_set = target_yaw_set;
    out->yaw = yaw_deg;
    out->ideal_yaw = yaw_ideal;
    out->timer0 = timer_value[0];
    out->timer1 = timer_value[1];
    out->timer2 = timer_value[2];
    out->anim_index = (int32_t)anim_store.index;
    out->anim_timer = anim_store.timer;
    out->anim_ctrl_timer = ctrl.timer;
    out->anim_duration = ctrl.animation_duration;
    out->anim_blend = anim_store.duration;
    out->anim_start = ctrl.start;
    out->sub_start = ctrl.subrange_start;
    out->sub_end = ctrl.subrange_end;
    out->playback = ctrl.playback_type;
    out->direction = ctrl.playback_direction;
    out->smooth = ctrl.smooth_transition;
    out->default_start = ctrl.default_start;
    out->physics_type = physics_type;
    out->yaw_mode = facing_mode;
    out->yaw_state = yaw_state;
    out->yaw_limit = yaw_limit;
    out->yaw_percent = yaw_percent;
    out->anim_update_type = anim_update_type;
    out->sfx_count = sfx_count;
    out->puff_count = puff_count;
    out->footstep_count = footstep_count;
    out->last_footstep = last_footstep;
    out->anim_starts = anim_starts;
    out->fidget = fidget;
    out->buzzer = buzzer;
    out->item_use = item_use;
}
