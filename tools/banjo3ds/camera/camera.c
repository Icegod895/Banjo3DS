#include "camera.h"
#include <math.h>
#include <string.h>

/* libultra finite sin/cos subset; same polynomial as the proven horizontal
 * module. Kept private: this layer does not change existing modules. */
static float trig(float a, bool cosine) {
    uint32_t bits; memcpy(&bits, &a, 4);
    unsigned exponent = (bits >> 22) & 511;
    if (!cosine && exponent < 0xe6) return a;
    double x = cosine ? fabs(a) : a;
    int n = 0;
    if (cosine || exponent >= 0xff) {
        double dn = x * 0x1.45f306dc9c883p-2 + (cosine ? 0.5 : 0.0);
        n = (int)(dn + (dn >= 0 ? 0.5 : -0.5));
        dn = n - (cosine ? 0.5 : 0.0);
        x = (x - dn * 0x1.921fb50000000p+1) - dn * 0x1.110b4611a6263p-25;
    }
    double square = x*x;
    double p = ((0x1.5dbdf0e314bfep-19*square - 0x1.9f6ffeea56814p-13)*square
                + 0x1.110ed3804c2a0p-7)*square - 0x1.55554bc83656dp-3;
    float r = (float)(x + (x*square)*p);
    return n & 1 ? -r : r;
}
static float angle(float x) {
    if (x < 0.0) { x = angle(-x); x = 360.0-x; }
    if (x >= 360.0) x -= 360.0*(int32_t)(x/360.0);
    return x;
}
static float delta(float a, float b) {
    float d=a-b;
    if (fabsf(d)>180.0f) d += d<0 ? 360.0 : -360.0;
    return d;
}
static float map(float x,float lo,float hi,float a,float b) {
    float v=((x-lo)/(hi-lo))*(b-a)+a;
    return v>b ? b : v<a ? a : v;
}
static void vector(float out[3],float yaw,float length) {
    float a=(float)(yaw*(3.141592654/180.0));
    /* func_80256E24, pitch=0, including cardinal residuals and operation order. */
    float t=0.0f*trig(0,false)+trig(0,true)*length;
    out[0]=t*trig(a,false)+trig(a,true)*0.0f;
    out[1]=0.0f*trig(0,true)-trig(0,false)*length;
    out[2]=t*trig(a,true)-trig(a,false)*0.0f;
}
void banjo_camera_math_init(BanjoCameraMath *m) {
    for (int i=0;i<10001;i++)
        m->angle_table[i]=(uint16_t)(trig((float)(i*90.0/10000*3.14159265358979323846/180),false)*65535.f);
}
/* ml_acosf is actually a quantized first-quadrant inverse-sine lookup.
 * Do not replace it with acosf/atan2f or the animation acos-degree table. */
