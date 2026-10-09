#include "player_runtime.h"
#include <math.h>
#include <string.h>

static void firstPersonZeroVelocity(PlayerRuntime *s) {
    memset(s->horizontal.velocity,0,sizeof(s->horizontal.velocity));
    memset(s->horizontal.target,0,sizeof(s->horizontal.target));
    s->horizontal.target_speed=0.0f;
}

void playerRuntimeFirstPersonUpdate(PlayerRuntime *s,FpCamera *camera,const FpClock *clock,
    const FpLookInput *input,const float internal_position[3],const float internal_rotation[3]) {
    if(!s || !camera || !clock || !input || !internal_position || !internal_rotation)return;
    const bool was=s->first_person.active!=0;
    const bool update_yaw=was && camera->state==FP_IDLE;
    fp_look_update(&s->first_person,camera,clock,input,internal_position,internal_rotation);
    if(update_yaw) {
        s->motion.actor.yaw=s->first_person.ideal_yaw;
        s->horizontal.ideal_yaw=s->first_person.ideal_yaw;
        s->horizontal.visible_yaw=s->first_person.ideal_yaw;
        s->horizontal.heading=s->first_person.ideal_yaw;
    }
    if(s->first_person.requested==152) {
        /* bsDroneLook_init requests the normal 006F loop and resets the
         * existing gait pose; the packet/evaluator remains the shared path. */
        s->locomotion.gait=BANJO_GAIT_IDLE;
        s->gait.initialized=false;
    }
    /* Entry, active frames, and the exit edge all consume movement/jump for
     * this frame.  The original DroneLook init also clears velocity. */
    s->first_person_blocks=was || s->first_person.active ||
        s->first_person.requested==152 || s->first_person.requested==1;
    if(s->first_person_blocks)firstPersonZeroVelocity(s);
}

bool playerRuntimeFirstPersonActive(const PlayerRuntime *s) {
    return s && s->first_person.active!=0;
}
bool playerRuntimeFirstPersonBlocks(const PlayerRuntime *s) {
    return s && s->first_person_blocks;
}

