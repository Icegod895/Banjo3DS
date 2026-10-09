"""Original-decomp oracle for the host crouch reference.

Extracted Rare functions keep their bodies. Gameplay around them is an explicit
input record: abilities, items, buttons, and selector flags. Animation poses,
surface sample ids, and non-idle state inits are not simulated.
"""
import ctypes as C
import functools
from pathlib import Path
import re
import subprocess
import tempfile

from horizontal_reference import FLAGS, ROOT

F = C.c_float


def _skip_trivia(text, i):
    n = len(text)
    while i < n:
        if text.startswith('//', i):
            nl = text.find('\n', i)
            i = n if nl < 0 else nl + 1
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
        elif text[i] in ' \t\r\n':
            i += 1
        else:
            break
    return i


def _match_delimiter(text, i, open_ch, close_ch):
    """Return the index of the closer matching the opener at i."""
    depth = 0
    n = len(text)
    while i < n:
        if text.startswith('//', i):
            nl = text.find('\n', i)
            i = n if nl < 0 else nl + 1
            continue
        if text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
            continue
        c = text[i]
        if c == '"' or c == "'":
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == '\\' else 1
            i += 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError('Unbalanced %s for extractor' % open_ch)


def original_function(path, name):
    text = (ROOT / path).read_text()
    pattern = r'(?m)^(?:static\s+)?(?:[\w*]+\s+)+[*]*' + re.escape(name) + r'\s*\('
    for match in re.finditer(pattern, text):
        close = _match_delimiter(text, match.end() - 1, '(', ')')
        brace = _skip_trivia(text, close + 1)
        if brace < len(text) and text[brace] == '{':
            end = _match_delimiter(text, brace, '{', '}')
            return text[match.start():end + 1] + '\n'
    raise ValueError('Original function not found: %s in %s' % (name, path))


def enum_text(path, name):
    text = (ROOT / path).read_text()
    match = re.search(r'enum ' + name + r'\s*\{.*?\};', text, re.S)
    if not match:
        raise ValueError('enum not found: ' + name)
    return match.group(0) + '\n'


