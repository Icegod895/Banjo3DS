#include "jump.h"
#include <math.h>
#include <string.h>

bool banjo_jump_sweep(const FloorVertex *vertices, const FloorTriangle *triangles,
                     size_t count, const float start[3], const float end[3],
                     float contact[3], size_t *triangleIndex) {
    if (!(end[1] < start[1])) return false;
    bool found=false;
    float best=2.0f, hit[3]={0};
    size_t index=0;
    for(size_t i=0;i<count;i++) {
        const FloorTriangle *t=&triangles[i];
        if(t->flags & MOVEMENT_FLOOR_FILTER)continue;
        const FloorVertex *a=&vertices[t->a], *b=&vertices[t->b], *c=&vertices[t->c];
        float u[3]={b->x-a->x,b->y-a->y,b->z-a->z};
        float v[3]={c->x-a->x,c->y-a->y,c->z-a->z};
        float n[3]={u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]};
        float length=sqrtf(n[0]*n[0]+n[1]*n[1]+n[2]*n[2]);
        if(length==0)continue;
        if((t->flags & 0x10000u) && n[1]<0)
            for(int j=0;j<3;j++)n[j]=-n[j];
        if(n[1]<MOVEMENT_MIN_NORMAL_Y*length)continue;
        float d0=n[0]*(start[0]-a->x)+n[1]*(start[1]-a->y)+n[2]*(start[2]-a->z);
        float d1=n[0]*(end[0]-a->x)+n[1]*(end[1]-a->y)+n[2]*(end[2]-a->z);
        if(d0<0 || d1>0 || !(d1<d0))continue;
        float time=d0/(d0-d1);
        if(time>=best)continue;
        float p[3];for(int j=0;j<3;j++)p[j]=start[j]+time*(end[j]-start[j]);
        float px=p[0]-a->x,pz=p[2]-a->z,det=u[0]*v[2]-u[2]*v[0];
        float s=(px*v[2]-pz*v[0])/det,r=(u[0]*pz-u[2]*px)/det;
        if(s<0 || r<0 || s+r>1)continue;
        /* Reconstruct height on the floor, avoiding residual plane error. */
        p[1]=a->y+s*u[1]+r*v[1];
        memcpy(hit,p,sizeof(hit));best=time;index=i;found=true;
    }
    if(found){memcpy(contact,hit,sizeof(hit));if(triangleIndex)*triangleIndex=index;}
    return found;
}
static bool supported(const MovementActor *a,const FloorVertex *v,const FloorTriangle *t,size_t n) {
    float height;
    return movementFloor(v,t,n,a->x,a->z,a->y,&height) &&
           fabsf(height-a->y)<=BANJO_JUMP_CONTACT_EPSILON;
}
static void remember(BanjoJumpMotion *s) {
    s->lastSafeGroundPosition[0]=s->actor.x;
    s->lastSafeGroundPosition[1]=s->actor.y;
    s->lastSafeGroundPosition[2]=s->actor.z;s->hasSafeGround=true;
}
static unsigned step(BanjoJumpMotion *s,BanjoHorizontal *h,float padX,float padY,float yaw,float dt,
                        bool jumpPressed,bool cameraMode,bool horizontalAllowed,
                        const FloorVertex *v,const FloorTriangle *t,size_t n,
                        BanjoCandidateObserver observe,void *context) {
    if(!s || !isfinite(dt) || dt<0 || !isfinite(padX) || !isfinite(padY) || !isfinite(yaw))return 0;
    dt=fminf(dt,0.05f);
    unsigned events=0;
    if(s->grounded) {
        if(!supported(&s->actor,v,t,n)){s->grounded=false;s->verticalVelocity=0;}
        else {
            remember(s);
            if(jumpPressed && !cameraMode){
                s->grounded=false;s->verticalVelocity=710;events|=BANJO_JUMP_TAKEOFF;
                if(h)banjo_horizontal_takeoff(h);
            }
            else {
                if(h) {
                    banjo_horizontal_step(h,BANJO_HORIZONTAL_GROUND,dt);
                    float x=s->actor.x+h->candidate[0],z=s->actor.z+h->candidate[1],height;
                    if(observe) {
                        const float candidate[3]={x,s->actor.y,z};
                        observe(context,candidate);
                    }
                    if(movementFollowFloor(v,t,n,s->actor.x,s->actor.y,s->actor.z,x,z,&height)) {
                        if(x!=s->actor.x || z!=s->actor.z)events|=BANJO_JUMP_MOVED;
                        s->actor.x=x;s->actor.y=height;s->actor.z=z;
                    }
                    /* Facing and physics velocity are independent of acceptance. */
                    s->actor.yaw=h->visible_yaw;
                } else if(horizontalAllowed && movementUpdate(&s->actor,padX,padY,yaw,dt,cameraMode,v,t,n))events|=BANJO_JUMP_MOVED;
                remember(s);return events;
            }
        }
    }
    float start[3]={s->actor.x,s->actor.y,s->actor.z},end[3],stick[2]={0},direction[2]={0};
    if(!cameraMode && horizontalAllowed){movementNormalize(padX,padY,stick);movementDirection(stick[0],stick[1],yaw,direction);}
    if(h)banjo_horizontal_step(h,BANJO_HORIZONTAL_AIR,dt);
    s->verticalVelocity=fmaxf(s->verticalVelocity-1350.0f*dt,-4000.0f);
    end[0]=start[0]+(h?h->candidate[0]:direction[0]*MOVEMENT_SPEED*dt);
    end[1]=start[1]+s->verticalVelocity*dt;
    end[2]=start[2]+(h?h->candidate[1]:direction[1]*MOVEMENT_SPEED*dt);
    if(observe)observe(context,end);
    float hit[3];
    if(banjo_jump_sweep(v,t,n,start,end,hit,NULL)) {
        memcpy(end,hit,sizeof(end));s->verticalVelocity=0;s->grounded=true;events|=BANJO_JUMP_LANDED;
    }
    s->actor.x=end[0];s->actor.y=end[1];s->actor.z=end[2];
    if(dt>0 && (end[0]!=start[0] || end[2]!=start[2])) {
        if(!h)s->actor.yaw=atan2f(direction[0],direction[1])/0.017453292519943295f;
        events|=BANJO_JUMP_MOVED;
    }
    if(h)s->actor.yaw=h->visible_yaw;
    if(s->grounded)remember(s);
    else if(s->actor.y<BANJO_JUMP_VOID_Y && s->hasSafeGround) {
        MovementActor safe={s->lastSafeGroundPosition[0],s->lastSafeGroundPosition[1],s->lastSafeGroundPosition[2],s->actor.yaw};
        if(supported(&safe,v,t,n)) {
            s->actor=safe;s->verticalVelocity=0;s->grounded=true;events|=BANJO_JUMP_RECOVERED;
        }
    }
    return events;
}

unsigned banjo_jump_step(BanjoJumpMotion *s,float padX,float padY,float yaw,float dt,
                        bool jumpPressed,bool cameraMode,bool horizontalAllowed,
                        const FloorVertex *v,const FloorTriangle *t,size_t n) {
    return step(s,NULL,padX,padY,yaw,dt,jumpPressed,cameraMode,horizontalAllowed,v,t,n,NULL,NULL);
}
unsigned banjo_jump_step_horizontal(BanjoJumpMotion *s,BanjoHorizontal *h,float dt,
                        bool jumpPressed,bool cameraMode,
                        const FloorVertex *v,const FloorTriangle *t,size_t n) {
    if(!h)return 0;
    return step(s,h,0,0,0,dt,jumpPressed,cameraMode,true,v,t,n,NULL,NULL);
}
unsigned banjo_jump_step_observed(BanjoJumpMotion *s,BanjoHorizontal *h,float dt,
                        bool jumpPressed,bool cameraMode,
                        const FloorVertex *v,const FloorTriangle *t,size_t n,
                        BanjoCandidateObserver observe,void *context) {
    if(!h)return 0;
    return step(s,h,0,0,0,dt,jumpPressed,cameraMode,true,v,t,n,observe,context);
}
