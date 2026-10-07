/* HOST ONLY. Drives the real PlayerMotionStep dispatch, never linked by Makefile.
 * The explicit-candidate mode tests the post-physics seam without pretending
 * that pathological >66-unit source probes are normal 500 units/s frames.
 * Air candidate math mirrors the existing pre-sweep jump boundary; a separate
 * regression compares it against the real jump observer. No new jump policy. */
#include "../../../platform/3ds/source/player_runtime.h"
#include "../body/frame.h"
#include "body_frame_observer.h"
#include <math.h>
#include <string.h>

typedef struct {
 PlayerRuntime player;
 BgState phase;
 BqFloorBridge clock;
 BpState history;
 BpSharedScratch scratch;
 BanjoCameraMath math;
 BridgeState world;
 BridgeModel opa,xlu;
 BodyFrameObservation observed;
 BgState prior;
 BgFrame input;
 uint32_t state_updates,physics_candidates,body_loops,fall_request;
 uint32_t applied[5][3],world_changed,clock_changed;
 int result,mode;
 float supplied[3];
 const FloorVertex *probe_vertices;const FloorTriangle *probe_triangles;size_t probe_count;
 uint32_t air_probe_calls,air_probe_equal;
} Host;
static Host *active; /* Test observer only: asserts sequential non-reentrancy. */
int __real_bridge_floor_update(BqFloorState*,const BqModel*,const BqModel*,const float*,float,uint32_t,unsigned);
int __wrap_bridge_floor_update(BqFloorState*s,const BqModel*o,const BqModel*x,const float*p,float upper,uint32_t mask,unsigned parity) {
 if(!active)return __real_bridge_floor_update(s,o,x,p,upper,mask,parity);
 Host*h=active;unsigned i=h->observed.floors++;
 if(i>=5)return -1;
 h->observed.parity[i]=parity;memcpy(h->observed.candidate[i],p,12);
 memcpy(h->observed.before[i],s,120);
 BridgeState before=h->world;uint32_t frame=h->clock.frame;
 for(int j=0;j<3;j++)h->applied[i][j]=(uint32_t)(int32_t)h->world.mesh[j].applied;
 int r=__real_bridge_floor_update(s,o,x,p,upper,mask,parity);
 memcpy(h->observed.after[i],s,120);
 h->world_changed|=memcmp(&before,&h->world,sizeof(before))!=0;
 h->clock_changed|=frame!=h->clock.frame || !h->clock.active || parity!=bq_bridge_parity(&h->clock);
 return r;
}
int __real_bridge_sphere(const BqModel*,const BqModel*,const float*,float,uint32_t,BqHit*);
int __wrap_bridge_sphere(const BqModel*o,const BqModel*x,const float*p,float r,uint32_t mask,BqHit*hit) {
 if(active)active->observed.spheres++;
 return __real_bridge_sphere(o,x,p,r,mask,hit);
}
int __real_bridge_moving(const BqModel*,const BqModel*,const float*,float*,float,int,uint32_t,BcScratch*,BqHit*);
int __wrap_bridge_moving(const BqModel*o,const BqModel*x,const float*p,float*end,float r,int n,uint32_t mask,BcScratch*s,BqHit*hit) {
 if(active)active->observed.moving++;
 return __real_bridge_moving(o,x,p,end,r,n,mask,s,hit);
}
int __real_bridge_segment(const BqModel*,const BqModel*,const float*,float*,uint32_t,BqHit*);
int __wrap_bridge_segment(const BqModel*o,const BqModel*x,const float*p,float*end,uint32_t mask,BqHit*hit) {
 if(active)active->observed.lines++;
 return __real_bridge_segment(o,x,p,end,mask,hit);
}
typedef struct {float candidate[3],vy;unsigned calls;BanjoJumpMotion*m;} AirProbe;
static void air_probe(void*context,const float p[3]) {
 AirProbe*a=context;memcpy(a->candidate,p,12);a->vy=a->m->verticalVelocity;a->calls++;
}
void frame_host_probe_geometry(Host*h,const FloorVertex*v,const FloorTriangle*t,size_t n) {
 h->probe_vertices=v;h->probe_triangles=t;h->probe_count=n;
}
unsigned frame_host_air_probe(const Host*h){return h->air_probe_calls && h->air_probe_equal;}
static unsigned motion(void*context,BanjoJumpMotion*m,BanjoHorizontal*horizontal,float dt,bool jump,bool camera_mode) {
 Host*h=context;BgState next=h->phase;
 next.position[0]=m->actor.x;next.position[1]=m->actor.y;next.position[2]=m->actor.z;
 next.vertical_velocity=m->verticalVelocity;next.grounded=m->grounded;
 if(next.grounded)next.falling=0;
 h->prior=next;h->state_updates++;
 h->fall_request=h->mode==2?0:(uint32_t)bg_state_update(&next);
 BgFrame f={0};unsigned events=0;
 h->physics_candidates++;
 if(h->mode==1) {
  memcpy(f.previous,next.position,12);memcpy(f.candidate,h->supplied,12);f.previous_grounded=next.grounded;
  for(int k=0;k<3;k++)f.requested[k]=f.candidate[k]-f.previous[k];
 } else if(h->mode==2) {
  BanjoJumpMotion legacy_motion=*m;BanjoHorizontal legacy_horizontal=*horizontal;
  AirProbe probe={{0},0,0,&legacy_motion};
  if(h->probe_vertices)banjo_jump_step_observed(&legacy_motion,&legacy_horizontal,dt,jump,camera_mode,
     h->probe_vertices,h->probe_triangles,h->probe_count,air_probe,&probe);
  if(next.grounded && jump && !camera_mode) {
   next.grounded=0;next.vertical_velocity=710;banjo_horizontal_takeoff(horizontal);events|=BANJO_JUMP_TAKEOFF;
  }
  next.falling=0;
  banjo_horizontal_step(horizontal,BANJO_HORIZONTAL_AIR,dt);
  next.vertical_velocity=fmaxf(next.vertical_velocity-1350.f*dt,-4000.f);
  memcpy(f.previous,next.position,12);f.previous_grounded=next.grounded;
  f.candidate[0]=next.position[0]+horizontal->candidate[0];
  f.candidate[1]=next.position[1]+next.vertical_velocity*dt;
  f.candidate[2]=next.position[2]+horizontal->candidate[1];
  for(int k=0;k<3;k++)f.requested[k]=f.candidate[k]-f.previous[k];
  h->air_probe_calls=probe.calls;
  h->air_probe_equal=memcmp(probe.candidate,f.candidate,12)==0 &&
      memcmp(&probe.vy,&next.vertical_velocity,4)==0 &&
      memcmp(legacy_horizontal.velocity,horizontal->velocity,sizeof(horizontal->velocity))==0;
 } else {
  banjo_horizontal_step(horizontal,next.falling?BANJO_HORIZONTAL_AIR:BANJO_HORIZONTAL_GROUND,dt);
  bg_candidate(&next,horizontal->velocity,dt,&f);
 }
 h->input=f;h->body_loops++;
 BpFrameContext c={&h->clock,&h->history,&next,&h->opa,&h->xlu,&h->math,&h->scratch.player};
 h->result=bp_frame_resolve(&c,&f,h->clock.frame);
 if(h->result!=1)return 0;
 if(!m->grounded && next.grounded)events|=BANJO_JUMP_LANDED;
 if(next.position[0]!=m->actor.x || next.position[2]!=m->actor.z)events|=BANJO_JUMP_MOVED;
 m->actor.x=next.position[0];m->actor.y=next.position[1];m->actor.z=next.position[2];m->actor.yaw=horizontal->visible_yaw;
 m->verticalVelocity=next.vertical_velocity;m->grounded=next.grounded!=0;
 h->phase=next;return events;
}
size_t frame_host_size(void){return sizeof(Host);}
void frame_host_init(Host*h,const uint8_t*o,size_t on,const uint8_t*x,size_t xn,
 const BgState*initial,const BqFloorState*floor,uint32_t bits,float heading,float speed) {
 memset(h,0,sizeof(*h));h->phase=*initial;
 h->player.motion.actor=(MovementActor){initial->position[0],initial->position[1],initial->position[2],heading};
 h->player.motion.verticalVelocity=initial->vertical_velocity;h->player.motion.grounded=initial->grounded;
 banjo_horizontal_init(&h->player.horizontal,heading);h->player.horizontalInitialized=true;
 h->player.horizontal.velocity[0]=speed*sinf(heading*.017453292519943295f);
 h->player.horizontal.velocity[1]=speed*cosf(heading*.017453292519943295f);
 h->player.locomotion.gait=speed>0?BANJO_GAIT_FAST:BANJO_GAIT_IDLE;
 bridge_init(&h->world);bridge_actor_tick(&h->world,bits);bridge_mesh_tick(&h->world,1.f/60.f);
 bridge_model_open(&h->opa,o,on,&h->world);bridge_model_open(&h->xlu,x,xn,&h->world);
 bq_bridge_init(&h->clock,0);h->clock.floor=*floor;banjo_camera_math_init(&h->math);
}
int frame_host_update(Host*h,float x,float y,float yaw,float dt,int mode,const float*supplied,bool jump,bool camera_mode,uint32_t bits) {
 if(active)return -1;
 memset(&h->observed,0,sizeof(h->observed));memset(h->applied,0,sizeof(h->applied));
 h->state_updates=h->physics_candidates=h->body_loops=h->fall_request=h->world_changed=h->clock_changed=0;
 h->mode=mode;if(supplied)memcpy(h->supplied,supplied,12);
 h->result=1;
 bridge_actor_tick(&h->world,bits);
 if(bq_bridge_begin(&h->clock)!=1)return -1;
 BridgeState leased_world=h->world;
 active=h;
 playerRuntimeMoveStepped(&h->player,x,y,yaw,dt,jump,camera_mode,NULL,NULL,0,NULL,NULL,NULL,motion,h);
 active=NULL;
 h->world_changed|=memcmp(&leased_world,&h->world,sizeof(leased_world))!=0;
 if(bq_bridge_end(&h->clock)!=1)return -1;
 /* The actual camera would consume final floor/player state HERE, before
  * publication. This harness intentionally does not execute a viewer. */
 bridge_mesh_tick(&h->world,dt);
 return h->result;
}
void frame_host_snapshot(Host*h,BgState*phase,BqFloorBridge*clock,BpState*history,BpTrace*trace,
 BodyFrameObservation*obs,BgState*prior,BgFrame*input,uint32_t*counts,uint32_t*applied) {
 *phase=h->phase;*clock=h->clock;*history=h->history;*trace=h->scratch.player.trace;
 *obs=h->observed;*prior=h->prior;*input=h->input;
 uint32_t c[]={h->state_updates,h->physics_candidates,h->body_loops,h->fall_request,h->world_changed,h->clock_changed};
 memcpy(counts,c,sizeof(c));memcpy(applied,h->applied,sizeof(h->applied));
}
void frame_host_pending(Host*h,uint32_t bits){bridge_init(&h->world);bridge_actor_tick(&h->world,bits);}
void frame_host_reinit(Host*h){bq_bridge_reinit(&h->clock);}
void frame_host_stuck(Host*h,uint32_t stuck){h->history.stuck=stuck;}
const PlayerRuntime*frame_host_player(const Host*h){return &h->player;}
/* Scratch alias proof: damage the camera lease after body return, next player
 * update must rebuild its own work records; persistent histories live elsewhere. */
void frame_host_camera_lease(Host*h){memset(&h->scratch.camera,0xA5,sizeof(h->scratch.camera));}
