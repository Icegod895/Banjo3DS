#include "first_person.h"
#include <math.h>
#include <string.h>
/* Finite libultra sine polynomial. Input here is bounded by the nested ease.
 * Source constants/order: lib/ultralib/src/gu/sinf.c; no host libm sin oracle. */
static float sine(float a) {
    uint32_t bits; memcpy(&bits,&a,4); unsigned exponent=(bits>>22)&511;
    if(exponent<0xe6)return a;
    double x=a; int n=0;
    if(exponent>=0xff) {
        double dn=x*0x1.45f306dc9c883p-2;
        n=(int)(dn+(dn>=0?.5:-.5));dn=n;
        x=(x-dn*0x1.921fb50000000p+1)-dn*0x1.110b4611a6263p-25;
    }
    double square=x*x;
    double p=((0x1.5dbdf0e314bfep-19*square-0x1.9f6ffeea56814p-13)*square
              +0x1.110ed3804c2a0p-7)*square-0x1.55554bc83656dp-3;
    float r=(float)(x+(x*square)*p);return n&1?-r:r;
}
static float angle(float a) {
    if(a<0.0){a=angle(-a);a=360.0-a;}
    if(a>=360.0)a-=360.0*(int32_t)(a/360.0);
    return a;
}
static float difference(float a,float b) {
    float d=a-b;while(d>180)d-=360;while(d<=-180)d+=360;return d;
}
static float map(float v,float lo,float hi,float a,float b) {
    if(hi==lo)return b;
    float r=(((v-lo)/(hi-lo))*(b-a))+a;
    if(a<b){if(r>b)return b;if(r<a)return a;}
    else {if(r<b)return b;if(r>a)return a;}
    return r;
}
static float ease(float x){return (sine((float)(x*3.141592654+-3.141592654/2))+1)/2.0;}
static float interpolate(float t,float lo,float hi,float a,float b) {
    float u=map(t,lo,hi,0,1);u=ease(ease(u));return map(u,0,1,a,b);
}
static void copy(float *a,const float *b){memcpy(a,b,12);}
void fp_reset(FpCamera *s) {
    memset(s->position,0,72);s->state=0;
}
void fp_state(FpCamera *s,int32_t state,const float p[3],const float r[3]) {
    if(state==FP_ENTER) {
        if(s->state==FP_EXIT){copy(s->source,s->position);copy(s->source_rotation,s->rotation);}
        else {copy(s->position,p);copy(s->rotation,r);copy(s->source,p);copy(s->source_rotation,r);}
        s->timer=1;
    }
    if(state==FP_EXIT)s->timer=1;
    s->state=state;
}
void fp_target(FpCamera *s,const float eye[3],const float look[3]) {
    copy(s->eye,eye);for(int i=0;i<3;i++)s->look[i]=angle(look[i]);
}
int fp_view(FpCamera *s,const FpClock *clock,float p[3],float r[3],int32_t *visible) {
    int event=0,old=s->state;
    if(old==FP_ENTER || old==FP_EXIT) {
        s->timer-=clock->dt;if(s->timer<0)s->timer=0;
        for(int i=0;i<3;i++) {
            if(old==FP_ENTER) {
                s->position[i]=interpolate(s->timer,1,0,s->source[i],s->eye[i]);
                s->rotation[i]=angle(s->source_rotation[i]+interpolate(s->timer,.5f,0,0,difference(s->look[i],s->source_rotation[i])));
            } else {
                s->position[i]=interpolate(s->timer,1,0,s->eye[i],p[i]);
                s->rotation[i]=angle(s->look[i]+interpolate(s->timer,1,.5f,0,difference(r[i],s->look[i])));
            }
        }
        if(s->timer==0)s->state=old==FP_ENTER?FP_IDLE:FP_DONE;
        float x=s->position[0]-s->eye[0],y=s->position[1]-s->eye[1],z=s->position[2]-s->eye[2];
        int near=sqrtf(x*x+y*y+z*z)<40.f;
        if(old==FP_ENTER && near && *visible){*visible=0;event=1;}
        if(old==FP_EXIT && !near && !*visible){*visible=1;event=2;}
    } else if(old==FP_IDLE) {
        copy(s->position,s->eye);
        for(int n=0;n<clock->vi*5;n++)for(int i=0;i<2;i++) {
            float d=difference(s->look[i],s->rotation[i]);d*=0.003333*clock->gains[i];
            float max=clock->gains[i+2]*0.003333;
            if(d>max)d=max;
            if(d< -max)d= -max;
            s->rotation[i]=angle(s->rotation[i]+d);
        }
        s->rotation[2]=0;
    } else return 0;
    copy(p,s->position);copy(r,s->rotation);return event;
}
int fp_eligible(const FpCamera *c,const FpLookInput *in) {
    return !in->map_blocks && c->state!=FP_EXIT && in->stable_flag && in->vy<0;
}
int fp_select(const FpCamera *c,const FpLookInput *in,uint32_t pressed) {
    int out=0,z=in->zone,ctx=in->context;
    int look=(pressed&FP_CUP) && fp_eligible(c,in);
    if(ctx==1) {
        const int states[5]={0,31,2,3,4};out=states[z];
        if(in->buttons&FP_Z)out=7;
        if((pressed&FP_B) && in->can_claw)out=6;
        if(pressed&FP_A)out=(in->buttons&FP_Z)?18:5;
        if(look)out=152;
    } else {
        if(ctx==31){if(z==0 && in->speed<1)out=1;else if(z>=2)out=z;}
        if(ctx==2){if(z==0 && in->speed<3)out=1;else if(z==1)out=31;else if(z>=3)out=z;}
        if(ctx==3){if(z<=2 && in->speed<150)out=2;else if(z==4)out=4;}
        if(ctx==4){if(z==0 && in->speed<18)out=1;else if((z==1 || z==2) && in->speed<150)out=2;else if(z==3 && in->speed<225)out=3;}
        if(look && (ctx!=4 || z!=4))out=152;
        if(in->fall)out=47;
        if(in->buttons&FP_Z)out=7;
        if(pressed&FP_B) {
            if(in->target_speed>225){if(in->can_roll)out=49;}
            else if(in->can_claw)out=6;
        }
        if(pressed&FP_A)out=(in->buttons&FP_Z)?18:5;
    }
    if(in->slide)out=50;
    return out;
}
static void event(FpLook *s,int e){s->events[s->event_count++]=e;}
void fp_look_update(FpLook *s,FpCamera *c,const FpClock *clock,const FpLookInput *in,const float p[3],const float r[3]) {
    uint32_t pressed=in->buttons&~s->buttons;s->buttons=in->buttons;
    s->event_count=0;memset(s->events,0,sizeof(s->events));s->requested=0;
    if(!s->active) {
        s->requested=fp_select(c,in,pressed);
        if(s->requested!=152)return;
        s->active=1;s->entries++;
        s->sound=0x12d;event(s,1);
        s->animation=0x6f;s->animation_duration=5.5f;s->animation_starts++;event(s,2);
        s->update_types[0]=1;s->update_types[1]=1;s->update_types[2]=3;s->update_types[3]=2;event(s,3);
        s->target_speed=0;event(s,4);memset(s->velocity,0,12);event(s,5);
        fp_state(c,FP_ENTER,p,r);copy(c->eye,p);for(int i=0;i<3;i++)c->look[i]=angle(r[i]);event(s,6);
        copy(c->eye,in->player);c->eye[1]+=100;event(s,7);
        c->look[0]=0;c->look[1]=angle(in->yaw+180.f);c->look[2]=0;event(s,8);
        s->flag=1;event(s,9);
    } else {
        int exit=0;
        if(c->state==FP_IDLE) {
            float look[3];copy(look,c->look);
            look[0]-=in->stick_y*90.f*clock->dt;look[1]-=in->stick_x*90.f*clock->dt;look[2]=0;
            look[0]=look[0]>180.f?(look[0]>305.f?look[0]:305.f):(look[0]<70.f?look[0]:70.f);
            for(int i=0;i<3;i++)c->look[i]=angle(look[i]);
            event(s,8);
            s->ideal_yaw=angle(look[1]+180.f);event(s,10);
            exit=(pressed&(FP_A|FP_B|FP_CUP))!=0;
            if(!(in->stable_flag && in->vy<0) && !(in->vy<0 && in->player[1]-in->floor<25.f))exit=1;
        }
        copy(c->eye,in->player);c->eye[1]+=100;event(s,7);
        if(exit) {
            s->requested=1;s->sound=0x12e;event(s,1);
            fp_state(c,FP_EXIT,p,r);event(s,11);s->flag=0;event(s,12);s->active=0;s->exits++;
        }
    }
}