void playerRuntimeMoveStepped(PlayerRuntime *s,float x,float y,float yaw,float dt,
                       bool jumpPressed,bool cameraMode,const FloorVertex *v,const FloorTriangle *t,size_t n,
                       BanjoCandidateObserver observe,void *context,const MovementOverlay *overlay,
                       PlayerMotionStep step,void *step_context) {
    if(!s || !isfinite(dt) || dt<0 || !isfinite(x) || !isfinite(y) || !isfinite(yaw))return;
    dt=fminf(dt,.05f);
    s->events=0;s->accepted=false;s->speed=0;
    if(dt==0)return;
    if(!s->horizontalInitialized) {
        banjo_horizontal_init(&s->horizontal,s->motion.actor.yaw);
        s->horizontalInitialized=true;
    }
    BanjoHorizontal *h=&s->horizontal;
    float stick[2]={0},direction[2];
    if(!cameraMode)movementNormalize(x,y,stick);
    float magnitude=banjo_horizontal_magnitude(stick[0],stick[1]);
    movementDirection(stick[0],stick[1],yaw,direction);
    float heading=magnitude>0?atan2f(direction[0],direction[1])/0.017453292519943295f:h->intent.desired_yaw;
    banjo_horizontal_intent(h,magnitude,heading);
    MovementActor before=s->motion.actor;
    bool wasGrounded=s->motion.grounded;
    if(wasGrounded) {
        BanjoGait old=(BanjoGait)s->locomotion.gait;
        BanjoHorizontalMetrics previous=banjo_horizontal_metrics(h,dt);
        BanjoGait next=banjo_gait_motion_select(&s->locomotion,&previous,dt);
        /* Original stand update starts movement for the NEXT physics frame.
         * Takeoff explicitly replaces this target with current stick intent. */
        if(old==BANJO_GAIT_IDLE && next!=BANJO_GAIT_IDLE)h->target_speed=0;
    }
    s->events=step?step(step_context,&s->motion,h,dt,jumpPressed,cameraMode):
        banjo_jump_step_overlay(&s->motion,h,dt,jumpPressed,cameraMode,v,t,n,observe,context,overlay);
    float dx=s->motion.actor.x-before.x,dz=s->motion.actor.z-before.z;
    if(s->events&BANJO_JUMP_RECOVERED) {
        /* Diagnostic teleport is neither accepted movement nor stored momentum. */
        banjo_horizontal_init(h,s->motion.actor.yaw);dx=dz=0;
    }
    banjo_horizontal_accept(h,dx,dz);
    s->metrics=banjo_horizontal_metrics(h,dt);
    s->accepted=wasGrounded && s->motion.grounded && (s->events&BANJO_JUMP_MOVED) &&
                !(s->events&(BANJO_JUMP_TAKEOFF|BANJO_JUMP_LANDED|BANJO_JUMP_RECOVERED));
    s->speed=s->accepted?s->metrics.accepted_speed:0;
    /* Preserve M4.6 contact-frame idle handoff; input selects gait next frame. */
    if(s->events&(BANJO_JUMP_LANDED|BANJO_JUMP_RECOVERED)) {
        s->locomotion.gait=BANJO_GAIT_IDLE;s->locomotion.downshift_remaining=0;
    }
}
void playerRuntimeMoveOverlay(PlayerRuntime *s,float x,float y,float yaw,float dt,
    bool jump,bool cameraMode,const FloorVertex *v,const FloorTriangle *t,size_t n,
    BanjoCandidateObserver observe,void *context,const MovementOverlay *overlay) {
    playerRuntimeMoveStepped(s,x,y,yaw,dt,jump,cameraMode,v,t,n,observe,context,overlay,NULL,NULL);
}
void playerRuntimeMoveObserved(PlayerRuntime *s,float x,float y,float yaw,float dt,
    bool jumpPressed,bool cameraMode,const FloorVertex *v,const FloorTriangle *t,size_t n,
    BanjoCandidateObserver observe,void *context) {
    playerRuntimeMoveOverlay(s,x,y,yaw,dt,jumpPressed,cameraMode,v,t,n,observe,context,NULL);
}
void playerRuntimeMove(PlayerRuntime *s,float x,float y,float yaw,float dt,
                       bool jumpPressed,bool cameraMode,const FloorVertex *v,const FloorTriangle *t,size_t n) {
    playerRuntimeMoveObserved(s,x,y,yaw,dt,jumpPressed,cameraMode,v,t,n,NULL,NULL);
}
static bool crouch_animate_none(PlayerRuntime *s,const uint8_t *packet,size_t size,float dt) {
    (void)s;(void)packet;(void)size;(void)dt;return false;
}
static PlayerCrouchAnimateFn crouch_animate_fn=crouch_animate_none;
void playerRuntimeSetCrouchAnimate(PlayerCrouchAnimateFn fn){crouch_animate_fn=fn?fn:crouch_animate_none;}
bool playerRuntimeAnimate(PlayerRuntime *s,const uint8_t *packet,size_t size,float dt) {
    if(!s || !isfinite(dt) || dt<0)return false;
    if(crouch_animate_fn(s,packet,size,dt))return true;
    if(!s->gait.initialized && !banjo_gait_update(&s->gait,packet,size,false,0,0))return false;
    if(!s->motion.grounded) {
        if(!s->jumpActive) {
            if(!banjo_jump_animation_begin(&s->jump,s->gait.pose.bones,BANJO_CLIP_JUMP,1.9f))return false;
            s->jumpActive=true;
        }
        return banjo_jump_animation_step(&s->jump,packet,size,dt);
    }
    if(s->jumpActive) {
        /* Freeze the last actually evaluated jump/mixed pose, not a freshly
         * sampled jump target. Same handoff as the M4.6B contact contract. */
        banjo_jump_animation_land(&s->jump,false,0);
        memcpy(&s->gait.pose,&s->jump.pose,sizeof(s->gait.pose));
        memcpy(s->gait.source,s->jump.source,sizeof(s->gait.source));
        s->gait.phase=s->jump.phase;s->gait.factor=s->jump.factor;
        s->gait.gait=BANJO_GAIT_IDLE;
        s->gait.initialized=true;s->jumpActive=false;
    }
    BanjoGait next=(BanjoGait)s->locomotion.gait;
    return banjo_gait_update_selected(&s->gait,packet,size,next,
        banjo_gait_motion_duration(next,s->metrics.physics_speed),dt);
}
bool playerRuntimeWriteVertices(const PlayerRuntime *s,const uint8_t *packet,void *vertices,
                                size_t total,size_t first,size_t count,size_t stride) {
    if(!s || !packet || !vertices || stride<12 || count!=2085 || first>total || count>total-first)return false;
    const BanjoPose *pose=s->jumpActive?&s->jump.pose:&s->gait.pose;
    const uint8_t *corners=packet+36+960+5784;
    for(size_t i=0;i<count;i++) {
        unsigned load=(unsigned)corners[2*i]*256+corners[2*i+1];
        memcpy((uint8_t *)vertices+(first+i)*stride,pose->xyz[load],12);
    }
    return true;
}