def _source():
    code = r'''
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef float f32;
typedef double f64;
typedef int32_t s32;
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define TRUE 1
#define FALSE 0
#define M_PI 3.14159265358979323846
#define IO_READ(addr) 0x10000003u
#define COMUSIC_2C_BUZZER 0x2c
#define _SQ2(x, y) ((x) * (x) + (y) * (y))
#define TUPLE_COPY(dst, src) { dst[0] = src[0]; dst[1] = src[1]; dst[2] = src[2]; }
#define anctrl_start(this, file, line) _anctrl_start(this, file, line)
'''
    code += enum_text('include/enums.h', 'bs_e')
    code += enum_text('include/enums.h', 'button_e')
    code += enum_text('include/enums.h', 'transformation_e')
    code += enum_text('include/enums.h', 'item_e')
    code += enum_text('include/enums.h', 'misc_flag_e')
    code += enum_text('include/enums.h', 'anctrl_direction_e')
    code += r'''
enum asset_e {
    ASSET_1_ANIM_BSCROUCH_ENTER = 0x1,
    ASSET_6F_ANIM_BSSTAND_IDLE = 0x6F,
    ASSET_10C_ANIM_BSCROUCH_IDLE = 0x10C,
    ASSET_116_ANIM_BSCROUCH_NOINPUT = 0x116
};
enum anctrl_playback_e {
    ANIMCTRL_ONCE = 1, ANIMCTRL_LOOP = 2, ANIMCTRL_STOPPED = 3, ANIMCTRL_SUBRANGE_LOOP = 4
};
enum yaw_state_e { YAW_STATE_0_NONE, YAW_STATE_1_DEFAULT, YAW_STATE_2_UNBOUNDED, YAW_STATE_3_BOUNDED };
enum baanim_update_type_e {
    BAANIM_UPDATE_0_NONE, BAANIM_UPDATE_1_NORMAL, BAANIM_UPDATE_2_SCALE_HORZ, BAANIM_UPDATE_3_SCALE_VERT
};
typedef enum {
    BA_PHYSICS_NONE, BA_PHYSICS_UNK1, BA_PHYSICS_NORMAL, BA_PHYSICS_LOCKED_ROTATION
} BaPhysicsType;
typedef struct Animation {
    u32 index; f32 timer; f32 duration;
} Animation;
typedef struct AnimCtrl {
    Animation *animation;
    f32 timer, subrange_start, subrange_end, animation_duration, transition_duration, start;
    s32 index;
    s32 playback_type, playback_direction, smooth_transition, default_start;
} AnimCtrl;
typedef struct CrouchInput {
    float dt, stick_distance, stick_angle, zone_position;
    float velocity_x, velocity_z, horizontal_velocity, target_speed;
    int32_t zone, context, prev_state, provisional, prev_anim;
    int32_t button_count[14];
    int32_t release_count[14];
    int32_t can_claw, can_roll, can_flap_flip, can_beak_barge, can_trot, can_wonderwing, can_egg;
    int32_t feather_empty, egg_empty;
    int32_t slide, should_fall, in_water, dangerous_ground, skid, fp_look;
    int32_t spring, flight, turbo, transform, notedoor, wading, timeout_flag, jiggy, boggy;
    int32_t transformation;
} CrouchInput;
typedef struct CrouchView {
    int32_t state, requested, phase, active;
    float target_speed, target_yaw, entry_speed;
    int32_t target_yaw_set;
    float yaw, ideal_yaw;
    float timer0, timer1, timer2;
    int32_t anim_index;
    float anim_timer, anim_ctrl_timer, anim_duration, anim_blend, anim_start;
    float sub_start, sub_end;
    int32_t playback, direction, smooth, default_start;
    int32_t physics_type, yaw_mode, yaw_state;
    float yaw_limit, yaw_percent;
    int32_t anim_update_type;
    int32_t sfx_count, puff_count, footstep_count, last_footstep;
    int32_t anim_starts, fidget, buzzer, item_use;
} CrouchView;
static CrouchInput cur;
static Animation anim_store;
static AnimCtrl ctrl_store;
AnimCtrl *playerAnimCtrl = &ctrl_store;
f32 D_8037D400; u8 D_8037D404;
s32 D_8037D160, D_8037D164, D_8037D540; u8 D_8037D544;
f32 yaw_deg, yawIdeal_deg, D_8037C69C, D_8037C6A0, D_8037C6A4, D_8037C6B4;
s32 yawUpdateState, D_8037C6B0;
struct { f32 value[8]; f32 last[8]; } s_batimer;
struct { s32 pressed_count[BUTTON_max]; s32 released_count[BUTTON_max]; } bakey;
static u16 acos_storage[10001];
u16 *D_80276CB8;
f32 bsWalkWalkFastWalkVelocityThreshold = 225.0f;
f32 bsWalkSkidVelocity = 125.0f;
static f32 coast_target, target_yaw;
static s32 target_yaw_set, physics_type, baAnimState;
static s32 requested, active;
static s32 sfx_count, puff_count, footstep_count, last_footstep, anim_starts, fidget, buzzer, item_use;
void *bk_malloc(u32 n) { (void)n; return acos_storage; }
f32 time_getDelta(void) { return cur.dt; }
f32 bastick_distance(void) { return cur.stick_distance; }
f32 bastick_getAngleRelativeToBanjo(void) { return cur.stick_angle; }
f32 bastick_getX(void) { return 0.f; }
s32 bastick_getZone(void) { return cur.zone; }
int bainput_should_look_first_person_camera(void) { return cur.fp_look; }
enum bs_e badrone_look(void) { return BS_98_WALK_DRONE; }
enum bs_e badrone_transform(void) { return BS_98_WALK_DRONE; }
int player_getTransformation(void) { return cur.transformation; }
int player_isSliding(void) { return cur.slide; }
int player_shouldFall(void) { return cur.should_fall; }
int player_inWater(void) { return cur.in_water; }
int player_isOnDangerousGround(void) { return cur.dangerous_ground; }
int can_claw(void) { return cur.can_claw; }
int can_roll(void) { return cur.can_roll; }
int can_flap_flip(void) { return cur.can_flap_flip; }
int can_beak_barge(void) { return cur.can_beak_barge; }
int can_trot(void) { return cur.can_trot; }
int can_wonderwing(void) { return cur.can_wonderwing; }
int can_egg(void) { return cur.can_egg; }
int baflag_isTrue(int n) {
    switch (n) {
    case BA_FLAG_1_ON_FLIGHT_PAD: return cur.flight;
    case BA_FLAG_2_ON_SPRING_PAD: return cur.spring;
    case BA_FLAG_6: return cur.timeout_flag;
    case BA_FLAG_7_TOUCHING_JIGGY: return cur.jiggy;
    case BA_FLAG_E_TOUCHING_WADING_BOOTS: return cur.wading;
    case BA_FLAG_10_TOUCHING_TURBO_TRAINERS: return cur.turbo;
    case BA_FLAG_14_LOSE_BOGGY_RACE: return cur.boggy;
    case BA_FLAG_19_SHOULD_TRANSFORM: return cur.transform;
    case BA_FLAG_1A_OPEN_NOTEDOOR: return cur.notedoor;
    default: return 0;
    }
}
void baflag_clear(int n) { (void)n; }
int item_empty(enum item_e id) {
    if (id == ITEM_10_GOLD_FEATHER) return cur.feather_empty;
    if (id == ITEM_D_EGGS) return cur.egg_empty;
    return 1;
}
void item_adjustByDiffWithHud(enum item_e id, int n) { (void)id; (void)n; }
void item_dec(enum item_e id) { (void)id; item_use++; }
void coMusicPlayer_playMusic(int id, int volume) { (void)id; (void)volume; buzzer++; }
void basfx_80299AAC(void) { sfx_count++; }
void func_802929F8(void) { puff_count++; }
void func_8029AE74(s32 id) { footstep_count++; last_footstep = id; }
void func_802900B4(void) { fidget++; }
int bsclimb_inSet(s32 id) { (void)id; return 0; }
void climb_release(void) {}
u32 anim_getIndex(Animation *a) { return a->index; }
void anim_setIndex(Animation *a, u32 id) { a->index = id; }
f32 anim_getTimer(Animation *a) { return a->timer; }
void anim_setTimer(Animation *a, f32 t) { a->timer = t; }
f32 anim_getDuration(Animation *a) { return a->duration; }
void anim_setDuration(Animation *a, f32 t) { a->duration = t; }
void anim_resetSmooth(Animation *a) { (void)a; }
void anim_resetNow(Animation *a) { (void)a; }
void baanim_setUpdateType(enum baanim_update_type_e t) {
    baAnimState = t;
    if (t != BAANIM_UPDATE_0_NONE && t != BAANIM_UPDATE_1_NORMAL) abort();
}
AnimCtrl *baanim_getAnimCtrlPtr(void) { return playerAnimCtrl; }
void baphysics_set_type(BaPhysicsType t) { physics_type = t; }
void baphysics_set_target_horizontal_velocity(f32 v) { coast_target = v; }
f32 baphysics_get_target_horizontal_velocity(void) { return cur.target_speed; }
void baphysics_get_velocity(f32 *v) { v[0] = cur.velocity_x; v[1] = 0.f; v[2] = cur.velocity_z; }
'''
    for name in ('ml_max_f', 'ml_min_f', 'mlAbsF', 'ml_clamp_f', 'mlNormalizeAngle',
                 'mlDiffDegF', 'ml_map_f', 'ml_mapAbsRange_f', 'ml_acosf', 'func_8025801C', 'ml_init'):
        code += original_function('src/core1/ml.c', name)
    code += r'''
void baphysics_set_target_yaw(f32 yaw) { target_yaw = mlNormalizeAngle(yaw); target_yaw_set = 1; }
'''
    for name in ('batimer_decrement', 'batimer_get', 'batimer_set', 'batimer_isNonzero', 'batimer_isZero'):
        code += original_function('src/core2/batimer.c', name)
    for name in ('__yaw_update_limitless', '__yaw_update_limited', 'yaw_update', 'yaw_setUpdateState',
                 'yaw_setIdeal', 'yaw_set', 'yaw_get', 'yaw_getIdeal', 'yaw_setVelocityBounded'):
        code += original_function('src/core2/yaw.c', name)
    for name in ('func_8029932C', 'func_80299338', 'func_802993C8', 'func_8029957C'):
        code += original_function('src/core2/code_12360.c', name)
    code += r'''
void anctrl_setPlaybackType(AnimCtrl *this, enum anctrl_playback_e arg1);
void anctrl_setDuration(AnimCtrl *this, f32 arg1);
void anctrl_setTransitionDuration(AnimCtrl *this, f32 arg1);
void anctrl_setDirection(AnimCtrl *this, s32 arg1);
void anctrl_setSmoothTransition(AnimCtrl *this, s32 arg1);
void anctrl_setSubRange(AnimCtrl *this, f32 start, f32 end);
void anctrl_setStart(AnimCtrl *this, f32 start_position);
void anctrl_setIndex(AnimCtrl *this, enum asset_e index);
void _anctrl_start(AnimCtrl *this, char *file, s32 line);
Animation *anctrl_getAnimPtr(AnimCtrl *this);
f32 anctrl_getDuration(AnimCtrl *this);
f32 anctrl_getTransistionDuration(AnimCtrl *this);
f32 anctrl_getAnimTimer(AnimCtrl *this);
enum anctrl_playback_e anctrl_getPlaybackType(AnimCtrl *this);
s32 anctrl_isStopped(AnimCtrl *this);
int anctrl_isAt(AnimCtrl *this, f32 arg1);
'''
    anctrl_names = (
        'anctrl_80286F90', '__anctrl_update_looped', 'func_802870E0', 'func_802871A4', 'anctrl_update',
        'anctrl_setIndex', 'anctrl_getAnimPtr', 'anctrl_reset', '__anctrl_gotoStart', '_anctrl_start',
        'anctrl_setPlaybackType', 'anctrl_setDirection', 'anctrl_setSmoothTransition', 'anctrl_setDuration',
        'anctrl_setTransitionDuration', 'anctrl_setSubRange', 'anctrl_setStart', 'anctrl_getDuration',
        'anctrl_getTransistionDuration', 'anctrl_getAnimTimer', 'anctrl_getPlaybackType', 'anctrl_isStopped',
        'anctrl_isAt')
    for name in anctrl_names:
        body = original_function('src/core2/anctrl.c', name)
        if name == '_anctrl_start':
            needle = 'void _anctrl_start(AnimCtrl * this, char *file, s32 line){'
            if needle not in body:
                raise ValueError('anim start signature drifted')
            body = body.replace(needle, needle + ' anim_starts++;', 1)
        code += body
    for name in ('baanim_playForDuration_loopSmooth', 'baanim_playForDuration_once',
                 'baanim_playForDuration_onceStartingAt'):
        code += original_function('src/core2/ba/anim.c', name)
    code += original_function('src/core2/code_13A00.c', 'func_8029AD28')
    code += original_function('src/core2/code_14420.c', 'code_14420_setUpdateTypes')
    for name in ('bakey_pressed', 'bakey_held', 'bakey_released'):
        code += original_function('src/core2/bakey.c', name)
    for name in ('bainput_should_beak_barge', 'bainput_should_poop_egg', 'bainput_should_shoot_egg',
                 'bainput_should_flap_flip', 'bainput_should_trot', 'bainput_should_wonderwing'):
        code += original_function('src/core2/bainput.c', name)
    code += original_function('src/core2/code_BEF20.c', 'func_80346C10')
    code += original_function('src/core2/code_13780.c', 'bs_getPrevState')
    code += r'''
void bscrouch_init(void);
void bscrouch_end(void);
void bsstand_init(void);
enum bs_e func_802ADCD4(enum bs_e arg0);
enum bs_e bs_getTypeOfJump(void);
s32 func_8029CA94(s32 arg0);
s32 func_802B6F20(s32 arg0);
void bs_setState(s32 id) {
    if (id == 0) return;
    requested = id;
    D_8037D160 = D_8037D164;
    D_8037D164 = id;
    if (id == BS_7_CROUCH) active = 1;
    else if (id == BS_1_IDLE) { active = 0; bsstand_init(); }
    else active = 0;
}
'''
    for name in ('func_802AD6D0', 'func_802AD6FC', 'func_802AD728', 'func_802AD768', 'func_802AD7B0',
                 'bscrouch_init', 'bscrouch_update', 'bscrouch_end', 'func_802ADCD4'):
        code += original_function('src/core2/bs/crouch.c', name)
    code += original_function('src/core2/bs/stand.c', 'bsstand_init')
    code += original_function('src/core2/bs/stand.c', 'func_802B488C')
    code += original_function('src/core2/code_14420.c', 'bs_getTypeOfJump')
    code += original_function('src/core2/code_14420.c', 'func_8029CA94')
    code += original_function('src/core2/bs/walk.c', 'func_802B6F20')
    code += r'''
static void load_input(const CrouchInput *in) {
    int i;
    cur = *in;
    for (i = 0; i < BUTTON_max; i++) {
        bakey.pressed_count[i] = in->button_count[i];
        bakey.released_count[i] = in->release_count[i];
    }
}
static void post_frame(void) {
    func_802993C8();
    if (baAnimState == BAANIM_UPDATE_1_NORMAL) anctrl_update(playerAnimCtrl);
    else if (baAnimState != BAANIM_UPDATE_0_NONE) abort();
}
static int tail_from_look(int next) {
    if (cur.fp_look) next = BS_98_WALK_DRONE;
    if (cur.should_fall) next = BS_2F_FALL;
    if (bakey_held(BUTTON_Z)) next = BS_7_CROUCH;
    next = func_802B6F20(next);
    if (bakey_pressed(BUTTON_A)) next = bs_getTypeOfJump();
    if (cur.slide) next = BS_32_SLIDE;
    next = func_8029CA94(next);
    if (cur.in_water) next = BS_2D_SWIM_IDLE;
    return next;
}
int ref_input_size(void) { return (int)sizeof(CrouchInput); }
int ref_view_size(void) { return (int)sizeof(CrouchView); }
void ref_reset(float yaw, float ideal) {
    memset(&cur, 0, sizeof cur);
    memset(&anim_store, 0, sizeof anim_store);
    memset(&ctrl_store, 0, sizeof ctrl_store);
    ctrl_store.animation = &anim_store;
    playerAnimCtrl = &ctrl_store;
    memset(&s_batimer, 0, sizeof s_batimer);
    memset(&bakey, 0, sizeof bakey);
    D_8037D400 = 0; D_8037D404 = 0;
    D_8037D160 = D_8037D164 = D_8037D540 = 0; D_8037D544 = 0;
    yawUpdateState = D_8037C6B0 = 0;
    D_8037C69C = D_8037C6A0 = D_8037C6A4 = D_8037C6B4 = 0;
    coast_target = target_yaw = 0;
    target_yaw_set = physics_type = baAnimState = requested = active = 0;
    sfx_count = puff_count = footstep_count = last_footstep = 0;
    anim_starts = fidget = buzzer = item_use = 0;
    ml_init();
    yaw_set(yaw);
    yaw_setIdeal(ideal);
}
int ref_select(const CrouchInput *in) {
    int next;
    load_input(in);
    if (cur.context == BS_1_IDLE) {
        next = func_802B488C(0);
        if (cur.should_fall) next = BS_2F_FALL;
        return next;
    }
    if (cur.context == BS_1F_WALK_CREEP || cur.context == BS_2_WALK_SLOW) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_7A_WALK_MUD;
        return tail_from_look(next);
    }
    if (cur.context == BS_3_WALK) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_7A_WALK_MUD;
        if (cur.skid && bsWalkSkidVelocity < cur.horizontal_velocity) next = BS_C_SKID;
        return tail_from_look(next);
    }
    if (cur.context == BS_4_WALK_FAST) {
        next = cur.provisional;
        if (cur.dangerous_ground) next = BS_7A_WALK_MUD;
        if (cur.skid && bsWalkSkidVelocity < cur.horizontal_velocity) next = BS_C_SKID;
        if (cur.should_fall) next = BS_2F_FALL;
        if (bakey_held(BUTTON_Z)) next = BS_7_CROUCH;
        next = func_802B6F20(next);
        if (bakey_pressed(BUTTON_A)) next = bs_getTypeOfJump();
        if (cur.slide) next = BS_32_SLIDE;
        next = func_8029CA94(next);
        if (cur.in_water) next = BS_2D_SWIM_IDLE;
        return next;
    }
    if (cur.context == BS_7A_WALK_MUD) {
        next = 0;
        if (!cur.dangerous_ground) next = BS_2_WALK_SLOW;
        if (!cur.zone) next = BS_1_IDLE;
        return tail_from_look(next);
    }
    return cur.provisional;
}
void ref_enter(const CrouchInput *in) {
    load_input(in);
    D_8037D160 = cur.prev_state;
    D_8037D164 = BS_7_CROUCH;
    active = 1;
    requested = BS_7_CROUCH;
    anim_store.index = (u32)cur.prev_anim;
    bscrouch_init();
    post_frame();
}
void ref_step(const CrouchInput *in) {
    int became_idle;
    load_input(in);
    requested = 0;
    became_idle = 0;
    if (D_8037D164 == BS_7_CROUCH && active) {
        bscrouch_update();
        became_idle = D_8037D164 == BS_1_IDLE;
    }
    if ((D_8037D164 == BS_7_CROUCH && active) || became_idle) post_frame();
}
void ref_view(CrouchView *out) {
    memset(out, 0, sizeof *out);
    out->state = D_8037D164;
    out->requested = requested;
    out->phase = D_8037D404;
    out->active = active;
    out->target_speed = coast_target;
    out->target_yaw = target_yaw;
    out->entry_speed = D_8037D400;
    out->target_yaw_set = target_yaw_set;
    out->yaw = yaw_deg;
    out->ideal_yaw = yawIdeal_deg;
    out->timer0 = s_batimer.value[0];
    out->timer1 = s_batimer.value[1];
    out->timer2 = s_batimer.value[2];
    out->anim_index = (int)anim_store.index;
    out->anim_timer = anim_store.timer;
    out->anim_ctrl_timer = ctrl_store.timer;
    out->anim_duration = ctrl_store.animation_duration;
    out->anim_blend = anim_store.duration;
    out->anim_start = ctrl_store.start;
    out->sub_start = ctrl_store.subrange_start;
    out->sub_end = ctrl_store.subrange_end;
    out->playback = ctrl_store.playback_type;
    out->direction = ctrl_store.playback_direction;
    out->smooth = ctrl_store.smooth_transition;
    out->default_start = ctrl_store.default_start;
    out->physics_type = physics_type;
    out->yaw_mode = D_8037C6B0;
    out->yaw_state = yawUpdateState;
    out->yaw_limit = D_8037C6A0;
    out->yaw_percent = D_8037C6A4;
    out->anim_update_type = baAnimState;
    out->sfx_count = sfx_count;
    out->puff_count = puff_count;
    out->footstep_count = footstep_count;
    out->last_footstep = last_footstep;
    out->anim_starts = anim_starts;
    out->fidget = fidget;
    out->buzzer = buzzer;
    out->item_use = item_use;
}
'''
    return code


