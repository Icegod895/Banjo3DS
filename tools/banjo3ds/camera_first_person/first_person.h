#ifndef BANJO_FIRST_PERSON_H
#define BANJO_FIRST_PERSON_H
#include <stdint.h>
/* Host-only original-angle camera overlay. No zone/contact/player solver. */
typedef struct {
    float position[3], rotation[3], eye[3], look[3], source[3], source_rotation[3];
    float timer;
    int32_t state;
} FpCamera;
typedef struct { float dt, gains[4]; int32_t vi; } FpClock;
enum { FP_ENTER=1, FP_IDLE=2, FP_EXIT=3, FP_DONE=4 };
enum { FP_A=1, FP_B=2, FP_CUP=4, FP_Z=8 };
/* reset preserves timer and external visibility, exactly like ncba1p_reset. */
void fp_reset(FpCamera *);
void fp_state(FpCamera *,int32_t,const float internal_position[3],const float internal_rotation[3]);
void fp_target(FpCamera *,const float eye[3],const float look[3]);
/* in/out viewport is already the underlying camera + its viewport transition.
 * visibility is a separate persistent model flag. Input camera never mutates.
 * Returns 0/no visibility setter, 1/hide, 2/show. Finite original-domain inputs. */
int fp_view(FpCamera *,const FpClock *,float viewport_position[3],float viewport_rotation[3],int32_t *visible);
typedef struct {
    float player[3], yaw, floor, vy, speed, target_speed, stick_x, stick_y;
    uint32_t buttons;
    int32_t stable_flag, zone, context, fall, slide, can_claw, can_roll, map_blocks;
} FpLookInput;
/* Ordered observer events: 1 sound, 2 animation reset/start-loop, 3 update
 * modes, 4 target speed, 5 actual velocity, 6 camera ENTER, 7 eye target,
 * 8 look target, 9 flag set, 10 ideal yaw, 11 camera EXIT, 12 flag clear.
 * Events describe service requests; they do not implement those subsystems. */
typedef struct {
    float velocity[3], target_speed, ideal_yaw, animation_duration;
    uint32_t buttons;
    int32_t active, flag, animation, animation_starts, entries, exits;
    int32_t update_types[4], sound, requested, event_count, events[16];
} FpLook;
/* Selection only: dry, safe normal ground; no scripted override/skid or mud.
 * context uses original state IDs 1/31/2/3/4; returns 0 or requested BS ID.
 * Gait phase gate open, flap-flip learned, no spring/flight pad.
 * Finite inputs; zone in [0,4], context one of the five IDs above.
 * Movement state side effects outside first-person are NOT emulated here. */
int fp_eligible(const FpCamera *,const FpLookInput *);
int fp_select(const FpCamera *,const FpLookInput *,uint32_t pressed);
/* Call once during gameplay state update BEFORE physics; returns transition
 * requests/events, not a replacement player runtime. Caller owns physics and
 * the non-look destination state's init. Water/transforms/interrupts excluded. */
void fp_look_update(FpLook *,FpCamera *,const FpClock *,const FpLookInput *,
                    const float internal_position[3],const float internal_rotation[3]);
#endif
