#include "gait_motion.h"
#include <math.h>

BanjoGait banjo_gait_motion_select(BanjoGaitMotion *s,const BanjoHorizontalMetrics *m,float dt) {
    int zone=m->magnitude<=.12f?0:m->magnitude<=.20f?1:m->magnitude<=.50f?2:m->magnitude<=.75f?3:4;
    BanjoGait old=(BanjoGait)s->gait,next=old;
    float speed=m->physics_speed;
    /* bs/walk.c: bswalk_*_update, baphysics_is_slower_than uses <=.
     * Original .3 s WALK/FAST downshift timer; no M4.5 speed/150 hysteresis. */
    s->downshift_remaining=fmaxf(0,s->downshift_remaining-dt);
    switch(old) {
        case BANJO_GAIT_IDLE: next=(BanjoGait)zone;break;
        case BANJO_GAIT_CREEP:
            if(zone==0 && speed<=1)next=BANJO_GAIT_IDLE;
            else if(zone>=2)next=(BanjoGait)zone;
            break;
        case BANJO_GAIT_SLOW:
            if(zone==0 && speed<=3)next=BANJO_GAIT_IDLE;
            else if(zone==1 || zone>=3)next=(BanjoGait)zone;
            break;
        case BANJO_GAIT_WALK:
            if(zone<=2 && speed<=150 && s->downshift_remaining==0)next=BANJO_GAIT_SLOW;
            else if(zone==4)next=BANJO_GAIT_FAST;
            break;
        case BANJO_GAIT_FAST:
            if(zone==0 && speed<=18)next=BANJO_GAIT_IDLE;
            else if((zone==1 || zone==2) && speed<=150)next=BANJO_GAIT_SLOW;
            else if(zone==3 && speed<=225 && s->downshift_remaining==0)next=BANJO_GAIT_WALK;
            break;
    }
    if(next!=old)s->downshift_remaining=next>=BANJO_GAIT_WALK?.3f:0;
    s->gait=(uint8_t)next;return next;
}
float banjo_gait_motion_duration(BanjoGait gait,float speed) {
    static const float ranges[][4]={{30,80,1.8f,1.2f},{80,150,1.3f,.6f},
                                  {150,225,.92f,.58f},{225,500,.54f,.44f}};
    if(gait<=BANJO_GAIT_IDLE || gait>BANJO_GAIT_FAST)return 5.5f;
    const float *r=ranges[gait-1];
    /* ba/anim.c: velocity map first, duration clamp afterwards. */
    float duration=((speed-r[0])/(r[1]-r[0]))*(r[3]-r[2])+r[2];
    return fminf(fmaxf(duration,.3f),1.5f);
}
