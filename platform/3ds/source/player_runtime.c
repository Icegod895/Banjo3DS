#include "player_runtime.h"
#include <math.h>
#include <string.h>

void playerRuntimeMove(PlayerRuntime *s,float x,float y,float yaw,float dt,
                       bool jumpPressed,bool cameraMode,const FloorVertex *v,const FloorTriangle *t,size_t n) {
    MovementActor before=s->motion.actor;
    bool wasGrounded=s->motion.grounded;
    s->events=banjo_jump_step(&s->motion,x,y,yaw,dt,jumpPressed,cameraMode,true,v,t,n);
    /* Contact consumes the rest of the frame. Resume accepted ground-speed
     * gait selection on the next grounded movement step, never teleport speed. */
    s->accepted=wasGrounded && s->motion.grounded && (s->events&BANJO_JUMP_MOVED) &&
                !(s->events&(BANJO_JUMP_TAKEOFF|BANJO_JUMP_LANDED|BANJO_JUMP_RECOVERED));
    float dx=s->motion.actor.x-before.x,dz=s->motion.actor.z-before.z;
    s->speed=s->accepted && dt>0?sqrtf(dx*dx+dz*dz)/fminf(dt,0.05f):0;
}
bool playerRuntimeAnimate(PlayerRuntime *s,const uint8_t *packet,size_t size,float dt) {
    if(!s || !isfinite(dt) || dt<0)return false;
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
        banjo_jump_animation_land(&s->jump,s->accepted,s->speed);
        memcpy(&s->gait.pose,&s->jump.pose,sizeof(s->gait.pose));
        memcpy(s->gait.source,s->jump.source,sizeof(s->gait.source));
        s->gait.phase=s->jump.phase;s->gait.factor=s->jump.factor;
        s->gait.gait=(uint8_t)banjo_gait_select(BANJO_GAIT_IDLE,s->accepted,s->speed);
        s->gait.initialized=true;s->jumpActive=false;
    }
    return banjo_gait_update(&s->gait,packet,size,s->accepted,s->speed,dt);
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
