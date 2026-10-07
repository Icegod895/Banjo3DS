#include "contact.h"
/* Static source contracts and independent proof: README.md in this directory.
 * Preserve float operation order; no analytic sweep or triangle deduplication. */
#include <math.h>
#include <string.h>
/* Optional isolated world-state reader. Default preserves immutable queries. */
#ifndef BQ_VERTEX_COMPONENT
#define BQ_VERTEX_COMPONENT(m,v,a) s16((m)->vertices+24+16*(v)+2*(a))
#endif

static int16_t s16(const uint8_t *p){return (int16_t)((unsigned)p[0]*256+p[1]);}
static uint32_t u32(const uint8_t *p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static float dot(const float *a,const float *b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static void diff(float *d,const float *a,const float *b){for(int i=0;i<3;i++)d[i]=a[i]-b[i];}
static void norm(float *v){float q=dot(v,v);if(q!=0){float k=1.0/sqrtf(q);for(int i=0;i<3;i++)v[i]*=k;}}
static float distance(const float *a,const float *b){float d[3];diff(d,a,b);return sqrtf(dot(d,d));}
static void length(float *v,float n){float q=sqrtf(dot(v,v));if(q!=0){float k=n/q;for(int i=0;i<3;i++)v[i]*=k;}}
static const uint8_t *record(const BqModel *m,int r){return m->collision+24+4*m->grid[8]+12*r;}
static int valid(const BqModel *o,const BqModel *x,const float *a,const float *b,float r){
    if(!o || o->role || (x && x->role!=1) || !a || !b || !isfinite(r) || r<=.5f || r>10000)return 0;
    for(int i=0;i<3;i++)if(!isfinite(a[i]) || !isfinite(b[i]) || fabsf(a[i])>1e6f || fabsf(b[i])>1e6f)return 0;
    return 1;
}
static void identity(const BqModel *m,const BcTriangle *t,BqHit *h){
    const uint8_t *r=record(m,t->record);h->role=m->role;h->occurrence=t->record;
    h->cell=t->cell;h->surface=s16(r+6);h->flags=u32(r+8);
    for(int i=0;i<3;i++)h->indices[i]=(uint16_t)s16(r+2*i);
}
static void triangle(const BqModel *m,int r,int cell,BcTriangle *t){
    t->record=r;t->cell=cell;const uint8_t *p=record(m,r);
    for(int j=0;j<3;j++)for(int i=0;i<3;i++)t->xyz[j][i]=BQ_VERTEX_COMPONENT(m,s16(p+2*j),i);
    diff(t->ab,t->xyz[1],t->xyz[0]);diff(t->ac,t->xyz[2],t->xyz[0]);
    t->normal[0]=t->ab[1]*t->ac[2]-t->ab[2]*t->ac[1];
    t->normal[1]=t->ab[2]*t->ac[0]-t->ab[0]*t->ac[2];
    t->normal[2]=t->ab[0]*t->ac[1]-t->ab[1]*t->ac[0];norm(t->normal);
}
static int cell_box(const BqModel *m,const float *lo,const float *hi,int *a,int *b){
    for(int i=0;i<3;i++)if(hi[i]<=-m->global_norm || lo[i]>=m->global_norm)return 0;
    for(int i=0;i<3;i++){
        a[i]=b[i]=0;if(!m->grid[9])continue;
        int l=(int)lo[i]/m->grid[9]-(lo[i]<0),h=(int)hi[i]/m->grid[9]-(hi[i]<0);
        if(l<m->grid[i])l=m->grid[i];
        if(l>m->grid[i+3])l=m->grid[i+3];
        if(h<m->grid[i])h=m->grid[i];
        if(h>m->grid[i+3])h=m->grid[i+3];
        a[i]=l-m->grid[i];b[i]=h-m->grid[i];
    }
    return (int64_t)(b[0]-a[0]+1)*(b[1]-a[1]+1)*(b[2]-a[2]+1)>100?-1:1;
}
static int overlaps_box(const BcTriangle *t,const float *lo,const float *hi){
    for(int i=0;i<3;i++){
        float l=t->xyz[0][i],h=l;
        for(int j=1;j<3;j++){if(t->xyz[j][i]<l)l=t->xyz[j][i];if(t->xyz[j][i]>h)h=t->xyz[j][i];}
        if(l>hi[i] || h<lo[i])return 0;
    }return 1;
}
/* Original plane test first, inclusive projection, strict-radius vertices/edges. */
static int overlaps(const BcTriangle *t,const float *p,float radius){
    float v[3][3],q[3];diff(v[0],p,t->xyz[0]);float theta=dot(v[0],t->normal);
    if(theta<=-(radius-.5) || theta>=radius-.5)return 0;
    float n2=dot(t->normal,t->normal);if(n2==0)return 0;
    float k=-theta/n2;for(int i=0;i<3;i++)q[i]=p[i]+k*t->normal[i];
    int axis=fabsf(t->normal[0])>fabsf(t->normal[1])?0:1;
    if(fabsf(t->normal[2])>fabsf(t->normal[axis]))axis=2;
    int j=(axis+1)%3,l=(axis+2)%3;
    float a=q[j]-t->xyz[0][j],b=t->ab[j],c=t->ac[j];
    float d=q[l]-t->xyz[0][l],e=t->ab[l],f=t->ac[l],det=b*f-e*c;
    float u=(a*f-d*c)/det,w=(b*d-e*a)/det;
    if(0<=u && u<=1 && 0<=w && w<=1 && 0<=1.f-(u+w))return 1;
    for(int i=0;i<3;i++){diff(v[i],p,t->xyz[i]);if(dot(v[i],v[i])<radius*radius)return 1;}
    for(int i=0;i<3;i++){
        float edge[3];diff(edge,t->xyz[(i+1)%3],t->xyz[i]);float n=dot(edge,edge);norm(edge);
        float along=dot(edge,v[i]);if(0<=along && along*along<=n){
            for(int z=0;z<3;z++)q[z]=v[i][z]-along*edge[z];
            if(dot(q,q)<radius*radius)return 1;
        }
    }return 0;
}
static int sphere_model(const BqModel *m,const float *p,float radius,uint32_t filter,BqHit *hit){
    float lo[3],hi[3],sum[3]={0};int a[3],b[3],found=0;
    for(int i=0;i<3;i++){lo[i]=p[i]-(radius+.5);hi[i]=p[i]+(radius+.5);}
    int result=cell_box(m,lo,hi,a,b);if(result<=0)return result;
    for(int z=a[2];z<=b[2];z++)for(int y=a[1];y<=b[1];y++)for(int x=a[0];x<=b[0];x++){
        int cell=x+y*m->grid[6]+z*m->grid[7],first=s16(m->collision+24+4*cell),count=s16(m->collision+26+4*cell);
        for(int r=first;r<first+count;r++){
            if(u32(record(m,r)+8)&filter)continue;
            BcTriangle t;triangle(m,r,cell,&t);if(!overlaps_box(&t,lo,hi) || !overlaps(&t,p,radius))continue;
            for(int i=0;i<3;i++)sum[i]+=t.normal[i];
            identity(m,&t,hit);found=1;
        }
    }
    if(found){norm(sum);memcpy(hit->normal,sum,12);memcpy(hit->position,p,12);}return found;
}
int bc_sphere(const BqModel *o,const BqModel *x,const float p[3],float r,uint32_t f,BqHit *out){
    if(!out || !valid(o,x,p,p,r))return -1;
    BqHit h={0};int a=sphere_model(o,p,r,f,&h);if(a<0)return -1;
    if(x){int b=sphere_model(x,p,r,f,&h);if(b<0)return -1;a|=b;}
    if(a)*out=h;
    return a;
}
static int active(const BqModel *m,const float *p,const float *end,float radius,uint32_t filter,BcScratch *s){
    float lo[3],hi[3],velocity[3];int a[3],b[3],count=0;diff(velocity,end,p);
    float margin=radius+.5;
    for(int i=0;i<3;i++){lo[i]=(p[i]<end[i]?p[i]:end[i])-margin;hi[i]=(p[i]<end[i]?end[i]:p[i])+margin;}
    int result=cell_box(m,lo,hi,a,b);if(result<=0)return result;
    for(int z=a[2];z<=b[2];z++)for(int y=a[1];y<=b[1];y++)for(int x=a[0];x<=b[0];x++){
        int cell=x+y*m->grid[6]+z*m->grid[7],first=s16(m->collision+24+4*cell),n=s16(m->collision+26+4*cell);
        for(int r=first;r<first+n;r++){
            uint32_t flags=u32(record(m,r)+8);if(flags&filter)continue;
            BcTriangle t;triangle(m,r,cell,&t);if(!overlaps_box(&t,lo,hi))continue;
            if(flags&0x10000){float d[3];diff(d,p,t.xyz[0]);if(dot(d,t.normal)<0)for(int i=0;i<3;i++)t.normal[i]=-t.normal[i];}
            else if(dot(t.normal,velocity)>0)continue;
            if(count==100)return -1;
            s->triangles[count++]=t;
        }
    }return count;
}
static int iteration(const BcScratch *s,int n,const float *p,float radius,float *normal){
    int last=-1;for(int j=0;j<3;j++)normal[j]=0;
    for(int i=0;i<n;i++)if(overlaps(s->triangles+i,p,radius)){
        last=i;for(int j=0;j<3;j++)normal[j]+=s->triangles[i].normal[j];
    }return last;
}
static int moving_model(const BqModel *m,const float *p,float *end,float radius,int steps,uint32_t f,BcScratch *s,BqHit *hit){
    int n=active(m,p,end,radius,f,s);if(n<=0)return n;
    float normal[3];int last=iteration(s,n,end,radius,normal);if(last<0)return 0;
    float d[3];diff(d,end,p);memcpy(end,p,12);memcpy(hit->normal,normal,12);
    float lo=0,hi=1;
    for(int i=0;i<steps;i++){
        float mid=(lo+hi)*.5,q[3];for(int j=0;j<3;j++)q[j]=p[j]+mid*d[j];
        int r=iteration(s,n,q,radius,normal);
        if(r>=0){last=r;memcpy(hit->normal,normal,12);hi=mid;}else{memcpy(end,q,12);lo=mid;}
    }
    norm(hit->normal);identity(m,s->triangles+last,hit);memcpy(hit->position,end,12);return 1;
}
int bc_moving(const BqModel *o,const BqModel *x,const float p[3],float end[3],float r,int steps,uint32_t f,BcScratch *s,BqHit *out){
    if(!s || !out || !valid(o,x,p,end,r) || steps<0 || steps>32)return -1;
    float e[3];memcpy(e,end,12);BqHit h={0};int a=moving_model(o,p,e,r,steps,f,s,&h);if(a<0)return -1;
    if(x){int b=moving_model(x,p,e,r,steps,f,s,&h);if(b<0)return -1;a|=b;}
    if(a){*out=h;memcpy(end,e,12);}return a;
}
int bc_gated(const BqModel *o,const BqModel *x,const float p[3],float end[3],float r,int steps,uint32_t f,BcScratch *s,BqHit *out){
    if(!valid(o,x,p,end,r))return -1;
    if(r<distance(p,end))return 0;
    return bc_moving(o,x,p,end,r,steps,f,s,out);
}
typedef struct {const BqModel *o,*x;BcScratch *scratch;BcTrace *trace;int error;} World;
static int line(World *w,const float *a,float *b,float *n,uint32_t filter){
    BqHit hit;w->trace->line_calls++;int r=bq_segment(w->o,w->x,a,b,filter,&hit);
    if(r<0)w->error=1;
    if(r>0)memcpy(n,hit.normal,12);
    return r>0;
}
static int sphere(World *w,const float *a,float radius,float *n){
    BqHit hit;w->trace->sphere_calls++;int r=bc_sphere(w->o,w->x,a,radius,0x9e0000,&hit);
    if(r<0)w->error=1;
    if(r>0)memcpy(n,hit.normal,12);
    return r>0;
}
static int gated(World *w,const float *a,float *b,float radius,float *n,int steps){
    w->trace->gated_calls++;if(radius<distance(a,b))return 0;
    w->trace->moving_calls++;BqHit hit;int r=bc_moving(w->o,w->x,a,b,radius,steps,0x9e0000,w->scratch,&hit);
    if(r<0)w->error=1;
    if(r>0)memcpy(n,hit.normal,12);
    return r>0;
}
static void contact(World *w,float *previous,float *camera){
    float normal[3],a[3],b[3],offset[3];
    /* The condition queries again BEFORE checking i<1. */
    for(int i=0;sphere(w,previous,35,normal) && i<1;i++){
        if(dot(normal,normal)<.01)break;
        for(int j=0;j<3;j++)previous[j]+=1.5f*normal[j];
    }
    memcpy(w->trace->pushed_previous,previous,12);
    memcpy(a,previous,12);memcpy(b,camera,12);diff(offset,b,a);norm(offset);
    for(int i=0;i<3;i++){offset[i]*=35.f;b[i]+=offset[i];}
    memcpy(w->trace->extended_end,b,12);
    int l=line(w,a,b,normal,0x9e0000);for(int i=0;i<3;i++)b[i]-=offset[i];
    memcpy(w->trace->subtracted_end,b,12);
    int m=gated(w,a,b,35,normal,3);
    if(l || m){
        float d[3],clipped[3],change[3];diff(d,camera,previous);diff(clipped,b,a);diff(change,d,clipped);
        float dp=-dot(normal,change);for(int i=0;i<3;i++)camera[i]+=dp*normal[i];
        diff(offset,camera,previous);norm(offset);
        for(int i=0;i<3;i++){offset[i]*=35.f;camera[i]+=offset[i];}
        line(w,previous,camera,normal,0x9e0000);for(int i=0;i<3;i++)camera[i]-=offset[i];
    }
}
int bc_contact(const BqModel *o,const BqModel *x,float previous[3],float camera[3],BcScratch *s,BcTrace *trace){
    if(!s || !trace || !valid(o,x,previous,camera,35))return -1;
    float a[3],b[3];memcpy(a,previous,12);memcpy(b,camera,12);BcTrace t={0};World w={o,x,s,&t,0};
    contact(&w,a,b);if(w.error)return -1;
    t.changed=b[0]!=camera[0] || b[1]!=camera[1] || b[2]!=camera[2];
    memcpy(previous,a,12);memcpy(camera,b,12);*trace=t;return (int)t.changed;
}
/* Original libultra sin/cos finite subset; host/newlib trig differs in bits. */
static float trig(float a,int cosine){
    uint32_t bits;memcpy(&bits,&a,4);unsigned e=(bits>>22)&511;
    if(!cosine && e<0xe6)return a;
    double x=cosine?fabs(a):a;int n=0;
    if(cosine || e>=0xff){double dn=x*0x1.45f306dc9c883p-2+(cosine?.5:0);
        n=(int)(dn+(dn>=0?.5:-.5));dn=n-(cosine?.5:0);
        x=(x-dn*0x1.921fb50000000p+1)-dn*0x1.110b4611a6263p-25;}
    double square=x*x,p=((0x1.5dbdf0e314bfep-19*square-0x1.9f6ffeea56814p-13)*square
        +0x1.110ed3804c2a0p-7)*square-0x1.55554bc83656dp-3;
    float r=(float)(x+(x*square)*p);return n&1?-r:r;
}
static void rotate(float *v,float yaw){
    yaw*=3.141592654/180.0;float c=trig(yaw,1),s=trig(yaw,0);
    float x=v[2]*s+v[0]*c;v[2]=v[2]*c-v[0]*s;v[0]=x;
}
static void obstruction(World *w,float *camera,const float *target,BcState *s){
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
    float minimum=fmaxf(150.f,dist-100.f);
    for(unsigned k=0;k<sizeof(angles)/sizeof(*angles);k++){
        w->trace->recovery_attempts++;
        for(int i=0;i<3;i++)offset[i]=dir[i]*-dist;
        rotate(offset,angles[k]);for(int i=0;i<3;i++)end[i]=target[i]+offset[i];
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
int bc_state_b(const BqModel *o,const BqModel *x,float previous[3],float camera[3],const float target[3],BcState *state,BcScratch *scratch,BcTrace *trace){
    if(!state || state->counter>4 || !scratch || !trace || !valid(o,x,previous,camera,35) || !valid(o,x,target,target,35))return -1;
    float a[3],b[3];memcpy(a,previous,12);memcpy(b,camera,12);BcState s=*state;BcTrace t={0};World w={o,x,scratch,&t,0};
    contact(&w,a,b);t.changed=b[0]!=camera[0] || b[1]!=camera[1] || b[2]!=camera[2];
    if(t.changed)obstruction(&w,b,target,&s);
    if(w.error)return -1;
    memcpy(previous,a,12);memcpy(camera,b,12);*state=s;*trace=t;return (int)t.changed;
}
