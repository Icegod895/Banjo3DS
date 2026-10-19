#include "prephysics_response.h"
#include <float.h>
#include <math.h>
#include <string.h>

#ifdef __FAST_MATH__
#error "Original response requires strict floating-point arithmetic"
#endif
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24 &&
               DBL_MANT_DIG==53, "binary32/binary64 required");

static int overlap(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x=(uintptr_t)a, y=(uintptr_t)b;
    return x>=y ? x-y<nb : y-x<na;
}

/* Defined subset of mlNormalizeAngle; preserve double subtraction and the
 * negative-angle recursion's float assignment, rather than using fmodf. */
static float heading(float a) {
    int negative=a<0.0;
    if(negative)a=-a;
    if(a>=360.0)a-=360.0*(int32_t)(a/360.0);
    if(negative) {
        a=360.0-a;
        if(a>=360.0)a-=360.0*(int32_t)(a/360.0);
    }
    return a;
}

/* Finite normalized-angle subset of libultra sinf/cosf. Same audited
 * constants as horizontal.c; kept private so the old controller is untouched.
 * Independent tests compile lib/ultralib/src/gu/{sin,cos}f.c, not this helper. */
static float trig(float a, int cosine) {
    uint32_t bits;memcpy(&bits,&a,sizeof(bits));
    unsigned exponent=(bits>>22)&511;
    if(!cosine && exponent<0xe6)return a;
    double x=cosine ? fabs(a) : a;
    int n=0;
    if(cosine || exponent>=0xff) {
        double dn=x*0x1.45f306dc9c883p-2+(cosine ? 0.5 : 0.0);
        n=(int)(dn+(dn>=0 ? 0.5 : -0.5));
        dn=n-(cosine ? 0.5 : 0.0);
        x=(x-dn*0x1.921fb50000000p+1)-dn*0x1.110b4611a6263p-25;
    }
    double square=x*x;
    double p=((0x1.5dbdf0e314bfep-19*square-0x1.9f6ffeea56814p-13)*square
              +0x1.110ed3804c2a0p-7)*square-0x1.55554bc83656dp-3;
    float r=(float)(x+(x*square)*p);
    return n&1 ? -r : r;
}

static int context_valid(const ChHistory *h) {
    if(h->initialized!=1 || !h->serial || h->category<1 || h->category>4 ||
       h->grounded>1 || h->active>1 || h->forced>1 || h->below_special>1 ||
       (h->forced && !h->grounded) || (h->active && !(h->floor_flags&0x50)) ||
       (h->category==1 && h->grounded) ||
       ((h->category==2 || h->category==4) && !h->grounded) ||
       (h->category==3 && !h->below_special) ||
       !isfinite(h->slope_timer) || h->slope_timer<0 || h->slope_timer>1 ||
       !isfinite(h->coefficient) || h->coefficient<0)return 0;
    float length=0;
    for(int i=0;i<3;i++) {
        if(!isfinite(h->support[i]))return 0;
        length+=h->support[i]*h->support[i];
    }
    return isfinite(length) && fabsf(length-1)<=1e-4f &&
           fabsf(h->support[1])<=1 && fabsf(h->support[1])>0.0174519997f;
}

static int evaluate(const OriginalResponseInput *in, uint32_t active,
                    float coefficient, OriginalResponseOutput *out) {
    if(!in || !out || !in->history ||
       overlap(in,sizeof(*in),out,sizeof(*out)) ||
       overlap(in->history,sizeof(*in->history),out,sizeof(*out)))return 0;
    const ChHistory *h=in->history;
    if(in->map!=1 || !context_valid(h) || in->history_serial!=h->serial ||
       !isfinite(in->dt) || in->dt<=0 || in->dt>.05f ||
       !isfinite(in->target_heading) ||
       (double)fabsf(in->target_heading)/360.0>=2147483648.0 ||
       !isfinite(in->target_speed) || !isfinite(in->velocity[0]) ||
       !isfinite(in->velocity[1]))return 0;

    float radians=(float)(heading(in->target_heading)*(3.141592654/180.0));
    float sn=trig(radians,0), cs=trig(radians,1);
    /* func_80256D0C: pitch/X/Y zero, including the original zero additions. */
    float tmp=0.0f+1.0f*in->target_speed;
    float target[2]={tmp*sn+cs*0.0f,tmp*cs-sn*0.0f};
    if(h->grounded) { /* func_80294548, NOT player_isStable or velocity.Y */
        float unit[2]={target[0],target[1]};
        float length=target[0]*target[0]+0.0f+target[1]*target[1];
        if(!isfinite(length))return 0;
        if(length!=0) {
            float inverse=(float)(1.0/sqrtf(length));
            unit[0]*=inverse;unit[1]*=inverse;
        } /* Original copies the vector when squared length is zero. */
        float d=unit[0]*h->support[0]+0.0f*h->support[1]+unit[1]*h->support[2];
        if(!isfinite(d))return 0;
        if(d!=0.0f) {
            float q;
            if(d<0) {
                float start=(float)(d*0.5);
                if(active) {
                    /* ml_map_f descending-output branch, including clamps. */
                    q=((h->slope_timer-0.0f)/(1.0f-0.0f))*(-1.0f-start)+start;
                    if(q< -1.0f)q=-1.0f;
                    if(q>start)q=start;
                }else q=(float)(0.5*d);
                q=(float)(1.0+q);
            }else {
                q=(float)(d*0.2);
                q=(float)(q+1.0);
            }
            target[0]*=q;target[1]*=q;
        }
    }
    OriginalResponseOutput next;
    float ratio=(float)(in->dt/0.0333333);
    for(int i=0;i<2;i++) {
        float scaled_target=target[i]*coefficient;
        float scaled_current=in->velocity[i]*coefficient;
        float delta=scaled_target-scaled_current;
        delta*=ratio;
        float v=in->velocity[i]+delta;
        if(!isfinite(target[i]) || !isfinite(scaled_target) ||
           !isfinite(scaled_current) || !isfinite(delta) || !isfinite(v))return 0;
        next.displacement_velocity[i]=v;
        /* Original compares a float to DOUBLE 0.0001, strictly less. */
        next.stored_velocity[i]=fabsf(v)<0.0001 ? 0.0f : v;
    }
    *out=next;
    return 1;
}

int original_horizontal_response(const OriginalResponseInput *in,
                                 OriginalResponseOutput *out) {
    if(!in || !in->history)return 0;
    return evaluate(in,in->history->active,in->history->coefficient,out);
}

int original_horizontal_response_prephysics(const OriginalResponseInput *in,
    const PrephysicsEngine *engine, uint64_t expected, PrephysicsResponse *out) {
    if(!in || !in->history || !engine || !out ||
       overlap(in,sizeof(*in),out,sizeof(*out)) ||
       overlap(in->history,sizeof(*in->history),out,sizeof(*out)) ||
       overlap(engine,sizeof(*engine),out,sizeof(*out)) ||
       !expected || engine->epoch!=expected || engine->map!=in->map ||
       in->map!=1 || !context_valid(in->history) ||
       in->history_serial!=in->history->serial)return 0;
    PrephysicsResponse next={0};
    if(!ch_select_response(in->history->category,in->history->floor_flags,
                          &engine->response,&next.selection))return 0;
    if(!evaluate(in,next.selection.active,next.selection.coefficient,&next.velocity))return 0;
    next.engine_epoch=engine->epoch;next.history_serial=in->history_serial;next.map=in->map;
    *out=next;return 1;
}