class Input(C.Structure):
    _fields_ = [
        ('dt', F), ('stick_distance', F), ('stick_angle', F), ('zone_position', F),
        ('velocity_x', F), ('velocity_z', F), ('horizontal_velocity', F), ('target_speed', F),
        ('zone', C.c_int32), ('context', C.c_int32), ('prev_state', C.c_int32),
        ('provisional', C.c_int32), ('prev_anim', C.c_int32),
        ('button_count', C.c_int32 * 14), ('release_count', C.c_int32 * 14),
        ('can_claw', C.c_int32), ('can_roll', C.c_int32), ('can_flap_flip', C.c_int32),
        ('can_beak_barge', C.c_int32), ('can_trot', C.c_int32), ('can_wonderwing', C.c_int32),
        ('can_egg', C.c_int32), ('feather_empty', C.c_int32), ('egg_empty', C.c_int32),
        ('slide', C.c_int32), ('should_fall', C.c_int32), ('in_water', C.c_int32),
        ('dangerous_ground', C.c_int32), ('skid', C.c_int32), ('fp_look', C.c_int32),
        ('spring', C.c_int32), ('flight', C.c_int32), ('turbo', C.c_int32),
        ('transform', C.c_int32), ('notedoor', C.c_int32), ('wading', C.c_int32),
        ('timeout_flag', C.c_int32), ('jiggy', C.c_int32), ('boggy', C.c_int32),
        ('transformation', C.c_int32)]


