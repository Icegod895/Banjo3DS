/* Host-only private reuse; accepted contact.c remains byte-identical. */
#define bc_sphere bm_private_bc_sphere
#define bc_moving bm_private_bc_moving
#define bc_gated bm_private_bc_gated
#define bc_contact bm_private_bc_contact
#define bc_state_b bm_private_bc_state_b
#include "../camera_contact/contact.c"
#undef bc_sphere
#undef bc_moving
#undef bc_gated
#undef bc_contact
#undef bc_state_b
#include "manual.h"
static void manual_obstruction(World *w,float *camera,const float *target,BcState *s,unsigned variant){
    float d[3],dir[3],base[3],offset[3]={0},end[3],normal[3];
    diff(d,target,camera);memcpy(dir,d,12);norm(dir);memcpy(base,target,12);float dist=sqrtf(dot(d,d));
    if(1500.f<dist)for(int i=0;i<3;i++)base[i]=camera[i]+dir[i]*1500.f;
    if(s->counter==1 || s->counter==2){for(int i=0;i<3;i++)offset[i]=dir[i]*100.f;rotate(offset,s->counter==1?-90.f:90.f);}
    else if(s->counter==3)offset[1]=100;
    for(int i=0;i<3;i++)end[i]=offset[i]+base[i];
    w->trace->obstruction_calls++;
    if(!line(w,camera,end,normal,0x9e0000)){s->counter=0;return;}
    if(++s->counter<5)return;
    s->counter=0;
    static const float angles[]={0,-25,25,-50,50,-80,80,-120,120,-140,140};
    float minimum=variant==0?150.f:fmaxf(150.f,dist-100.f);
    unsigned count=variant==0?1:variant==1?11:18;
    for(unsigned k=0;k<count;k++){
        w->trace->recovery_attempts++;
        for(int i=0;i<3;i++)offset[i]=dir[i]*-dist;
        rotate(offset,variant<2?angles[k]:(variant==3?-1.f:1.f)*(20.f*k));for(int i=0;i<3;i++)end[i]=target[i]+offset[i];
        float extended[3],extra[3];memcpy(extended,end,12);diff(extra,extended,target);length(extra,40);
        for(int i=0;i<3;i++)extended[i]+=extra[i];
        if(line(w,target,extended,normal,0x9e0000))for(int i=0;i<3;i++)end[i]=extended[i]-extra[i];
        gated(w,target,end,40,normal,4);
        if(minimum<distance(target,end)){
            memcpy(camera,end,12);memset(s->position_step,0,12);memset(s->angular_step,0,12);
            w->trace->recovered=1;return;
        }
    }
}
int bm_gate(const BqModel *o,const BqModel *x,const float a[3],const float b[3],BcScratch *scratch,BcTrace *trace){
    float end[3],extra[3],normal[3];memcpy(end,b,12);diff(extra,end,a);length(extra,40);
    for(int i=0;i<3;i++)end[i]+=extra[i];
    World w={o,x,scratch,trace,0};int hit=line(&w,a,end,normal,0x9e0000);
    if(w.error)return -1;
    if(hit)return 0;
    memcpy(end,b,12);hit=gated(&w,a,end,40,normal,4);
    return w.error?-1:!hit;
}
int bm_obstruction(const BqModel *o,const BqModel *x,float camera[3],const float target[3],unsigned variant,BcState *s,BcScratch *scratch,BcTrace *trace){
    if(variant>3 || s->counter>4)return -1;
    World w={o,x,scratch,trace,0};manual_obstruction(&w,camera,target,s,variant);
    return w.error?-1:(int)trace->recovered;
}