static float lookup(const BanjoCameraMath *m,float x) {
    uint16_t lo=0,hi=10000,i=10000,target=(uint16_t)(fabsf(x)*65535.0);
    while (hi-lo>=2 && target!=m->angle_table[i]) {
        i=(hi+lo)/2;
        if (target<m->angle_table[i]) hi=i; else lo=i;
    }
    return i*90.0/10000.0;
}
static float heading(const BanjoCameraMath *m,float x,float z) {
    float h=sqrtf(z*z+x*x),yaw=0;
    if (h<0.01) return yaw;
    yaw=lookup(m,x/h);
    if (z<0) yaw=180-yaw;
    if (x<0) yaw=360-yaw;
    return yaw;
}
static void look(const BanjoCameraMath *m,const float focus[3],const float eye[3],float out[3]) {
    float dx=eye[0]-focus[0],dy=eye[1]-focus[1],dz=eye[2]-focus[2];
    float h2=dx*dx+dz*dz,h=sqrtf(h2),d=sqrtf(dy*dy+h2);
    out[1]=0;
    if (h>0.01) {
        out[1]=lookup(m,dx/h);
        if (dz<0) out[1]=180-out[1];
        if (dx<0) out[1]=360-out[1];
    }
    out[0]=0;
    if (d>0.01) { out[0]=lookup(m,dy/d); if(dy<0) out[0]=360-out[0]; }
    out[0]=angle(-out[0]);out[2]=0;
}
static void base_focus(const BanjoCameraInput *in,float f[3]) {
    memcpy(f,in->player,12);
    f[1]=in->floor_height+130.f<in->player[1] ? in->player[1]+(80.f-130.f) : in->floor_height+80.f;
}
static void focus(BanjoCamera *s,const BanjoCameraInput *in) {
    base_focus(in,s->focus);
    if(s->state==0xB) for(int i=0;i<3;i++)s->focus[i]+=s->lead[i];
}
static void enter_free(BanjoCamera *s,const BanjoCameraMath *m,const BanjoCameraInput *in) {
    s->state=0xB;focus(s,in);
    s->orbit_yaw=heading(m,s->position[0]-s->focus[0],s->position[2]-s->focus[2]);
}
void banjo_camera_init(BanjoCamera *s,const BanjoCameraMath *m,const BanjoCameraInput *in,
                       const float eye[3],const float rotation[3]) {
    memset(s,0,sizeof(*s));memcpy(s->position,eye,12);memcpy(s->rotation,rotation,12);
    memcpy(s->stable_position,in->player,12);s->node=-1;s->mode=2;s->preset=2;
    enter_free(s,m,in);
}
static bool hit(const BanjoCameraTrigger *t,const float p[3]) {
    int32_t x=(int32_t)p[0],y=(int32_t)p[1],z=(int32_t)p[2];
    int32_t dx=x-t->position[0],dz=z-t->position[2];
    return (t->mask&1) && y+150>=t->position[1] && y-150<t->position[1]
        && dx*dx+dz*dz<t->radius*t->radius;
}
static bool overshot(float step,float error) {
    return fabsf(error)<fabsf(step) && 0.0f<=step*error;
}
static void smooth_position(BanjoCamera *s,const float desired[3],float gain,float response,int vi) {
    for(int n=0;n<vi*5;n++) {
        float error[3],wanted[3],diff[3];
        for(int i=0;i<3;i++)error[i]=desired[i]-s->position[i];
        for(int i=0;i<3;i++)wanted[i]=gain*(0.003333*error[i]);
        for(int i=0;i<3;i++)diff[i]=wanted[i]-s->position_step[i];
        for(int i=0;i<3;i++)s->position_step[i]+=diff[i]*0.003333*response;
        for(int i=0;i<3;i++)if(overshot(s->position_step[i],error[i])) {
            s->position_step[i]=0;s->position[i]=desired[i];
        }
        for(int i=0;i<3;i++)s->position[i]+=s->position_step[i];
    }
}
static void smooth_angles(BanjoCamera *s,const float desired[3],float gain,float response,float dt) {
    float error[2],wanted[2],diff[2];
    for(int i=0;i<2;i++)error[i]=delta(desired[i],s->rotation[i]);
    for(int i=0;i<2;i++)wanted[i]=error[i]*dt*gain;
    for(int i=0;i<2;i++)diff[i]=wanted[i]-s->angular_step[i];
    for(int i=0;i<2;i++)diff[i]=response*(0.0333*diff[i]);
    for(int i=0;i<2;i++)s->angular_step[i]+=diff[i];
    for(int i=0;i<2;i++) {
        if(fabsf(error[i])<fabsf(s->angular_step[i]) && s->angular_step[i]*error[i]>0.0f) {
            s->angular_step[i]=0;s->rotation[i]=desired[i];
        }
        s->rotation[i]=angle(s->rotation[i]+s->angular_step[i]);
    }
    s->rotation[2]=0;
}
bool banjo_camera_prepare(BanjoCameraPhase *phase,const BanjoCamera *s,const BanjoCameraMath *m,const BanjoCameraZoom *z,
                         const BanjoCameraTrigger *ts,size_t count,const BanjoCameraInput *in) {
    if(!phase || !s || !m || !z || !in || (count && !ts) || (z->flags&1) || !isfinite(in->dt) || in->dt<0 || in->dt>.05f
       || in->vi_frames<1 || in->vi_frames>15 || s->preset<1 || s->preset>3
       || !isfinite(in->floor_height) || !isfinite(in->floor_under_camera)
       || !isfinite(in->visible_yaw) || fabsf(in->visible_yaw)>36000) return false;
    for(int i=0;i<3;i++)if(!isfinite(in->player[i]) || fabsf(in->player[i])>20000)return false;
    BanjoCamera next=*s;
    if(in->stable)memcpy(next.stable_position,in->player,12);
    bool member=false,other=false;
    for(size_t i=0;i<count;i++)if(hit(ts+i,next.stable_position)) {
        if(ts[i].node==32)member=true;else other=true;
    }
    /* Refuse ambiguous/unsupported new zones instead of guessing their mode.
     * Original lookup checks current group first (gccube.c:func_803077FC). */
    if(other && !(next.node==32 && member))return false;
    next.node=member?32:-1;
    if(member){next.mode=9;next.state=0x11;}
    else if(next.mode==9)next.mode=2; /* one final zoom update, as Rare */
    else if(next.state!=0xB)enter_free(&next,m,in);
    float dx=in->player[0]-next.position[0],dz=in->player[2]-next.position[2];
    float amplitude=map(fabsf((float)(angle(next.rotation[1]-in->visible_yaw)-180.0)),0,180,110,180);
    float length=map(sqrtf(dx*dx+dz*dz),300,450,0,amplitude),lead[3];
    vector(lead,in->visible_yaw,length);
    for(int i=0;i<3;i++) {float d=lead[i]-next.lead[i];d*=.08f;next.lead[i]+=d;}
    focus(&next,in);
    float desired[3],pg,pr,ag,ar,anchor_distance=0;
    if(next.state==0xB) {
        static const float radius[]={550,850,1100},height[]={175,375,675};
        float offset[3];vector(offset,next.orbit_yaw,radius[next.preset-1]);
        for(int i=0;i<3;i++)desired[i]=next.focus[i]+offset[i];
        desired[1]=in->player[1]-in->floor_height>130.f ? in->player[1]+height[next.preset-1]-130.f : height[next.preset-1]+in->floor_height;
        float clearance=in->floor_under_camera+35.f+20.f;
        if(desired[1]<clearance)desired[1]=clearance;
        pg=3;pr=8;ag=5;ar=10;
    } else {
        float x=next.position[0]-next.focus[0],zz=next.position[2]-next.focus[2];
        float distance=sqrtf(x*x+zz*zz);
        if(distance<z->close_distance)distance=z->close_distance;
        if(z->far_distance<distance)distance=z->far_distance;
        float d[3]={z->anchor[0]-next.focus[0],0,z->anchor[2]-next.focus[2]};
        anchor_distance=sqrtf(d[0]*d[0]+d[2]*d[2]);
        if(anchor_distance<distance)distance=anchor_distance;
        float mag=sqrtf(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]);
        if(mag!=0) {float scale=distance/mag;for(int i=0;i<3;i++)d[i]*=scale;}
        desired[0]=d[0]+next.focus[0];desired[2]=d[2]+next.focus[2];desired[1]=z->anchor[1];
        pg=z->position_gains[0];pr=z->position_gains[1];ag=z->rotation_gains[0];ar=z->rotation_gains[1];
    }
    smooth_position(&next,desired,pg,pr,in->vi_frames);
    phase->next=next;memcpy(phase->previous,s->position,12);
    memcpy(phase->desired,desired,12);phase->angular_gain=ag;
    phase->angular_response=ar;phase->anchor_distance=anchor_distance;
    return true;
}
bool banjo_camera_finish(BanjoCamera *s,const BanjoCameraPhase *phase,
                         const BanjoCameraMath *m,const BanjoCameraZoom *z,
                         const BanjoCameraInput *in,bool changed,bool recovered,float look_output[3]) {
    if(!s || !phase || !m || !z || !in || (recovered && !changed)
       || (changed && phase->next.state!=0xB))return false;
    BanjoCamera next=phase->next;
    if(changed)next.orbit_yaw=heading(m,next.position[0]-next.focus[0],next.position[2]-next.focus[2]);
    float angles[3];look(m,next.focus,next.position,angles);
    if(next.state==0x11 && phase->anchor_distance<150.f) {
        float target[3],a[3];for(int i=0;i<3;i++)target[i]=z->anchor[i]+z->offset[i];
        look(m,next.focus,target,a);angles[1]=a[1];
    }
    if(look_output)memcpy(look_output,angles,12);
    if(recovered)memcpy(next.rotation,angles,12);
    smooth_angles(&next,angles,phase->angular_gain,phase->angular_response,in->dt);
    *s=next;return true;
}
bool banjo_camera_update(BanjoCamera *s,const BanjoCameraMath *m,const BanjoCameraZoom *z,
                         const BanjoCameraTrigger *ts,size_t count,const BanjoCameraInput *in) {
    BanjoCameraPhase phase;
    if(!banjo_camera_prepare(&phase,s,m,z,ts,count,in))return false;
    return banjo_camera_finish(s,&phase,m,z,in,false,false,NULL);
}
bool banjo_camera_project(const BanjoCamera *s,const float world[3],float aspect,float near_plane,float far_plane,float ndc[3]) {
    if(!s || !world || !ndc || !isfinite(aspect) || aspect<=0 || !isfinite(near_plane)
       || !isfinite(far_plane) || near_plane<1 || far_plane<near_plane+100)return false;
    float yaw=(float)(s->rotation[1]*(3.141592654/180.0)),pitch=(float)(s->rotation[0]*(3.141592654/180.0));
    float sy=trig(yaw,false),cy=trig(yaw,true),sp=trig(pitch,false),cp=trig(pitch,true);
    float x=world[0]-s->position[0],y=world[1]-s->position[1],z=world[2]-s->position[2];
    float vx=cy*x-sy*z,vz=sy*x+cy*z;
    float vy=cp*y+sp*vz;vz=cp*vz-sp*y;
    if(vz>=0)return false;
    float fovy=40;fovy*=3.141592654/180.0;
    float cot=trig(fovy/2,true)/trig(fovy/2,false);
    /* guPerspectiveF scale=.5; preserve its float operations. NDC is analytic
     * float projection, not an RSP fixed-matrix/viewport rasterization oracle. */
    float px=(cot/aspect)*.5f,py=cot*.5f;
    float pz=((near_plane+far_plane)/(near_plane-far_plane))*.5f;
    float pw=(((2*near_plane)*far_plane)/(near_plane-far_plane))*.5f;
    float w=-.5f*vz;
    ndc[0]=px*vx/w;ndc[1]=py*vy/w;ndc[2]=(pz*vz+pw)/w;
    return true;
}