class View(C.Structure):
    _fields_ = [
        ('state', C.c_int32), ('requested', C.c_int32), ('phase', C.c_int32), ('active', C.c_int32),
        ('target_speed', F), ('target_yaw', F), ('entry_speed', F), ('target_yaw_set', C.c_int32),
        ('yaw', F), ('ideal_yaw', F), ('timer0', F), ('timer1', F), ('timer2', F),
        ('anim_index', C.c_int32),
        ('anim_timer', F), ('anim_ctrl_timer', F), ('anim_duration', F), ('anim_blend', F), ('anim_start', F),
        ('sub_start', F), ('sub_end', F),
        ('playback', C.c_int32), ('direction', C.c_int32), ('smooth', C.c_int32), ('default_start', C.c_int32),
        ('physics_type', C.c_int32), ('yaw_mode', C.c_int32), ('yaw_state', C.c_int32),
        ('yaw_limit', F), ('yaw_percent', F), ('anim_update_type', C.c_int32),
        ('sfx_count', C.c_int32), ('puff_count', C.c_int32), ('footstep_count', C.c_int32),
        ('last_footstep', C.c_int32), ('anim_starts', C.c_int32), ('fidget', C.c_int32),
        ('buzzer', C.c_int32), ('item_use', C.c_int32)]


