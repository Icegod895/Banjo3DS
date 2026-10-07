#include "ground.h"
#include <string.h>

int bg_state_update(BgState *s) {
    if(!s->falling && 60.0f < s->position[1]-s->floor_height) {
        s->falling=1;
        return 1;
    }
    return 0;
}

void bg_candidate(BgState *s,const float horizontal_velocity[2],float dt,BgFrame *f) {
    memset(f,0,sizeof(*f));
    memcpy(f->previous,s->position,sizeof(f->previous));
    f->previous_grounded=s->grounded;
    /* physics.c __baphysics_update_normal: vertical tail, in source order. */
    s->vertical_velocity=s->vertical_velocity+dt*(-2700.0f);
    if(s->vertical_velocity < -4000.0f)s->vertical_velocity=-4000.0f;
    float delta[3]={horizontal_velocity[0],0.0f,horizontal_velocity[1]};
    delta[1]=delta[1]+s->vertical_velocity;
    for(int i=0;i<3;i++) {
        delta[i]*=dt;
        f->candidate[i]=s->position[i]+delta[i];
        /* C4B0 subtracts actual float32 endpoints, not the pre-add delta. */
        f->requested[i]=f->candidate[i]-f->previous[i];
    }
}

void bg_resolve(BgState *s,BgFrame *f,float height,const float normal[3]) {
    memcpy(f->normal,normal,sizeof(f->normal));
    s->floor_height=height;
    s->grounded=0;
    if(!(normal[1] < 0.432)) {
        if(f->candidate[1] <= height) {
            f->candidate[1]=height;s->grounded=1;
        } else if(f->previous_grounded && f->requested[1] < 0.0f) {
            if(normal[1] < 0.9) {
                if(f->candidate[1] < height+30.0f) {
                    f->candidate[1]=height;s->grounded=1;
                }
            } else if(f->candidate[1] < height+5.0f) {
                f->candidate[1]=height;s->grounded=1;
            }
        }
    }
    memcpy(s->position,f->candidate,sizeof(s->position));
    /* C4B0 ordinary post-collision branch. Body-forced ground is out of scope. */
    if(s->grounded && s->vertical_velocity < 0.0f)s->vertical_velocity=-1.0f;
}

int bg_query_resolve(BgState *s,BgFrame *f,BqFloorState *floor,
    const BqModel *opa,const BqModel *xlu,unsigned parity,BgFloorQuery query) {
    int result=query(floor,opa,xlu,f->candidate,56.0f,0x400000u,parity);
    if(result!=1)return result;
    bg_resolve(s,f,floor->height,floor->normal);
    return 1;
}
