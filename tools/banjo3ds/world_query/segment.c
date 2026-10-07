#include "segment.h"
#include <math.h>
#include <string.h>

/* Optional isolated world-state reader. Default preserves immutable queries. */
#ifndef BQ_VERTEX_COMPONENT
#define BQ_VERTEX_COMPONENT(m,v,a) s16((m)->vertices+24+16*(v)+2*(a))
#endif

static uint16_t u16(const uint8_t *p) { return (uint16_t)((unsigned)p[0]*256+p[1]); }
static int16_t s16(const uint8_t *p) { return (int16_t)u16(p); }
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0]<<24 | (uint32_t)p[1]<<16 | (uint32_t)p[2]<<8 | p[3];
}
int bq_open(BqModel *out,const uint8_t *p,size_t size) {
    if(!out || !p || size<112 || memcmp(p,"B3Q1",4) || u16(p+4)!=1 ||
       u16(p+6)>1 || u32(p+8)!=(uint32_t)(0x14cf+u16(p+6)) || u32(p+12)!=0x3f800000)return 0;
    uint32_t vl=u32(p+24),cl=u32(p+28);
    if(vl<24 || cl<24 || (uint64_t)64+vl+cl!=size)return 0;
    BqModel m;memset(&m,0,sizeof(m));m.vertices=p+64;m.collision=p+64+vl;
    m.role=u16(p+6);m.vertex_count=u16(m.vertices+20);m.global_norm=s16(m.vertices+22);
    for(int i=0;i<11;i++)m.grid[i]=s16(m.collision+2*i);
    int nc=m.grid[8],nt=m.grid[10];
    if(!m.vertex_count || m.vertex_count>32767 || nc<=0 || nt<0 || m.grid[9]<0 || m.global_norm<=0 ||
       vl!=24u+16u*m.vertex_count || cl!=24u+4u*nc+12u*nt)return 0;
    int dims[3];for(int i=0;i<3;i++) {dims[i]=m.grid[i+3]-m.grid[i]+1;if(dims[i]<=0)return 0;}
    if(m.grid[9] && (m.grid[6]!=dims[0] || m.grid[7]!=(int64_t)dims[0]*dims[1] ||
        nc!=(int64_t)dims[0]*dims[1]*dims[2]))return 0;
    for(int c=0;c<nc;c++) {
        int first=s16(m.collision+24+4*c),n=s16(m.collision+26+4*c);
        if(first<0 || n<0 || first+n>nt)return 0;
    }
    for(int r=0;r<nt;r++)for(int j=0;j<3;j++)
        if(u16(m.collision+24+4*nc+12*r+2*j)>=m.vertex_count)return 0;
    *out=m;return 1;
}
static float dot(const float *a,const float *b) {return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
static void bounds(const float *a,const float *b,int *lo,int *hi,float *d) {
    for(int i=0;i<3;i++) {
        lo[i]=(int)(a[i]<b[i]?a[i]:b[i])-1;
        hi[i]=(int)(a[i]<b[i]?b[i]:a[i])+1;
        d[i]=b[i]-a[i];
    }
}
static int model_query(const BqModel *m,const float *start,float *end,uint32_t filter,BqHit *hit) {
    int lo[3],hi[3],a[3]={0},b[3]={0};float direction[3];
    bounds(start,end,lo,hi,direction);
    for(int i=0;i<3;i++)if(hi[i]<=-m->global_norm || m->global_norm<=lo[i])return 0;
    if(m->grid[9])for(int i=0;i<3;i++) {
        int l=lo[i]/m->grid[9]-(lo[i]<0),h=hi[i]/m->grid[9]-(hi[i]<0);
        if(l<m->grid[i])l=m->grid[i];
        if(l>m->grid[i+3])l=m->grid[i+3];
        if(h<m->grid[i])h=m->grid[i];
        if(h>m->grid[i+3])h=m->grid[i+3];
        a[i]=l-m->grid[i];b[i]=h-m->grid[i];
    }
    if((int64_t)(b[0]-a[0]+1)*(b[1]-a[1]+1)*(b[2]-a[2]+1)>100)return -1;
    int found=0;
    /* Cell box is captured once. Only triangle bounds/direction change on hit. */
    for(int z=a[2];z<=b[2];z++)for(int y=a[1];y<=b[1];y++)for(int x=a[0];x<=b[0];x++) {
        int cell=x+y*m->grid[6]+z*m->grid[7];
        int first=s16(m->collision+24+4*cell),count=s16(m->collision+26+4*cell);
        for(int r=first;r<first+count;r++) {
            const uint8_t *record=m->collision+24+4*m->grid[8]+12*r;
            uint32_t flags=u32(record+8);if(flags&filter)continue;
            float tri[3][3];uint16_t indices[3];
            for(int j=0;j<3;j++) {
                indices[j]=u16(record+2*j);
                for(int i=0;i<3;i++)tri[j][i]=BQ_VERTEX_COMPONENT(m,indices[j],i);
            }
            int reject=0;
            for(int i=0;i<3;i++)if((tri[0][i]<lo[i] && tri[1][i]<lo[i] && tri[2][i]<lo[i]) ||
               (tri[0][i]>hi[i] && tri[1][i]>hi[i] && tri[2][i]>hi[i]))reject=1;
            if(reject)continue;
            float ab[3],ac[3],n[3],ls[3],le[3];
            for(int i=0;i<3;i++){ab[i]=tri[1][i]-tri[0][i];ac[i]=tri[2][i]-tri[0][i];}
            n[0]=ab[1]*ac[2]-ab[2]*ac[1];n[1]=ab[2]*ac[0]-ab[0]*ac[2];n[2]=ab[0]*ac[1]-ab[1]*ac[0];
            if(fabsf(n[0])>100000.f || fabsf(n[1])>100000.f || fabsf(n[2])>100000.f)
                for(int i=0;i<3;i++)n[i]/=100000.f;
            for(int i=0;i<3;i++){ls[i]=start[i]-tri[0][i];le[i]=end[i]-tri[0][i];}
            float ds=dot(ls,n),de=dot(le,n);
            if((ds>=0 && de>=0) || (ds<=0 && de<=0))continue;
            if((flags&0x10000) && ds<0)for(int i=0;i<3;i++)n[i]=-n[i];
            float denom=dot(n,direction),plane=dot(tri[0],n);
            if(denom==0)continue;
            float t=-(dot(n,start)-plane)/denom;
            if(t<=0 || t>=1)continue;
            float p[3];for(int i=0;i<3;i++)p[i]=start[i]+t*direction[i];
            int axis=fabsf(n[0])>fabsf(n[1])?0:1;
            axis=fabsf(n[2])>fabsf(n[axis])?2:axis;
            int j=(axis+1)%3,k=(axis+2)%3;
            float f0=p[j]-tri[0][j],f1=ab[j],f2=ac[j];
            float e0=p[k]-tri[0][k],e1=ab[k],e2=ac[k];
            float det=f1*e2-e1*f2;
            float u=(f0*e2-e0*f2)/det;if(u<0 || 1<u)continue;
            float v=(f1*e0-e1*f0)/det;if(v<0 || v>1 || u+v>1)continue;
            memcpy(end,p,12);memcpy(hit->position,p,12);
            float length=dot(n,n);
            if(length!=0) {
                float inverse=1.0/sqrtf(length);
                for(int i=0;i<3;i++)hit->normal[i]=n[i]*inverse;
            }else memcpy(hit->normal,n,12);
            hit->role=m->role;hit->occurrence=r;hit->cell=cell;
            hit->surface=s16(record+6);hit->flags=flags;memcpy(hit->indices,indices,6);
            found=1;bounds(start,end,lo,hi,direction);
        }
    }
    return found;
}
int bq_segment(const BqModel *opa,const BqModel *xlu,const float start[3],float end[3],uint32_t filter,BqHit *out) {
    if(!opa || opa->role!=0 || (xlu && xlu->role!=1) || !start || !end || !out)return -1;
    for(int i=0;i<3;i++)if(!isfinite(start[i]) || !isfinite(end[i]) || fabsf(start[i])>1e6f || fabsf(end[i])>1e6f)return -1;
    float shortened[3];memcpy(shortened,end,12);BqHit h;memset(&h,0,sizeof(h));int found=0;
    if(!xlu || (filter&0x80001f00)!=0x80001f00) {
        found=model_query(opa,start,shortened,filter,&h);if(found<0)return -1;
    }
    if(xlu) {int result=model_query(xlu,start,shortened,filter,&h);if(result<0)return -1;found|=result;}
    if(found){memcpy(end,shortened,12);*out=h;}return found;
}
int bq_camera_terrain(const BqModel *opa,const BqModel *xlu,const float camera[3],float *height) {
    if(!camera || !height)return -1;
    float start[3]={camera[0],camera[1]+10.f,camera[2]};
    float end[3]={camera[0],camera[1]-600.f,camera[2]};BqHit hit;
    int result=bq_segment(opa,xlu,start,end,0x800000,&hit);
    if(result>=0)*height=result?end[1]:camera[1]-600.f;
    return result;
}
