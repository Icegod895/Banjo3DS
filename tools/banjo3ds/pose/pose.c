#include "pose.h"
#include <math.h>
#include <string.h>
/* Independent implementation of animationfile.c, code_B9770.c,
 * code_BE2C0.c and mlmtx.c; finite canonical animation subset only. */
static unsigned u16(const uint8_t *p) { return (unsigned)p[0]*256+p[1]; }
static int s16(const uint8_t *p) { unsigned v=u16(p); return v<32768?(int)v:(int)v-65536; }
static uint32_t u32(const uint8_t *p) { return (uint32_t)u16(p)*65536+u16(p+2); }
static float f32(const uint8_t *p) { uint32_t v=u32(p); float f; memcpy(&f,&v,4); return f; }
static void identity(float m[4][4]) { memset(m,0,64); for(int i=0;i<4;i++) m[i][i]=1; }
static float trig(float a, bool cosine) {
    uint32_t bits; memcpy(&bits,&a,4); unsigned exponent=(bits>>22)&511;
    if(!cosine && exponent<0xe6) return a;
    double x=cosine?fabs(a):a; int n=0;
    if(cosine || exponent>=0xff) {
        double dn=x*0x1.45f306dc9c883p-2+(cosine?0.5:0.0);
        n=(int)(dn+(dn>=0?0.5:-0.5)); dn=n-(cosine?0.5:0.0);
        x=(x-dn*0x1.921fb50000000p+1)-dn*0x1.110b4611a6263p-25;
    }
    double s=x*x;
    double p=((0x1.5dbdf0e314bfep-19*s-0x1.9f6ffeea56814p-13)*s+0x1.110ed3804c2a0p-7)*s-0x1.55554bc83656dp-3;
    float r=(float)(x+(x*s)*p); return n&1?-r:r;
}
static float spline(float t,float a,float b,float c,float d) {
    if(t<0)t=0;
    if(t>1)t=1;
    float cubic=-.5*a+1.5*b-1.5*c+.5*d;
    float square=a-2.5*b+2.*c-.5*d, linear=-.5*a+0.*b+.5*c+0.*d;
    return ((cubic*t+square)*t+linear)*t+b;
}
static float value(const uint8_t *k,int i) { return s16(k+4*i+2)/64.f; }
static int frame(const uint8_t *k,int i) { return u16(k+4*i)&0x3fff; }
static float channel(const uint8_t *k,int n,int ch,float t) {
    float a=value(k,0), b=value(k,n-1);
    if((int)t<frame(k,0)) {
        float def=ch>=3&&ch<=5?1:0;
        return spline(t/frame(k,0),def,def,a,(u16(k)&0x8000)&&n>1?value(k,1):a);
    }
    if((int)t>=frame(k,n-1)) return spline(t-frame(k,n-1),
        (u16(k+4*(n-1))&0x4000)&&n>1?value(k,n-2):b,b,b,b);
    int i=0; while(frame(k,i+1)<=(int)t)i++;
    float f=(t-frame(k,i))/(frame(k,i+1)-frame(k,i));
    a=value(k,i); b=value(k,i+1);
    unsigned left=u16(k+4*i),right=u16(k+4*(i+1));
    if(!(left&0x4000) && !(right&0x8000))return a+(b-a)*f;
    return spline(f,(left&0x4000)&&i>0?value(k,i-1):a,a,b,
                  (right&0x8000)&&i+2<n?value(k,i+2):b);
}
static void quaternion(const float *angles,float *q) {
    float m[4][4]; identity(m);
    const int axes[3]={2,1,0},rows[3][2]={{1,2},{0,2},{0,1}};
    for(int n=0;n<3;n++) {
        int axis=axes[n]; float a=angles[axis]; if(a==0)continue;
        float rad=axis==1?(float)(a*(3.141592654/180.0)):a*(float)(3.141592654/180.0);
        float s=trig(rad,false),c=trig(rad,true); if(axis==1)s=-s;
        int i=rows[axis][0],j=rows[axis][1];
        for(int k=0;k<3;k++) {float x=m[i][k],y=m[j][k]; m[i][k]=x*c+y*s; m[j][k]=x*(-s)+y*c;}
    }
    float trace=m[0][0]+m[1][1]+m[2][2];
    if(trace>0) {
        float root=sqrtf((float)(trace+1.0)),f=.5/root; q[3]=root*.5;
        for(int i=0;i<3;i++) {int j=(i+1)%3,k=(i+2)%3; q[i]=(m[j][k]-m[k][j])*f;}
    } else {
        int i=0; if(m[1][1]>m[i][i])i=1; if(m[2][2]>m[i][i])i=2;
        int j=(i+1)%3,k=(i+2)%3;
        float root=sqrtf((float)((m[i][i]-(m[j][j]+m[k][k]))+1.0)),f=.5/root;
        q[i]=root*.5; q[3]=(m[j][k]-m[k][j])*f;
        q[j]=(m[i][j]+m[j][i])*f; q[k]=(m[i][k]+m[k][i])*f;
    }
}
static void translate(float m[4][4],float x,float y,float z) {
    for(int c=0;c<3;c++)m[3][c]+=m[0][c]*x+m[1][c]*y+m[2][c]*z;
}
static void bone(float m[4][4],const float *q,const float *pivot,float factor) {
    translate(m,pivot[0]+factor*q[7],pivot[1]+factor*q[8],pivot[2]+factor*q[9]);
    if(q[0]!=0 || q[1]!=0 || q[2]!=0 || q[3]!=1) {
        float norm=q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3];
        float f=norm?(float)(2.0/norm):2;
        float x=q[0]*f,y=q[1]*f,z=q[2]*f;
        float xx=x*q[0],xy=y*q[0],xz=z*q[0],yy=y*q[1],yz=z*q[1],zz=z*q[2];
        float xw=x*q[3],yw=y*q[3],zw=z*q[3];
        float r[3][3]={{1.f-(yy+zz),xy+zw,xz-yw},{xy-zw,1.f-(xx+zz),yz+xw},{xz+yw,yz-xw,1.f-(xx+yy)}},tmp[3][3]={{0}};
        for(int i=0;i<3;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)tmp[i][j]+=r[i][k]*m[k][j];
        for(int i=0;i<3;i++)for(int j=0;j<3;j++)m[i][j]=tmp[i][j];
    }
    for(int i=0;i<3;i++)for(int j=0;j<3;j++)m[i][j]*=q[4+i];
    translate(m,-pivot[0],-pivot[1],-pivot[2]);
}
bool banjo_pose_evaluate(const uint8_t *p,size_t size,float phase,BanjoPose *o) {
    if(!p || !o || size!=12082 || !isfinite(phase) || phase<0 || phase>1)return false;
    if(memcmp(p,"B3P3",4) || u32(p+4)!=1 || u32(p+8)!=60 || u32(p+12)!=723 || u32(p+16)!=2085 || u32(p+20)!=1132 || u32(p+24) || u32(p+28))return false;
    const uint8_t *sk=p+36,*loads=sk+960,*corners=loads+5784,*anim=corners+4170;
    if(u16(anim)!=0 || u16(anim+2)!=120 || u16(anim+4)!=47 || u16(anim+6))return false;
    memset(o,0,sizeof(*o));
    /* Euler channels temporarily occupy q.xyz; no extra channel array. */
    for(int i=0;i<109;i++)o->bones[i][4]=o->bones[i][5]=o->bones[i][6]=1;
    const uint8_t *k=anim+8,*end=p+size;
    for(int c=0;c<47;c++) {
        if(end-k<4)return false;
        unsigned id=u16(k)>>4,ch=u16(k)&15; int n=s16(k+2); k+=4;
        if(id>=109 || ch>8 || n<=0 || end-k<4*n)return false;
        for(int i=0;i<n;i++)if(frame(k,i)>120 || (i && frame(k,i)<=frame(k,i-1)))return false;
        o->bones[id][ch<3?ch:ch+1]=channel(k,n,ch,phase*120.f); k+=4*n;
    }
    if(k!=end)return false;
    for(int i=0;i<109;i++){float angles[3];memcpy(angles,o->bones[i],12);quaternion(angles,o->bones[i]);}
    float factor=f32(p+32); if(!isfinite(factor))return false;
    for(int i=0;i<60;i++) {
        const uint8_t *r=sk+16*i; int id=s16(r+12),parent=s16(r+14);
        if(id<0 || id>=109 || parent< -1 || parent>=i)return false;
        float pivot[3]={f32(r),f32(r+4),f32(r+8)};
        if(!isfinite(pivot[0]) || !isfinite(pivot[1]) || !isfinite(pivot[2]))return false;
        if(parent<0)identity(o->matrices[i]);else memcpy(o->matrices[i],o->matrices[parent],64);
        bone(o->matrices[i],o->bones[id],pivot,factor);
    }
    for(int i=0;i<2085;i++)if(u16(corners+2*i)>=723)return false;
    for(int i=0;i<723;i++) {
        const uint8_t *r=loads+8*i; unsigned id=u16(r+6); float base[4][4];
        if(id>=60 && id!=65535)return false;
        identity(base); const float (*m)[4]=id==65535?base:o->matrices[id];
        for(int c=0;c<3;c++) {
            double result=0;
            for(int j=0;j<4;j++) {
                float v=m[j][c]; if(j==3 && c==2)v-=100.f;
                float scaled=v*65536.f;
                if(!isfinite(scaled) || scaled>=2147483648.0 || scaled< -2147483648.0)return false;
                result+=((int32_t)scaled/65536.0)*(j==3?1:s16(r+2*j));
            }
            o->xyz[i][c]=(float)(result+(c==2?100.0:0.0));
        }
    }
    return true;
}
