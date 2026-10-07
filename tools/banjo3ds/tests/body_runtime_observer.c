/* Test-only linker observers around the ACTUAL live motion-step invocation. */
#include "camera_runtime.h"
#include "body_frame_observer.h"
#include <string.h>
typedef struct {
 BgState before,after;
 BgFrame input,output;
 BqFloorState floor_before,floor_after;
 BpState history_before,history_after;
 BpTrace trace;
 BodyFrameObservation queries;
 uint32_t frame,parity,ordinal_before,ordinal_after,world_changed;
 int32_t applied[5][3];
 int result;
} Capture;
static Capture captured;
static const BpFrameContext *active;
int __real_bp_frame_resolve(const BpFrameContext*,BgFrame*,uint32_t);
int __wrap_bp_frame_resolve(const BpFrameContext*c,BgFrame*f,uint32_t frame) {
 memset(&captured,0,sizeof(captured));
 captured.before=*c->phase;captured.input=*f;captured.floor_before=c->clock->floor;
 captured.history_before=*c->history;captured.frame=frame;captured.parity=bq_bridge_parity(c->clock);
 captured.ordinal_before=c->clock->next_ordinal;
 BridgeState world=*c->opa->state;active=c;
 int r=__real_bp_frame_resolve(c,f,frame);active=NULL;
 captured.result=r;captured.after=*c->phase;captured.output=*f;captured.floor_after=c->clock->floor;
 captured.history_after=*c->history;captured.trace=c->scratch->trace;captured.ordinal_after=c->clock->next_ordinal;
 captured.world_changed=memcmp(&world,c->opa->state,sizeof(world))!=0;return r;
}
int __real_bridge_floor_update(BqFloorState*,const BqModel*,const BqModel*,const float*,float,uint32_t,unsigned);
int __wrap_bridge_floor_update(BqFloorState*s,const BqModel*o,const BqModel*x,const float*p,float up,uint32_t mask,unsigned parity) {
 if(!active)return __real_bridge_floor_update(s,o,x,p,up,mask,parity);
 unsigned i=captured.queries.floors++;
 if(i>=5)return -1;
 captured.queries.parity[i]=parity;memcpy(captured.queries.candidate[i],p,12);
 memcpy(captured.queries.before[i],s,120);
 for(int k=0;k<3;k++)captured.applied[i][k]=active->opa->state->mesh[k].applied;
 int r=__real_bridge_floor_update(s,o,x,p,up,mask,parity);
 memcpy(captured.queries.after[i],s,120);return r;
}
int __real_bridge_sphere(const BqModel*,const BqModel*,const float*,float,uint32_t,BqHit*);
int __wrap_bridge_sphere(const BqModel*o,const BqModel*x,const float*p,float r,uint32_t mask,BqHit*h) {
 if(active)captured.queries.spheres++;
 return __real_bridge_sphere(o,x,p,r,mask,h);
}
int __real_bridge_moving(const BqModel*,const BqModel*,const float*,float*,float,int,uint32_t,BcScratch*,BqHit*);
int __wrap_bridge_moving(const BqModel*o,const BqModel*x,const float*p,float*e,float r,int n,uint32_t mask,BcScratch*s,BqHit*h) {
 if(active)captured.queries.moving++;
 return __real_bridge_moving(o,x,p,e,r,n,mask,s,h);
}
int __real_bridge_segment(const BqModel*,const BqModel*,const float*,float*,uint32_t,BqHit*);
int __wrap_bridge_segment(const BqModel*o,const BqModel*x,const float*p,float*e,uint32_t mask,BqHit*h) {
 if(active)captured.queries.lines++;
 return __real_bridge_segment(o,x,p,e,mask,h);
}
void body_runtime_capture(Capture*out){*out=captured;}
size_t body_runtime_capture_size(void){return sizeof(Capture);}
