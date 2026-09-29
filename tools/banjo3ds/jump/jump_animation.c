#include "jump_animation.h"
#include "gait.h"
#include <math.h>
#include <string.h>

bool banjo_jump_animation_begin(BanjoJumpAnimation *s,const float source[109][10],BanjoClip clip,float duration) {
    if(!s || !source || (unsigned)clip>BANJO_CLIP_JUMP || !isfinite(duration) || duration<=0)return false;
    memmove(s->source,source,sizeof(s->source));
    memcpy(s->pose.bones,s->source,sizeof(s->source));
    s->clip=(uint8_t)clip;s->segment=0;s->factor=0;
    s->phase=clip==BANJO_CLIP_JUMP?0.3f:0;
    s->duration=clip==BANJO_CLIP_JUMP?1.9f:duration;
    s->transition=clip==BANJO_CLIP_JUMP?0.134f:0.2f;
    return true;
}
bool banjo_jump_animation_step(BanjoJumpAnimation *s,const uint8_t *packet,size_t size,float dt) {
    if(!s || !isfinite(dt) || dt<0 || !isfinite(s->duration) || s->duration<=0 ||
       !isfinite(s->transition) || s->transition<=0)return false;
    dt=fminf(dt,0.05f);
    float phase=s->phase, factor=fminf(1.0f,s->factor+dt/s->transition);
    float duration=s->duration;
    uint8_t segment=s->segment;
    if(s->clip==BANJO_CLIP_JUMP) {
        if(segment<2) {
            phase+=dt/duration;
            float end=segment==0?0.5042f:0.6667f;
            /* anctrl ONCE uses strict >. No fractional wrap and no carrying
             * leftover frame time to the next subrange. No phase restart. */
            if(phase>end){phase=end;if(segment==0)duration=4.0f;segment++;}
        }
    } else {
        phase+=dt/duration;phase-=floorf(phase);
    }
    if(!banjo_pose_sample(packet,size,s->clip,phase,s->pose.bones))return false;
    banjo_pose_blend(s->pose.bones,s->source,s->pose.bones,factor);
    if(!banjo_pose_apply(packet,size,&s->pose))return false;
    s->phase=phase;s->factor=factor;s->duration=duration;s->segment=segment;
    return true;
}
void banjo_jump_animation_land(BanjoJumpAnimation *s,bool accepted,float speed) {
    BanjoGait gait=banjo_gait_select(BANJO_GAIT_IDLE,accepted,speed);
    banjo_jump_animation_begin(s,s->pose.bones,banjo_gait_clip(gait),banjo_gait_duration(gait,speed));
}
