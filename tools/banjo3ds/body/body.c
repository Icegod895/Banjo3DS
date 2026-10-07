#include "body.h"
#include <math.h>
#include <string.h>
#define COPY(a,b) memcpy((a),(b),12)
int bridge_floor_update(BqFloorState *,const BqModel *,const BqModel *,const float[3],float,uint32_t,unsigned);
#define MASK UINT32_C(0x5e0000)
static float dot(const float*a,const float*b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static void sub(float*d,const float*a,const float*b){for(int i=0;i<3;i++)d[i]=a[i]-b[i];}
static void add(float*d,const float*a,const float*b){for(int i=0;i<3;i++)d[i]=a[i]+b[i];}
static void cross(float*d,const float*a,const float*b){d[0]=a[1]*b[2]-a[2]*b[1];d[1]=a[2]*b[0]-a[0]*b[2];d[2]=a[0]*b[1]-a[1]*b[0];}
static void normalize(float*v){float q=dot(v,v);if(q!=0){float k=1.0/sqrtf(q);for(int i=0;i<3;i++)v[i]*=k;}}
static void length(float*d,const float*s,float len){float q=sqrtf(dot(s,s));if(q!=0){float k=len/q;for(int i=0;i<3;i++)d[i]=s[i]*k;}else COPY(d,s);}
static float distance2(const float*a,const float*b){float v[3];sub(v,a,b);return dot(v,v);}
/* Original libultra cosine, same proven polynomial used by existing camera.
 * Only the edge-distance branch uses it; do not substitute host cosf. */
static float cosine(float a){
 double x=fabs(a),dn=x*0x1.45f306dc9c883p-2+0.5;
 int n=(int)(dn+(dn>=0?0.5:-0.5));dn=n-0.5;
 x=(x-dn*0x1.921fb50000000p+1)-dn*0x1.110b4611a6263p-25;
 double s=x*x,p=((0x1.5dbdf0e314bfep-19*s-0x1.9f6ffeea56814p-13)*s+0x1.110ed3804c2a0p-7)*s-0x1.55554bc83656dp-3;
 float r=(float)(x+(x*s)*p);return n&1?-r:r;
}
static float lookup(const BanjoCameraMath*m,float x){
 uint16_t lo=0,hi=10000,i=10000,target=(uint16_t)(fabsf(x)*65535.0);
 while(hi-lo>=2 && target!=m->angle_table[i]){i=(hi+lo)/2;if(target<m->angle_table[i])hi=i;else lo=i;}
 return i*90.0/10000.0;
}
/* ml 59554 -> 596AC -> 5778C: quantized angular projection, then edge clamp. */
static void edge(float*d,const float*a,const float*b,const float*p,const BanjoCameraMath*m){
 float u[3],v[3],c[3];sub(u,b,a);sub(v,p,a);float mag=sqrtf(dot(v,v));
 if(mag==0.0)COPY(d,a);
 else{
  cross(c,u,v);float sine=sqrtf(dot(c,c))/(sqrtf(dot(u,u))*sqrtf(dot(v,v)));
  float angle=lookup(m,(sine*mag)/mag);
  length(u,u,cosine((float)(angle*(3.141592654/180.0)))*mag);
  if(dot(u,v)>0)add(d,a,u);else sub(d,a,u);
 }
 float aa=distance2(a,b),bb=distance2(a,d),cc=distance2(b,d);
 if(aa<bb || aa<cc){if(bb<cc)COPY(d,a);else COPY(d,b);}
}
static void closest(float*d,const float*p,float t[3][3],const BanjoCameraMath*m){
 float a[3],b[3],c[3];edge(a,t[0],t[1],p,m);edge(b,t[1],t[2],p,m);edge(c,t[2],t[0],p,m);
 float aa=distance2(a,p),bb=distance2(b,p),cc=distance2(c,p);
 if(aa<bb){if(cc<aa)COPY(d,c);else COPY(d,a);}else{if(cc<bb)COPY(d,c);else COPY(d,b);}
}
static void plane(float*d,const float*p,float t[3][3]){
 float a[3],b[3],n[3];sub(a,t[1],t[0]);sub(b,t[2],t[0]);cross(n,a,b);normalize(n);
 float k=dot(n,p)-dot(n,t[0]);for(int i=0;i<3;i++)a[i]=n[i]*k;sub(d,p,a);
}
static void coords(float t[3][3],const BqHit*h,const BqModel*o,const BqModel*x){
 const BqModel*m=h->role?x:o;
 for(int i=0;i<3;i++)for(int j=0;j<3;j++)t[i][j]=bridge_component(m,h->indices[i],j);
}
static int same(const BpStep*a,const BpStep*b){return a->contacted && b->contacted && a->hit.role==b->hit.role && a->hit.occurrence==b->hit.occurrence;}
static int shifted_moving(const BqModel*o,const BqModel*x,const float*a,float*b,float*n,BcScratch*s,BqHit*h){
 float start[3]={a[0],a[1]+80.f,a[2]},end[3]={b[0],b[1]+80.f,b[2]};
 int result=bridge_moving(o,x,start,end,35,3,MASK,s,h);
 if(result==1){b[0]=end[0];b[1]=end[1]-80.f;b[2]=end[2];COPY(n,h->normal);}return result;
}
static int long_line(const BqModel*o,const BqModel*x,const float*a,float*b,float*n){
 float start[3]={a[0],a[1]+80.f,a[2]},end[3]={b[0],b[1]+80.f,b[2]},offset[3];
 sub(offset,end,start);length(offset,offset,34);add(end,end,offset);BqHit hit;
 int result=bridge_segment(o,x,start,end,MASK,&hit);
 if(result==1){sub(end,end,offset);end[1]-=80.f;COPY(b,end);COPY(n,hit.normal);}return result;
}
int bp_resolve(BpState*history,BgState*state,BgFrame*frame,BqFloorState*floor,
 const BridgeModel*opaque,const BridgeModel*transparent,const BanjoCameraMath*math,
 unsigned parity,BpScratch*scratch,BpTrace*out){
 if(!history || !state || !frame || !floor || !opaque || !transparent || !math || !scratch || !out || history->stuck>3)return -1;
 for(int k=0;k<3;k++)if(!isfinite(frame->candidate[k]) || !isfinite(frame->previous[k]) || fabsf(frame->candidate[k])>20000 || fabsf(frame->previous[k])>20000)return -1;
 const BqModel*o=&opaque->base,*x=&transparent->base;
 BqFloorState fs=*floor;BgState gs=*state;BpState hs=*history;
 BpTrace*t=&scratch->trace;memset(t,0,sizeof(*t));memset(scratch->steps,0,sizeof(scratch->steps));
 float previous[3],fallback[3],center[3],desired[3],requested[3];COPY(previous,frame->previous);COPY(desired,frame->candidate);COPY(requested,frame->requested);
 COPY(fallback,previous);COPY(center,previous);center[1]+=80.f;BqHit hit;
 int r=bridge_sphere(o,x,center,35,MASK,&hit);if(r<0)return -1;
 if(r){
  for(int k=0;k<3;k++)fallback[k]=previous[k]+hit.normal[k]*35.f;
  COPY(previous,fallback);float start[3],end[3];COPY(start,previous);COPY(end,previous);start[1]+=100.f;end[1]-=500.f;
  r=bridge_segment(o,x,start,end,MASK,&hit);if(r<0)return -1;
  if(r && (!(hit.normal[1]<0.f) || (hit.flags&0x10000)) && previous[1]<end[1])previous[1]=end[1];
 }
 COPY(t->pushed_previous,previous);COPY(t->fallback,fallback);
 unsigned grounded=frame->previous_grounded;int i;
 for(i=0;i<5;i++){
  BpStep*s=&scratch->steps[i];BpIteration*tr=&t->iteration[i];t->iterations=i+1;
  if(i){COPY(s->position,scratch->steps[i-1].position);COPY(s->previous,scratch->steps[i-1].previous);}
  else{COPY(s->position,desired);COPY(s->previous,previous);}
  COPY(tr->initial,s->position);float delta[3],saved[3];COPY(saved,s->position);sub(delta,s->position,s->previous);
  if(dot(delta,delta)>66.f*66.f){
   tr->paths|=64;
   float y=s->position[1],normal[3]={0};r=long_line(o,x,s->previous,s->position,normal);if(r<0)return -1;
   if(r){normalize(delta);if(dot(delta,normal)>0){tr->paths|=32;r=0;COPY(s->position,saved);}}
   if(r && normal[1]>=0.0 && normal[1]<0.02)s->position[1]=y;
   tr->line_hit=r!=0;
  }
  COPY(tr->after_line,s->position);
  BgFrame f={0};COPY(f.candidate,s->position);COPY(f.requested,requested);f.previous_grounded=grounded;
  /* E.1 itself stays unchanged. Resolve in scratch with vy=0 so its standalone
   * final velocity adjustment is deferred until AFTER the body loop. */
  BgState phase=gs;phase.vertical_velocity=0;
  r=bg_query_resolve(&phase,&f,&fs,o,x,parity,bridge_floor_update);if(r!=1)return -1;
  COPY(s->position,f.candidate);grounded=phase.grounded;gs.floor_height=phase.floor_height;
  COPY(tr->after_floor,s->position);tr->grounded=grounded;memcpy(tr->floor,&fs,120);
  COPY(s->start,s->previous);s->start[1]+=80.f;COPY(s->end,s->position);s->end[1]+=80.f;
  r=bridge_moving(o,x,s->start,s->end,35,3,MASK,&scratch->contact,&s->hit);if(r<0)return -1;
  s->contacted=r;COPY(tr->start_center,s->start);COPY(tr->end_center,s->end);tr->role=tr->record=-1;
  if(!r){COPY(tr->final,s->position);break;}
  COPY(s->normal,s->hit.normal);COPY(tr->normal,s->normal);tr->role=s->hit.role;tr->record=s->hit.occurrence;
  ++t->hits;COPY(hs.normal,s->normal);
  float a[3],b[3],c[3],triangle[3][3];
  if(i==2 && same(s,&scratch->steps[0]) && !same(s,&scratch->steps[1])){
   tr->paths|=1;add(a,s->normal,scratch->steps[1].normal);normalize(a);COPY(s->normal,a);
  }
  if(i==2 && same(s,&scratch->steps[0]) && same(s,&scratch->steps[1])){
   tr->paths|=2;
   coords(triangle,&s->hit,o,x);plane(a,s->position,triangle);sub(b,s->position,a);length(b,b,36);add(a,a,b);
   if(!(s->hit.flags&0x10000)){r=shifted_moving(o,x,a,s->position,s->normal,&scratch->contact,&s->hit);if(r<0)return -1;s->contacted=r;}
   else COPY(s->position,a);
  }
  if(!grounded && s->contacted && requested[1]<0 && fabsf(s->normal[1])<0.01){
   tr->paths|=4;
   coords(triangle,&s->hit,o,x);plane(a,s->position,triangle);
   for(int k=0;k<3;k++)b[k]=s->normal[k]*36.f;
   add(c,a,b);
   r=shifted_moving(o,x,c,a,s->normal,&scratch->contact,&s->hit);if(r<0)return -1;s->contacted=r;
   s->position[0]=a[0];s->position[2]=a[2];
  }
  if(0.999<s->normal[1] && s->contacted){
   tr->paths|=8;
   coords(triangle,&s->hit,o,x);closest(a,s->position,triangle,math);
   b[0]=s->position[0]-a[0];b[1]=0;b[2]=s->position[2]-a[2];length(b,b,36);add(b,b,a);
   s->position[0]=b[0];s->position[2]=b[2];
  }else if(s->normal[0]!=0 || s->normal[1]!=0 || s->normal[2]!=0){
   tr->paths|=16;sub(a,s->position,s->previous);sub(b,s->end,s->start);sub(c,a,b);
   float amount=-dot(s->normal,c);amount=5.f>amount?5.f:amount;
   for(int k=0;k<3;k++)s->position[k]+=amount*s->normal[k];
  }
  COPY(tr->final,s->position);
 }
 t->exhausted=i==5;
 int stuck_now=i==5 && !grounded && t->hits && desired[1]<previous[1];
 COPY(gs.position,i==5?fallback:scratch->steps[i].position);
 if(hs.stuck==3){grounded=1;t->forced=1;}
 gs.grounded=grounded;if(grounded && gs.vertical_velocity<0)gs.vertical_velocity=-1;
 hs.stuck=stuck_now?(hs.stuck<3?hs.stuck+1:3):0;
 COPY(t->final,gs.position);COPY(t->normal,hs.normal);
 *state=gs;*floor=fs;*history=hs;COPY(frame->candidate,gs.position);COPY(frame->normal,fs.normal);*out=*t;return 1;
}
