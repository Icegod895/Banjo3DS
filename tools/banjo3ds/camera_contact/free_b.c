#include "free_b.h"
#include <math.h>
#include <string.h>

static void normalize(float v[3]) {
    float squared=v[0]*v[0]+v[1]*v[1]+v[2]*v[2];
    if(squared!=0) {
        float inverse=1.0/sqrtf(squared);
        for(int i=0;i<3;i++)v[i]*=inverse;
    }
}
bool bc_free_b_rollback(float *history,const float previous[3],const float desired[3],
                        float camera[3],float *dot_output) {
    float a[3],b[3];
    for(int i=0;i<3;i++){a[i]=desired[i]-previous[i];b[i]=camera[i]-previous[i];}
    normalize(a);normalize(b);
    float q=a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    bool rollback=q<0.0f || *history<0.0f;
    if(rollback)memcpy(camera,previous,12);
    *history=q;*dot_output=q;return rollback;
}
bool bc_free_b_update(BanjoCamera *camera,BcFreeBState *state,const BanjoCameraMath *math,
    const BanjoCameraZoom *zoom,const BanjoCameraTrigger *triggers,size_t count,
    const BanjoCameraInput *input,const BqModel *opa,const BqModel *xlu,
    const float target[3],BcScratch *scratch,BcFreeBTrace *trace) {
    if(!state || !scratch || !trace)return false;
    BanjoCameraPhase phase;
    if(!banjo_camera_prepare(&phase,camera,math,zoom,triggers,count,input))return false;
    BcFreeBState next=*state;BcFreeBTrace t={0};
    memcpy(t.previous,phase.previous,12);memcpy(t.desired,phase.desired,12);
    memcpy(t.smoothed,phase.next.position,12);t.free_b=phase.next.state==0xB;
    if(t.free_b) {
        float contact_previous[3];memcpy(contact_previous,phase.previous,12);
        BcState contact={0};
        contact.counter=next.obstruction_counter;
        memcpy(contact.position_step,phase.next.position_step,12);
        memcpy(contact.angular_step,phase.next.angular_step,12);
        if(bc_state_b(opa,xlu,contact_previous,phase.next.position,target,&contact,scratch,&t.contact)<0)return false;
        next.obstruction_counter=contact.counter;
        memcpy(phase.next.position_step,contact.position_step,12);
        memcpy(phase.next.angular_step,contact.angular_step,12);
        memcpy(t.corrected,phase.next.position,12);
        if(t.contact.changed && !t.contact.recovered) {
            t.rollback_executed=1;
            t.rolled_back=bc_free_b_rollback(&next.previous_rollback_dot,phase.previous,phase.desired,phase.next.position,&t.dot);
        }
    } else memcpy(t.corrected,phase.next.position,12);
    BanjoCamera result;
    if(!banjo_camera_finish(&result,&phase,math,zoom,input,t.contact.changed,t.contact.recovered,t.look))return false;
    memcpy(t.final_position,result.position,12);
    *camera=result;*state=next;*trace=t;return true;
}