VIEW_FIELDS = [name for name, _ in View._fields_]


def bind(lib, prefix):
    # getattr caches the function object. Subscripting a CDLL returns a new
    # pointer, so argtypes set that way never reach the calls.
    reset = getattr(lib, prefix + 'reset')
    select = getattr(lib, prefix + 'select')
    enter = getattr(lib, prefix + 'enter')
    step = getattr(lib, prefix + 'step')
    view = getattr(lib, prefix + 'view')
    reset.argtypes = [F, F]
    select.argtypes = [C.POINTER(Input)]
    select.restype = C.c_int32
    enter.argtypes = [C.POINTER(Input)]
    step.argtypes = [C.POINTER(Input)]
    view.argtypes = [C.POINTER(View)]
    getattr(lib, prefix + 'input_size').restype = C.c_int32
    getattr(lib, prefix + 'view_size').restype = C.c_int32


@functools.lru_cache(maxsize=2)
def library(opt):
    temporary = tempfile.TemporaryDirectory(prefix='banjo-crouch-oracle-')
    path = Path(temporary.name) / 'oracle.c'
    path.write_text(_source())
    so = path.with_suffix('.so')
    result = subprocess.run(
        ['cc', *FLAGS, opt, '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
         '-Wno-unused-variable', '-Wno-unused-parameter', '-Wno-sign-compare',
         '-Wno-unused-but-set-variable', '-shared', '-fPIC', str(path), '-lm', '-o', str(so)],
        capture_output=True, text=True)
    if result.returncode:
        Path('/tmp/crouch-oracle.c').write_text(path.read_text())
        raise RuntimeError(result.stderr)
    if result.stderr:
        raise RuntimeError(result.stderr)
    lib = C.CDLL(str(so))
    bind(lib, 'ref_')
    lib.temporary = temporary
    return lib
