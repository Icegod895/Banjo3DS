/* Category-4 rail for the canonical Spiral Mountain setup.
 * Knots, volumes, and the 0xCC chain come from BrData. No doorway distances.
 *
 * Limits versus Rare, all outside this dry bridge path:
 * - BSGROUP_4_LOOK and Freezezy Peak flying are not published to bm_update,
 *   so a new engagement is not rejected for first person and an active rail
 *   is not released by look.
 * - Underwater lead amplitudes stay 80/200. The carried-object bits of
 *   baMarker_8028D694() are omitted; the snap filter is 0x400000|0x1E0000.
 * - Marker bit 0 is treated as enabled for the session.
 * - A Y slice counts as loaded when it holds an exported volume or spline
 *   origin. The bridge starts find actor 0xCC in the ±1 cube search.
 * - Category-9 zoom stays on the existing zone path. Mode 0xA is not replaced.
 * ml_acosf is the same 10000-entry sine lookup as the free camera.
 * ml_cos_deg is libm cosf(degrees * (3.141592654/180)), as in ml.c. */
#include "../camera_manual/manual.h"
#include <math.h>
#include <string.h>

static const BrData *rail_data;

void br_bind(const BrData *data) { rail_data=data; }
bool br_bound(void) { return rail_data!=NULL; }
size_t br_volume_size(void) { return sizeof(BrVolume); }
size_t br_spline_size(void) { return sizeof(BrSpline); }
size_t br_data_size(void) { return sizeof(BrData); }
size_t br_runtime_size(void) { return sizeof(BrRuntime); }

