#include "gait.h"
#include <math.h>
#include <string.h>

static const float boundaries[] = {0.0f,0.20f,0.50f,0.75f,1.0f};
static float strength(float speed) { return fminf(fmaxf(speed/150.0f,0.0f),1.0f); }
BanjoGait banjo_gait_select(BanjoGait current, bool accepted, float speed) {
    if(!accepted || !isfinite(speed) || speed<=0)return BANJO_GAIT_IDLE;
    float s=strength(speed);
    if(current<=BANJO_GAIT_IDLE || current>BANJO_GAIT_FAST) {
        for(int i=BANJO_GAIT_CREEP;i<BANJO_GAIT_FAST;i++)
            if(s<=boundaries[i])return (BanjoGait)i;
        return BANJO_GAIT_FAST;
    }
    /* Banjo3DS policy, NOT Rare behavior: hysteresis only between moving
     * bands, after the existing movement normalization. No second deadzone.
     * Strict comparisons retain the band at equality; allow multi-band jumps. */
    while(current<BANJO_GAIT_FAST && s>boundaries[current]+0.02f)current++;
    while(current>BANJO_GAIT_CREEP && s<boundaries[current-1]-0.02f)current--;
    return current;
}
float banjo_gait_duration(BanjoGait gait, float speed) {
    static const float durations[4][2]={{1.8f,1.2f},{1.3f,0.6f},{0.92f,0.58f},{0.54f,0.44f}};
    if(gait<=BANJO_GAIT_IDLE || gait>BANJO_GAIT_FAST)return 5.5f;
    /* Banjo3DS band mapping. Endpoints/clamp from bs/walk.c, but this is
     * acceptedSpeed/150, NOT Rare's accelerated physics-velocity mapping. */
    float u=(strength(speed)-boundaries[gait-1])/(boundaries[gait]-boundaries[gait-1]);
    u=fminf(fmaxf(u,0.0f),1.0f);
    float d=durations[gait-1][0]+(durations[gait-1][1]-durations[gait-1][0])*u;
    return fminf(fmaxf(d,0.3f),1.5f);
}
BanjoClip banjo_gait_clip(BanjoGait gait) {
    static const BanjoClip clips[]={BANJO_CLIP_IDLE,BANJO_CLIP_CREEP,BANJO_CLIP_WALK,BANJO_CLIP_RUN,BANJO_CLIP_RUN};
    return (unsigned)gait<=BANJO_GAIT_FAST?clips[gait]:BANJO_CLIP_IDLE;
}
float banjo_gait_start_phase(BanjoGait old, BanjoGait next, float phase) {
    /* Exact entry-handler rules, bs/walk.c:117,190,262,339. No foot remap. */
    if(old==next || (next==BANJO_GAIT_CREEP && old==BANJO_GAIT_SLOW) ||
       (next==BANJO_GAIT_SLOW && old==BANJO_GAIT_WALK) ||
       (next==BANJO_GAIT_WALK && (old==BANJO_GAIT_SLOW || old==BANJO_GAIT_FAST)) ||
       (next==BANJO_GAIT_FAST && old==BANJO_GAIT_WALK))return phase;
    return 0;
}
bool banjo_gait_update(BanjoGaitState *s,const uint8_t *packet,size_t size,
                       bool accepted,float speed,float dt) {
    if(!s || !isfinite(dt) || dt<0 || (size!=26234 && size!=28022) || !packet)return false;
    if(!s->initialized) {
        if(!banjo_pose_sample(packet,size,BANJO_CLIP_IDLE,0,s->pose.bones))return false;
        s->gait=BANJO_GAIT_IDLE;s->phase=0;s->factor=1;s->initialized=true;
    }
    BanjoGait next=banjo_gait_select((BanjoGait)s->gait,accepted,speed);
    if(banjo_gait_clip(next)!=banjo_gait_clip((BanjoGait)s->gait)) {
        memcpy(s->source,s->pose.bones,sizeof(s->source));
        s->phase=banjo_gait_start_phase((BanjoGait)s->gait,next,s->phase);
        s->factor=0;
    }
    /* WALK<->FAST retains phase AND any in-flight transition; rate only. */
    s->gait=(uint8_t)next;
    dt=fminf(dt,0.05f);
    float phase=s->phase+dt/banjo_gait_duration(next,speed);
    phase-=floorf(phase);
    float factor=fminf(1.0f,s->factor+dt/0.2f);
    if(!banjo_pose_sample(packet,size,banjo_gait_clip(next),phase,s->pose.bones))return false;
    banjo_pose_blend(s->pose.bones,s->source,s->pose.bones,factor);
    if(!banjo_pose_apply(packet,size,&s->pose))return false;
    s->phase=phase;s->factor=factor;
    return true;
}
