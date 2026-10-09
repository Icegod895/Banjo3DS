#include "player_ground.h"
#include <math.h>
#include <string.h>

void playerGroundInit(PlayerGroundState *s,const BanjoJumpMotion *m) {
    memset(s,0,sizeof(*s));
    s->phase.position[0]=m->actor.x;s->phase.position[1]=m->actor.y;s->phase.position[2]=m->actor.z;
    s->phase.vertical_velocity=m->verticalVelocity;s->phase.grounded=m->grounded;
    /* Existing spawn contact is the sole bootstrap height before the first
     * real candidate/provider call. No fabricated query or clock advance. */
    s->phase.floor_height=m->actor.y;
    s->jump_flight=false; /* Only an accepted A takeoff starts the jump path. */
}
static void remember(BanjoJumpMotion *m) {
    m->lastSafeGroundPosition[0]=m->actor.x;m->lastSafeGroundPosition[1]=m->actor.y;
    m->lastSafeGroundPosition[2]=m->actor.z;m->hasSafeGround=true;
}
static void crouch_hook_none(BanjoJumpMotion *m,BanjoHorizontal *h,float dt,bool *jump,
    int should_fall,int *lock_mode,float *facing,int *use_facing) {
    (void)m;(void)h;(void)dt;(void)jump;(void)should_fall;(void)lock_mode;(void)facing;(void)use_facing;
}
static PlayerGroundCrouchHook crouch_hook=crouch_hook_none;
void playerGroundSetCrouchHook(PlayerGroundCrouchHook hook){crouch_hook=hook?hook:crouch_hook_none;}
unsigned playerGroundStep(void *context,BanjoJumpMotion *m,BanjoHorizontal *h,
                         float dt,bool jump,bool camera_mode) {
    PlayerGroundContext *c=context;PlayerGroundState *s=c->state;
    float support;
    int lock_mode=-1,use_facing=0;
    float facing=0.0f;
    bool jump_edge=jump;
    /* Same predicate as bg_state_update, using the previous resolved floor. */
    int should_fall=60.0f < (m->actor.y-s->phase.floor_height);
    crouch_hook(m,h,dt,&jump_edge,should_fall,&lock_mode,&facing,&use_facing);
    jump=jump_edge;
    bool takeoff=m->grounded && jump && !camera_mode &&
        movementFloorOverlay(c->vertices,c->triangles,c->count,m->actor.x,m->actor.z,m->actor.y,&support,c->overlay) &&
        fabsf(support-m->actor.y)<=BANJO_JUMP_CONTACT_EPSILON;
    bool flight=s->jump_flight || takeoff;
    BgState next=s->phase;
    next.position[0]=m->actor.x;next.position[1]=m->actor.y;next.position[2]=m->actor.z;
    next.vertical_velocity=m->verticalVelocity;next.grounded=m->grounded;
    BgFrame frame={0};unsigned events=0;
    if(flight) {
        /* Existing jump's PRE-sweep candidate, proven in E.2A. Collision now
         * belongs exclusively to the original body/floor loop below. */
        s->fall_request=0;next.falling=0;
        if(takeoff) {
            remember(m);next.grounded=0;next.vertical_velocity=710;
            banjo_horizontal_takeoff(h);events|=BANJO_JUMP_TAKEOFF;
        }
        banjo_horizontal_step(h,BANJO_HORIZONTAL_AIR,dt);
        next.vertical_velocity=fmaxf(next.vertical_velocity-1350.0f*dt,-4000.0f);
        memcpy(frame.previous,next.position,sizeof(frame.previous));
        frame.previous_grounded=next.grounded;
        frame.candidate[0]=next.position[0]+h->candidate[0];
        frame.candidate[1]=next.position[1]+next.vertical_velocity*dt;
        frame.candidate[2]=next.position[2]+h->candidate[1];
        for(int k=0;k<3;k++)frame.requested[k]=frame.candidate[k]-frame.previous[k];
    } else {
        if(next.grounded)next.falling=0; /* previous-frame landing handoff */
        s->fall_request=bg_state_update(&next);
        BanjoHorizontalMode mode=next.falling?BANJO_HORIZONTAL_AIR:BANJO_HORIZONTAL_GROUND;
        if(!next.falling && lock_mode==BANJO_HORIZONTAL_LOCKED)mode=BANJO_HORIZONTAL_LOCKED;
        banjo_horizontal_step(h,mode,dt);
        bg_candidate(&next,h->velocity,dt,&frame);
    }
    /* One genuine physics proposal; no pre-body floor query or sweep. */
    c->observe(c->context,frame.candidate);
    if(*c->query_status<0)return 0;
    const BpFrameContext body={c->floor,c->body,&next,c->opa,c->xlu,c->math,c->scratch};
    if(bp_frame_resolve(&body,&frame,c->floor->frame)!=1) {
        *c->query_status=-1;return 0;
    }
    if(!m->grounded && next.grounded)events|=BANJO_JUMP_LANDED;
    if(next.position[0]!=m->actor.x || next.position[2]!=m->actor.z)events|=BANJO_JUMP_MOVED;
    m->actor.x=next.position[0];m->actor.y=next.position[1];m->actor.z=next.position[2];
    if(use_facing && !flight && !next.falling)m->actor.yaw=facing;
    else m->actor.yaw=h->visible_yaw;
    m->verticalVelocity=next.vertical_velocity;m->grounded=next.grounded!=0;
    s->jump_flight=flight && !m->grounded;
    if(m->grounded)remember(m);
    else if(m->actor.y<BANJO_JUMP_VOID_Y && m->hasSafeGround) {
        /* Unchanged diagnostic recovery support policy; not a grounded fallback. */
        float height;const float *p=m->lastSafeGroundPosition;
        if(movementFloorOverlay(c->vertices,c->triangles,c->count,p[0],p[2],p[1],&height,c->overlay)
           && fabsf(height-p[1])<=BANJO_JUMP_CONTACT_EPSILON) {
            m->actor.x=p[0];m->actor.y=p[1];m->actor.z=p[2];
            m->grounded=true;m->verticalVelocity=0;events|=BANJO_JUMP_RECOVERED;
            next.falling=0;s->jump_flight=false;
        }
    }
    s->phase=next;
    return events;
}