enum { BR_RAY_FILTER=0x5E0000 };

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
    float t=0.0f*trig(0,false)+trig(0,true)*length;
    out[0]=t*trig(a,false)+trig(a,true)*0.0f;
    out[1]=0.0f*trig(0,true)-trig(0,false)*length;
    out[2]=t*trig(a,true)-trig(a,false)*0.0f;
}
static float lookup(const BanjoCameraMath *m,float x) {
    uint16_t lo=0,hi=10000,i=10000,target=(uint16_t)(fabsf(x)*65535.0);
    while (hi-lo>=2 && target!=m->angle_table[i]) {
        i=(hi+lo)/2;
        if (target<m->angle_table[i]) hi=i; else lo=i;
    }
    return i*90.0/10000.0;
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
static float ml_map_f(float val,float in_min,float in_max,float out_min,float out_max) {
    if (in_max==in_min) return out_max;
    float result=((val-in_min)/(in_max-in_min))*(out_max-out_min)+out_min;
    if (out_min<out_max) {
        if (result>out_max) return out_max;
        if (result<out_min) return out_min;
    } else {
        if (result<out_max) return out_max;
        if (result>out_min) return out_min;
    }
    return result;
}
static float dist(const float *a,const float *b) {
    float d0=a[0]-b[0],d1=a[1]-b[1],d2=a[2]-b[2];
    return sqrtf(d0*d0+d1*d1+d2*d2);
}
static float dist2(const float *a,const float *b) {
    float d0=a[0]-b[0],d1=a[1]-b[1],d2=a[2]-b[2];
    return d0*d0+d1*d1+d2*d2;
}
static void diff(float *dst,const float *a,const float *b) {
    dst[0]=a[0]-b[0];dst[1]=a[1]-b[1];dst[2]=a[2]-b[2];
}
static void set_length(float *dst,const float *src,float len) {
    float mag=sqrtf(src[0]*src[0]+src[1]*src[1]+src[2]*src[2]);
    if (mag!=0.f) { float s=len/mag; dst[0]=src[0]*s; dst[1]=src[1]*s; dst[2]=src[2]*s; }
    else { dst[0]=src[0]; dst[1]=src[1]; dst[2]=src[2]; }
}

static void catmull(float x,int length,const float *src,float dst[3]) {
    if (length<4) {
        float tmp[12];
        memcpy(tmp,src,12); memcpy(tmp+3,src,12); memcpy(tmp+6,src+3,12);
        if (length-1==1) memcpy(tmp+9,src+3,12); else memcpy(tmp+9,src+6,12);
        catmull(x,4,tmp,dst); return;
    }
    int max_interval=length-1;
    float clamped=x<0.f?0.f:(x>1.f?1.f:x);
    float temp=clamped*(float)max_interval;
    int a3=(int)temp;
    if (a3>length-1) a3=length-1;
    float local=temp-(float)a3;
    if (a3==0) {
        for (int c=0;c<3;c++) {
            float p0=src[c],p1=src[3+c],p2=src[6+c];
            float f3=-0.5f*p0+1.5f*p0-1.5f*p1+0.5f*p2;
            float f1=1.0f*p0-2.5f*p0+2.0f*p1-0.5f*p2;
            float f2=-0.5f*p0+0.5f*p1;
            dst[c]=p0+(((f3*local+f1)*local+f2)*local);
        }
    } else {
        a3--;
        if (a3==length-2) {
            const float *last=src+3*(length-1);
            dst[0]=last[0];dst[1]=last[1];dst[2]=last[2];
        } else if (a3==length-3) {
            const float *p=src+a3*3;
            for (int c=0;c<3;c++) {
                float p0=p[c],p1=p[3+c],p2=p[6+c];
                float f3=-0.5f*p0+1.5f*p1-1.5f*p2+0.5f*p2;
                float f1=1.0f*p0-2.5f*p1+2.0f*p2-0.5f*p2;
                float f2=-0.5f*p0+0.5f*p2;
                dst[c]=p1+(((f3*local+f1)*local+f2)*local);
            }
        } else {
            const float *p=src+a3*3;
            for (int c=0;c<3;c++) {
                float p0=p[c],p1=p[3+c],p2=p[6+c],p3=p[9+c];
                float f3=-0.5f*p0+1.5f*p1-1.5f*p2+0.5f*p3;
                float f1=1.0f*p0-2.5f*p1+2.0f*p2-0.5f*p3;
                float f2=-0.5f*p0+0.5f*p2;
                dst[c]=p1+(((f3*local+f1)*local+f2)*local);
            }
        }
    }
}
static void sample(float param,int count,const float *knots,float dst[3]) {
    if (param<0.f) param=0.f; else if (param>1.f) param=1.f;
    catmull(param,count,knots,dst);
}
static float arc(const float *knots,int count,float a,float b,float step) {
    if (b-a<1e-6f) return 0.f;
    float cursor=a,p[3],q[3],length=0.f;
    catmull(cursor,count,knots,p);
    while (cursor+step<b) {
        cursor+=step; catmull(cursor,count,knots,q);
        length+=dist(p,q); memcpy(p,q,12);
    }
    catmull(b,count,knots,q);
    return length+dist(p,q);
}
static float wrap_of(const float *knots,int count) {
    const float *end=knots+(count-1)*3;
    for (int i=0;i<count-1;i++) {
        const float *k=knots+i*3;
        if (k[0]==end[0] && k[1]==end[1] && k[2]==end[2])
            return (float)i/(float)(count-1);
    }
    return 1.f;
}
static void add_abs(float *a,const float *b) {
    a[0]=fabsf(a[0])+fabsf(b[0]); a[1]=fabsf(a[1])+fabsf(b[1]); a[2]=fabsf(a[2])+fabsf(b[2]);
}
static float advance(const float *knots,int count,float param,double distance,double wrap) {
    if (distance==0.0) return param;
    double walked=0.0, step=0.01;
    if (distance<0.0) { distance=-distance; step=-step; }
    double cursor=(double)param;
    float current[3];
    catmull((float)cursor,count,knots,current);
    int close=0;
    do {
        double next=cursor+step;
        float next_point[3];
        double traveled;
        if (step>0.0) {
            if (next>=1.0) {
                if (wrap==1.0) {
                    next=wrap;
                    catmull((float)next,count,knots,next_point);
                    traveled=walked+dist(current,next_point);
                } else {
                    float at_end[3],at_wrap[3],span[3],rest[3];
                    next+=wrap; next=next-(int)next;
                    catmull(1.f,count,knots,at_end);
                    diff(span,at_end,current);
                    catmull((float)wrap,count,knots,at_wrap);
                    catmull((float)next,count,knots,next_point);
                    diff(rest,next_point,at_wrap);
                    add_abs(span,rest);
                    traveled=walked+sqrtf(span[0]*span[0]+span[1]*span[1]+span[2]*span[2]);
                }
            } else {
                catmull((float)next,count,knots,next_point);
                traveled=walked+dist(current,next_point);
            }
        } else if (wrap==1.0) {
            if (next<0.0) next=0.0;
            catmull((float)next,count,knots,next_point);
            traveled=walked+dist(current,next_point);
        } else if (next<wrap) {
            float at_wrap[3],at_end[3],span[3],rest[3];
            next-=wrap; next=next-(int)next; next+=1.0;
            catmull((float)wrap,count,knots,at_wrap);
            diff(span,at_wrap,current);
            catmull(1.f,count,knots,at_end);
            catmull((float)next,count,knots,next_point);
            diff(rest,next_point,at_end);
            add_abs(span,rest);
            traveled=walked+sqrtf(span[0]*span[0]+span[1]*span[1]+span[2]*span[2]);
        } else {
            catmull((float)next,count,knots,next_point);
            traveled=walked+dist(current,next_point);
        }
        close=fabs(distance-traveled)<0.1;
        if (traveled<distance || close) {
            walked=traveled; cursor=next; memcpy(current,next_point,12);
            if (wrap==1.0) {
                if (step>0.0) { if (cursor==wrap) break; }
                else if (cursor==0.0) break;
            }
        } else step*=0.5;
    } while (!close && 1e-7<fabs(step));
    return (float)cursor;
}
static float search_param(const float *knots,int count,const float *point,float min,float max,float step) {
    if (min<0.f) min=0.f;
    if (max>1.f) max=1.f;
    float best_d=1e8f, best=min, cursor=min, at[3];
    for (;;) {
        sample(cursor,count,knots,at);
        float d=dist2(point,at);
        if (d<best_d) { best_d=d; best=cursor; }
        if (cursor==max) break;
        cursor+=step; if (cursor>max) cursor=max;
    }
    return best;
}
static float closest(const float *knots,int count,const float *point) {
    for (int i=0;i<count;i++) {
        const float *k=knots+i*3;
        if (k[0]==point[0] && k[1]==point[1] && k[2]==point[2])
            return (float)i/(float)(count-1);
    }
    float step=0.01f;
    float best=search_param(knots,count,point,0.f,1.f,step);
    for (int n=0;n<6;n++) {
        float lo=best-step, hi=best+step;
        step=(float)(((double)step/10.0)*2.0);
        best=search_param(knots,count,point,lo,hi,step);
    }
    float at[3],end[3];
    sample(best,count,knots,at); sample(1.f,count,knots,end);
    return dist2(point,at)<dist2(point,end) ? best : 1.f;
}
static float sin_between(const float *a,const float *b) {
    float la=sqrtf(a[0]*a[0]+a[1]*a[1]+a[2]*a[2]);
    float lb=sqrtf(b[0]*b[0]+b[1]*b[1]+b[2]*b[2]);
    float c0=a[1]*b[2]-a[2]*b[1], c1=a[2]*b[0]-a[0]*b[2], c2=a[0]*b[1]-a[1]*b[0];
    return sqrtf(c0*c0+c1*c1+c2*c2)/(la*lb);
}
static float project_distance(const BanjoCameraMath *m,const float *knots,int count,
                              float param,const float *focus,const float *eye) {
    float origin[3],ahead[3],dir[3],hit[3];
    sample(param,count,knots,origin);
    sample(param==0.f ? param+0.001f : param-0.001f,count,knots,ahead);
    diff(dir,ahead,origin); set_length(dir,dir,400.f);
    ahead[0]=dir[0]+origin[0]; ahead[1]=dir[1]+origin[1]; ahead[2]=dir[2]+origin[2];
    float along[3],from[3];
    diff(along,ahead,origin); diff(from,focus,origin);
    float mag=sqrtf(from[0]*from[0]+from[1]*from[1]+from[2]*from[2]);
    if (mag==0.0) memcpy(hit,origin,12);
    else {
        float ang=lookup(m,(sin_between(along,from)*mag)/mag);
        set_length(along,along,cosf((float)(ang*(3.141592654/180.0)))*mag);
        float dot=along[0]*from[0]+along[1]*from[1]+along[2]*from[2];
        if (dot>0.f) { hit[0]=origin[0]+along[0]; hit[1]=origin[1]+along[1]; hit[2]=origin[2]+along[2]; }
        else diff(hit,origin,along);
    }
    return dist(hit,eye);
}
static float separation(const BrRuntime *rail,const BanjoCameraMath *m,const BrSpline *sp,
                        const float *focus,const float *point) {
    float where=closest(sp->knots,sp->count,focus);
    if (where==0.0 || where==1.0)
        return project_distance(m,sp->knots,sp->count,where,focus,point);
    if (where<rail->param) return arc(sp->knots,sp->count,where,rail->param,(rail->param-where)/15.f);
    return arc(sp->knots,sp->count,rail->param,where,(where-rail->param)/15.f);
}

static int cube_of_int(int position) {
    return position>=0 ? position/1000 : position/1000-1;
}
static void clamp_cube(const BrData *d,int cube[3]) {
    for (int i=0;i<3;i++) {
        int max=d->cube_min[i]+d->cube_width[i]-1;
        if (cube[i]<d->cube_min[i]) cube[i]=d->cube_min[i];
        if (cube[i]>max) cube[i]=max;
    }
}
static int spline_in_cube(const BrData *d,int actor,const int cube[3]) {
    for (int i=0;i<d->spline_count;i++) {
        if (d->splines[i].actor!=actor) continue;
        int home[3];
        for (int a=0;a<3;a++) home[a]=cube_of_int((int)d->splines[i].origin[a]);
        clamp_cube(d,home);
        if (home[0]==cube[0] && home[1]==cube[1] && home[2]==cube[2]) return i;
    }
    return -1;
}
static int slice_has_export(const BrData *d,int y) {
    for (int i=0;i<d->volume_count;i++) if (d->volumes[i].cube[1]==y) return 1;
    for (int i=0;i<d->spline_count;i++) {
        int home=cube_of_int((int)d->splines[i].origin[1]);
        int cube[3]={0,home,0}; clamp_cube(d,cube);
        if (cube[1]==y) return 1;
    }
    return 0;
}
static int find_spline(const BrData *d,int actor,const int32_t player[3]) {
    int center[3],lo[3],hi[3];
    for (int i=0;i<3;i++) {
        float v=(float)player[i];
        center[i]=v>=0.f ? (int)(v/1000.f) : (int)(v/1000.f-1.f);
    }
    clamp_cube(d,center);
    for (int i=0;i<3;i++) {
        int max=d->cube_min[i]+d->cube_width[i]-1;
        lo[i]=center[i]-1; if (lo[i]<d->cube_min[i]) lo[i]=d->cube_min[i];
        hi[i]=center[i]+1; if (hi[i]>max) hi[i]=max;
    }
    for (int x=lo[0];x<=hi[0];x++) for (int y=lo[1];y<=hi[1];y++) for (int z=lo[2];z<=hi[2];z++) {
        int cube[3]={x,y,z}, found=spline_in_cube(d,actor,cube);
        if (found>=0) return found;
    }
    int maxx=d->cube_min[0]+d->cube_width[0]-1, maxz=d->cube_min[2]+d->cube_width[2]-1;
    for (int y=d->cube_min[1];y<=d->cube_min[1]+d->cube_width[1]-1;y++) {
        if (!slice_has_export(d,y)) continue;
        for (int x=d->cube_min[0];x<=maxx;x++) for (int z=d->cube_min[2];z<=maxz;z++) {
            int cube[3]={x,y,z}, found=spline_in_cube(d,actor,cube);
            if (found>=0) return found;
        }
    }
    return -1;
}
static int spline_at_point(const BrData *d,const float *pos) {
    for (int i=0;i<d->spline_count;i++) {
        const BrSpline *sp=d->splines+i;
        for (int k=0;k<sp->count;k++) {
            const float *p=sp->knots+k*3;
            if (p[0]==pos[0] && p[1]==pos[1] && p[2]==pos[2]) return i;
        }
    }
    return -1;
}
static int ray_blocked(const BqModel *opa,const BqModel *xlu,const float *eye,const float *point) {
    float end[3]; memcpy(end,point,12); BqHit hit;
    return bq_segment(opa,xlu,eye,end,BR_RAY_FILTER,&hit);
}
static int snap_param(const BrSpline *sp,float *param,const float *eye,const BqModel *opa,const BqModel *xlu) {
    float point[3];
    sample(*param,sp->count,sp->knots,point);
    int hit=ray_blocked(opa,xlu,eye,point);
    if (hit<0) return -1;
    if (hit==0) return 0;
    sample(1.f,sp->count,sp->knots,point);
    hit=ray_blocked(opa,xlu,eye,point);
    if (hit<0) return -1;
    if (hit==0) { *param=1.f; return 0; }
    sample(0.f,sp->count,sp->knots,point);
    hit=ray_blocked(opa,xlu,eye,point);
    if (hit<0) return -1;
    if (hit==0) { *param=0.f; return 0; }
    return 0;
}

static int predicate(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in,
                     const float *point,int record) {
    const BrSpline *sp=rail_data->splines+s->rail.spline;
    float focus[3]={in->player[0]+s->camera.lead[0], in->player[1]+60.f, in->player[2]+s->camera.lead[2]};
    /* Dry Banjo. Rare selects 20/200 only while underwater. */
    s->rail.lead_near=80.f; s->rail.lead_far=200.f;
    float sp30=separation(&s->rail,math,sp,focus,point);
    double wrap=wrap_of(sp->knots,sp->count);
    float ahead_p=advance(sp->knots,sp->count,s->rail.param,(double)in->dt*1000.0,wrap);
    float behind_p=advance(sp->knots,sp->count,s->rail.param,(double)in->dt*-1000.0,wrap);
    float ahead[3],behind[3];
    sample(ahead_p,sp->count,sp->knots,ahead);
    sample(behind_p,sp->count,sp->knots,behind);
    float d_plus=dist(focus,ahead), d_minus=dist(focus,behind);
    float step=0.f;
    int result;
    if (fabsf(d_plus-d_minus)>3.f) {
        float dir=d_plus<d_minus ? 1.f : -1.f;
        if (sp30>550.f) step=ml_map_f(sp30,550.f,650.f,0.f,1500.f)*dir;
        else if (sp30<500.f) step=ml_map_f(sp30,400.f,500.f,1500.f,0.f)*-dir;
        if (fabsf(s->rail.step)<fabsf(step)) s->rail.step+=(step-s->rail.step)*0.08f;
        else s->rail.step=step;
        s->rail.param=advance(sp->knots,sp->count,s->rail.param,(double)in->dt*(double)s->rail.step,wrap);
        if ((step>0.f && s->rail.param==1.0 && s->rail.allow_one==0)
            || (step<0.f && s->rail.param==0.0 && s->rail.allow_zero==0)) result=0;
        else result=step!=0.f ? 1 : 2;
    } else result=1;
    s->rail.distance=sp30; s->rail.predicate=result;
    if (record) { s->rail.engage_distance=sp30; s->rail.engage_predicate=result; }
    return result;
}

static int try_engage(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in,
                      const BrVolume *volume,const int32_t player[3],const BqModel *opa,const BqModel *xlu) {
    BrRuntime *rail=&s->rail;
    if (rail->actor==volume->spline_actor || rail->actor==-1) return 0;
    int located=find_spline(rail_data,volume->spline_actor,player);
    if (located<0) return 0;
    int index=spline_at_point(rail_data,rail_data->splines[located].origin);
    if (index<0) return 0;
    const BrSpline *sp=rail_data->splines+index;
    rail->allow_zero=0; rail->allow_one=0;
    if (sp->scale==1) rail->allow_zero=1;
    else if (sp->scale==2) rail->allow_one=1;
    else if (sp->scale==3) { rail->allow_zero=1; rail->allow_one=1; }
    rail->previous=(uint8_t)s->camera.state;
    memcpy(rail->captured,s->camera.position,12);
    rail->blend=0.f;
    rail->actor=sp->actor;
    rail->spline=index;
    rail->param=closest(sp->knots,sp->count,s->camera.position);
    if (snap_param(sp,&rail->param,s->camera.position,opa,xlu)<0) return -1;
    rail->phase=1;
    sample(rail->param,sp->count,sp->knots,rail->sample);
    if (predicate(s,math,in,rail->sample,1)==1) {
        s->camera.state=0x12; s->camera.mode=0xA; s->focus_mode=4;
        s->position_gain=3.f; s->position_response=8.f;
        s->rotation_gain=5.f; s->rotation_response=10.f;
        rail->lead_near=100.f; rail->lead_far=100.f;
        return 0;
    }
    rail->actor=0;
    return 0;
}

static int inside(const BrVolume *v,const int32_t *p) {
    for (int i=0;i<3;i++)
        if (!((v->center[i]-v->radius)<p[i] && p[i]<(v->center[i]+v->radius))) return 0;
    return 1;
}
static void visit_cubes(const BrData *d,const int32_t *player,int (*out)[3],int *count) {
    int rel[3];
    for (int i=0;i<3;i++) rel[i]=cube_of_int(player[i])-d->cube_min[i];
    int interior=1;
    for (int i=0;i<3;i++) if (!(rel[i]>0 && rel[i]<d->cube_width[i]-1)) interior=0;
    *count=0;
    if (interior) {
        for (int z=-1;z<=1;z++) for (int y=-1;y<=1;y++) for (int x=-1;x<=1;x++) {
            out[*count][0]=d->cube_min[0]+rel[0]+x;
            out[*count][1]=d->cube_min[1]+rel[1]+y;
            out[*count][2]=d->cube_min[2]+rel[2]+z;
            (*count)++;
        }
    } else {
        for (int x=rel[0]-1;x<=rel[0]+1;x++) if (x>=0 && x<d->cube_width[0])
            for (int y=rel[1]-1;y<=rel[1]+1;y++) if (y>=0 && y<d->cube_width[1])
                for (int z=rel[2]-1;z<=rel[2]+1;z++) if (z>=0 && z<d->cube_width[2]) {
                    out[*count][0]=d->cube_min[0]+x;
                    out[*count][1]=d->cube_min[1]+y;
                    out[*count][2]=d->cube_min[2]+z;
                    (*count)++;
                }
    }
}

void br_reset(BrRuntime *rail) {
    memset(rail,0,sizeof(*rail));
    rail->spline=-1; rail->lead_near=110.f; rail->lead_far=180.f;
}
void br_end(BmState *s) { br_reset(&s->rail); }

int br_triggers(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in,
                const BqModel *opa,const BqModel *xlu) {
    if (!rail_data || !rail_data->volumes || !rail_data->splines || rail_data->volume_count<1) return 0;
    int32_t player[3];
    for (int i=0;i<3;i++) player[i]=(int32_t)in->player[i];
    int cubes[27][3], count=0;
    visit_cubes(rail_data,player,cubes,&count);
    for (int c=0;c<count;c++) {
        for (int v=0;v<rail_data->volume_count;v++) {
            const BrVolume *volume=rail_data->volumes+v;
            if (volume->cube[0]!=cubes[c][0] || volume->cube[1]!=cubes[c][1] || volume->cube[2]!=cubes[c][2]) continue;
            if (volume->marker_bit!=0 || !inside(volume,player)) continue;
            if (volume->actor==0x2A) { if (s->rail.actor) s->rail.actor=-1; }
            else if (volume->actor==0x16) {
                int rc=try_engage(s,math,in,volume,player,opa,xlu);
                if (rc<0) return -1;
            }
        }
    }
    return 0;
}

static void ease_lead(BanjoCamera *c,const BanjoCameraInput *in,float near_amp,float far_amp) {
    float dx=in->player[0]-c->position[0], dz=in->player[2]-c->position[2];
    float amplitude=map(fabsf((float)(angle(c->rotation[1]-in->visible_yaw)-180.0)),0,180,near_amp,far_amp);
    float lead[3];
    vector(lead,in->visible_yaw,map(sqrtf(dx*dx+dz*dz),300,450,0,amplitude));
    for (int i=0;i<3;i++) c->lead[i]+=(lead[i]-c->lead[i])*0.08f;
}

void br_drive(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in) {
    if (!rail_data || s->rail.spline<0 || s->rail.spline>=rail_data->spline_count) return;
    if (s->rail.phase==1) s->rail.phase=2;
    ease_lead(&s->camera,in,s->rail.lead_near,s->rail.lead_far);
    if (s->rail.actor<1) { s->rail.actor=0; return; }
    if (predicate(s,math,in,s->camera.position,0)==0) { s->rail.actor=0; return; }
    const BrSpline *sp=rail_data->splines+s->rail.spline;
    float point[3];
    sample(s->rail.param,sp->count,sp->knots,point);
    if (s->rail.blend<1.f) {
        float rate=ml_map_f(s->rail.blend,0.5f,1.f,0.05f,0.01f);
        s->rail.blend+=30.f*in->dt*rate;
        if (s->rail.blend<1.f) {
            for (int i=0;i<3;i++) point[i]=s->rail.captured[i]+(point[i]-s->rail.captured[i])*s->rail.blend;
        }
    }
    memcpy(s->camera.position,point,12);
    float target[3]={in->player[0], in->player[1]+60.f, in->player[2]};
    memcpy(s->camera.focus,target,12);
    float angles[3];
    look(math,target,s->camera.position,angles);
    smooth_angles(&s->camera,angles,s->rotation_gain,s->rotation_response,in->dt);
}
