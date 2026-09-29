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
/* B3P3 v1 is the unchanged M4.3 walk fixture; v2 appends 006F and
 * uses header word 6 for its byte length. Binding offsets are identical. */
static bool packet_valid(const uint8_t *p,size_t size) {
    if(!p || size<32 || memcmp(p,"B3P3",4) || u32(p+8)!=60 ||
       u32(p+12)!=723 || u32(p+16)!=2085 || u32(p+20)!=1132 || u32(p+28))return false;
    return (u32(p+4)==1 && u32(p+24)==0 && size==12082) ||
           (u32(p+4)==2 && u32(p+24)==12316 && size==24398);
}
bool banjo_pose_sample(const uint8_t *p,size_t size,BanjoClip clip,float phase,float out[109][10]) {
    if(!out || !packet_valid(p,size) || !isfinite(phase) || phase<0 || phase>1 ||
       (clip!=BANJO_CLIP_WALK && clip!=BANJO_CLIP_IDLE) ||
       (clip==BANJO_CLIP_IDLE && u32(p+4)!=2))return false;
    const uint8_t *anim=p+10950+(clip==BANJO_CLIP_IDLE?1132:0);
    unsigned last=clip==BANJO_CLIP_IDLE?110:120, channels=clip==BANJO_CLIP_IDLE?81:47;
    const uint8_t *end=anim+(clip==BANJO_CLIP_IDLE?12316:1132);
    if(u16(anim)!=0 || u16(anim+2)!=last || u16(anim+4)!=channels || u16(anim+6))return false;
    memset(out,0,109*10*sizeof(float));
    /* Euler channels temporarily occupy q.xyz; no extra channel array. */
    for(int i=0;i<109;i++)out[i][4]=out[i][5]=out[i][6]=1;
    const uint8_t *k=anim+8;
    for(unsigned c=0;c<channels;c++) {
        if(end-k<4)return false;
        unsigned id=u16(k)>>4,ch=u16(k)&15; int n=s16(k+2); k+=4;
        if(id>=109 || ch>8 || n<=0 || end-k<4*n)return false;
        for(int i=0;i<n;i++)if(frame(k,i)>(int)last || (i && frame(k,i)<=frame(k,i-1)))return false;
        out[id][ch<3?ch:ch+1]=channel(k,n,ch,phase*(float)last); k+=4*n;
    }
    if(k!=end)return false;
    for(int i=0;i<109;i++){float angles[3];memcpy(angles,out[i],12);quaternion(angles,out[i]);}
    return true;
}
bool banjo_pose_apply(const uint8_t *p,size_t size,BanjoPose *o) {
    if(!o || !packet_valid(p,size))return false;
    const uint8_t *sk=p+36,*loads=sk+960,*corners=loads+5784;
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

bool banjo_pose_evaluate(const uint8_t *p,size_t size,float phase,BanjoPose *o) {
    return o && banjo_pose_sample(p,size,BANJO_CLIP_WALK,phase,o->bones) && banjo_pose_apply(p,size,o);
}

/* ml.c:13,37. Original NTSC 1.0 ROM bytes after the 90 declared floats
 * are two zero words (0xf52654..0xf5265b), proven by M4.4B. In particular
 * dot==0 returns zero degrees; replacing this with acosf changes the pose. */
static const float acos_degrees[92] = {
    1.0000000000, 0.9998480080, 0.9993910190, 0.9986299870, 0.9975640180,
    0.9961950180, 0.9945219760, 0.9925460220, 0.9902679920, 0.9876880050,
    0.9848080280, 0.9816269870, 0.9781479840, 0.9743700030, 0.9702960250,
    0.9659259920, 0.9612619880, 0.9563050270, 0.9510570170, 0.9455189700,
    0.9396929740, 0.9335799810, 0.9271839860, 0.9205049870, 0.9135450120,
    0.9063079950, 0.8987939950, 0.8910070060, 0.8829479810, 0.8746200200,
    0.8660249710, 0.8571670060, 0.8480479720, 0.8386710290, 0.8290380240,
    0.8191519980, 0.8090170030, 0.7986360190, 0.7880110140, 0.7771459820,
    0.7660440210, 0.7547100190, 0.7431449890, 0.7313539980, 0.7193400260,
    0.7071070080, 0.6946579810, 0.6819980140, 0.6691309810, 0.6560590270,
    0.6427879930, 0.6293200250, 0.6156619790, 0.6018149850, 0.5877850060,
    0.5735759740, 0.5591930150, 0.5446389910, 0.5299190280, 0.5150380130,
    0.5000000000, 0.4848099950, 0.4694719910, 0.4539909960, 0.4383710030,
    0.4226180020, 0.4067370000, 0.3907310070, 0.3746069970, 0.3583680090,
    0.3420200050, 0.3255679910, 0.3090170030, 0.2923719880, 0.2756370010,
    0.2588190140, 0.2419220060, 0.2249509990, 0.2079119980, 0.1908089970,
    0.1736480000, 0.1564340000, 0.1391730010, 0.1218689980, 0.1045280020,
    0.0871559978, 0.0697569996, 0.0523359999, 0.0348990001, 0.0174519997, 0.0f, 0.0f
};
static float rare_acos(float x) {
    int sign=x<0?-1:1,upper=0,lower=91;
    if(sign<0)x=-x;
    while(upper+1!=lower) {
        int index=(upper+lower)/2;
        if(x>acos_degrees[index])lower=index;else upper=index;
    }
    if(upper==90)return 0;
    float r=(x-acos_degrees[upper])/(acos_degrees[lower]-acos_degrees[upper])+upper;
    return sign>0?r:180-r;
}
/* code_BE2C0.c:88,133. Preserve float/double expression boundaries. */
static void blend_quaternion(float *out,const float *a,const float *b,float t) {
    float minus[4],plus[4],end[4];
    for(int i=0;i<4;i++){minus[i]=a[i]-b[i];plus[i]=a[i]+b[i];}
    float dm=minus[0]*minus[0]+minus[1]*minus[1]+minus[2]*minus[2]+minus[3]*minus[3];
    float dp=plus[0]*plus[0]+plus[1]*plus[1]+plus[2]*plus[2]+plus[3]*plus[3];
    for(int i=0;i<4;i++)end[i]=dm<=dp?b[i]:-b[i];
    float dot=a[0]*end[0]+a[1]*end[1]+a[2]*end[2]+a[3]*end[3],w0,w1;
    if(0.00001<(1.0+dot)) {
        if(0.00001<(1.0-dot)) {
            float angle=(3.141592654/180.0)*rare_acos(dot),sine=trig(angle,false);
            if(sine!=0) {
                w0=trig((1.0-t)*angle,false)/sine;
                w1=trig(t*angle,false)/sine;
            } else {w1=t;w0=1.0-t;}
        } else {w1=t;w0=1.0-t;}
        for(int i=0;i<4;i++)out[i]=w0*a[i]+w1*end[i];
    } else {
        float perpendicular[4]={-a[1],a[0],-a[3],a[2]};
        w0=trig((1.0-t)*(3.141592654/2.0f),false);
        w1=trig(t*(3.141592654/2.0f),false);
        for(int i=0;i<3;i++)out[i]=w0*a[i]+w1*perpendicular[i];
        out[3]=perpendicular[3];
    }
}
void banjo_pose_blend(float out[109][10],const float source[109][10],
                      const float destination[109][10],float factor) {
    /* Endpoints are exact copies, including signed zero. Destination may
     * alias out. No extra normalization (code_B3580.c:64). */
    if(factor<=0){memmove(out,source,109*10*sizeof(float));return;}
    if(factor>=1){memmove(out,destination,109*10*sizeof(float));return;}
    for(int i=0;i<109;i++) {
        float a[10],b[10];memcpy(a,source[i],sizeof(a));memcpy(b,destination[i],sizeof(b));
        if(a[0]==b[0] && a[1]==b[1] && a[2]==b[2] && a[3]==b[3])memcpy(out[i],a,16);
        else blend_quaternion(out[i],a,b,factor);
        for(int j=4;j<10;j++)out[i][j]=a[j]+(b[j]-a[j])*factor;
    }
}
