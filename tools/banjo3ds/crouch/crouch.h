#ifndef BANJO_CROUCH_H
#define BANJO_CROUCH_H
#include <stdint.h>

/* Host-only Rare crouch reference. No 3DS runtime, gait solver, horizontal
 * integration, camera, collision, or attack/trot/flip/barge implementation.
 * Button indices match include/enums.h button_e (Z=1, A=8, B=9, C-left=10,
 * C-down=11, C-up=12, C-right=13). bakey_released is nonzero while a button
 * has been up for one or more simulated frames, so release_count[Z] must be
 * nonzero to take the original "Z up" branch. */

enum {
    BANJO_CROUCH_IDLE = 1,
    BANJO_CROUCH_SLOW = 2,
    BANJO_CROUCH_WALK = 3,
    BANJO_CROUCH_FAST = 4,
    BANJO_CROUCH_STATE = 7,
    BANJO_CROUCH_CREEP = 0x1F,
    BANJO_CROUCH_MUD = 0x7A
};

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

int banjo_crouch_input_size(void);
int banjo_crouch_view_size(void);
/* Facing yaw and ideal yaw are degrees. Target heading stays unset. */
void banjo_crouch_reset(float yaw, float ideal);
/* Pure: does not keep selector writes. Idle runs the stand selector and then
 * the fall override. Creep, slow, and walk apply the original tail to
 * provisional. Fast applies its tail, which has no first-person check.
 * Mud starts at 0, as bswalk_mud_update does. Other contexts return provisional. */
int banjo_crouch_select(const CrouchInput *in);
/* Sets previous state, enters crouch, runs bscrouch_init, then this frame's
 * facing yaw and animation advance. */
void banjo_crouch_enter(const CrouchInput *in);
/* Crouch update, then facing yaw and animation when still crouching or when
 * this frame's request was idle. Other requests are recorded only. */
void banjo_crouch_step(const CrouchInput *in);
void banjo_crouch_view(CrouchView *out);
#endif
