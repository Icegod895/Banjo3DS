"""Independent M4.8B oracle: original C camera/math/zone functions.

No production-camera imports. Explicit unobstructed, non-water, no-manual-input
adapter. Original node32 data is read independently at its pinned asset offset;
cube records are walked independently for trigger data. Full map arbitration
outside node32 is NOT claimed. See camera/README.md for the bounded contract.
"""
import ctypes as C
import functools
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from horizontal_reference import ROOT, FLAGS, F, f, library as horizontal_library, trace, FIELDS as H_FIELDS

ASSET = ROOT/'assets/lvl_setup/071D.lvl_setup.bin'
FIELDS = ('camera_x camera_y camera_z pitch yaw roll focus_x focus_y focus_z '
          'lead_x lead_y lead_z position_step_x position_step_y position_step_z '
          'angular_step_x angular_step_y angular_step_z stable_x stable_y stable_z orbit_yaw').split()
CASES = ('node_stationary','node_movement','node_jump','node_landing','node_to_free',
         'free_stationary','free_straight','free_90','free_180','free_jump_rest',
         'free_jump_full','free_landing','free_to_node')
SOURCES = ['src/core1/ml.c','include/math.h','src/core1/code_7F60.c',
           'src/core2/nc/dynamicCamera.c','src/core2/nc/dynamicCamB.c',
           'src/core2/nc/dynamicCam11.c','src/core2/code_34790.c',
           'src/core2/code_9290.c','src/core2/code_9BD0.c','src/core2/gccube.c',
           'src/core2/code_F8EAF0.c','src/core2/time.c',
           'lib/ultralib/src/gu/sinf.c','lib/ultralib/src/gu/cosf.c']

def original(path, name):
    text=(ROOT/path).read_text()
    m=re.search(r'(?m)^(?:static\s+)?(?:void|f32|s32|bool|int)\s+'+name+r'\([^;]*?\)\s*\{',text)
    if not m:raise ValueError(name)
    end=m.end();depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]+'\n'

def setup():
    """Independent cube walker; node32's tagged payload pinned separately."""
    b=ASSET.read_bytes();lo=struct.unpack_from('>3i',b,2);hi=struct.unpack_from('>3i',b,14)
    p=26;records=[]
    for _ in range(math.prod(hi[i]-lo[i]+1 for i in range(3))):
        while b[p]!=1:
            t=b[p];p+=1
            if t==0:p+=24
            elif t==2:p+=12
            elif t==3:
                if b[p] in (10,6):
                    kind,n=b[p:p+2];p+=2
                    if b[p]==(11 if kind==10 else 7):
                        p+=1
                        for _ in range(n):
                            raw=b[p:p+20];flags=int.from_bytes(raw[6:8],'big')
                            if (flags>>1)&63==9:
                                records.append((p,*struct.unpack_from('>3h',raw),flags>>7,
                                                int.from_bytes(raw[8:10],'big'),(7,1,2,4)[raw[-1]&3]))
                            p+=20
                if b[p]==8:
                    n=b[p+1];p+=2
                    if b[p]==9:p+=1+12*n
            else:raise ValueError((p,t))
        p+=1
    assert b[p:p+2]==b'\0\3' and p+1==0x1df0
    raw=b[0x2491:0x24d1];assert raw[:5]==b'\1\0\x20\2\3'
    cursor=5;fields={}
    while raw[cursor]:
        tag=raw[cursor];cursor+=1
        fmt={1:'3f',2:'2f',3:'2f',4:'3f',5:'I',6:'2f'}[tag]
        fields[tag]=struct.unpack_from('>'+fmt,raw,cursor);cursor+=struct.calcsize('>'+fmt)
    return records, (*fields[1],*fields[4],*fields[2],*fields[3],*fields[6],*fields[5])

@functools.lru_cache(maxsize=2)
def library(opt='-O0'):
    tmp=tempfile.TemporaryDirectory(prefix='banjo-camera-oracle-');directory=Path(tmp.name)
    base=horizontal_library(opt);base_dir=Path(base.temporary.name)
    # Existing independent oracle supplies original libultra trig + ml primitives.
    code=(base_dir/'reference.c').read_text()+r'''
typedef uint16_t u16;typedef uint32_t u32;typedef uint8_t u8;
#define TRUE 1
#define FALSE 0
#define M_PI 3.14159265358979323846
#define LENGTH_VEC3F(v) sqrtf(LENGTH_SQ_VEC3F(v))
#define _SQ2(x,y) ((x)*(x)+(y)*(y))
#define _SQ3(x,y,z) ((x)*(x)+(y)*(y)+(z)*(z))
#define BSWATERGROUP_2_UNDERWATER 2
#define TRANSFORM_1_BANJO 1
#define TRANSFORM_3_PUMPKIN 3
#define BSGROUP_5_CLIMB 5
#define BSGROUP_A_FLYING 10
#define BS_B_UNKOWN 11
float player[3],cameraPosition[3],cameraRotation[3],floor_height;
int stable,vi_frames,focus_mode=2;
float profile_r=850,profile_h=375;
u16 lookup[10001],*D_80276CB8=lookup;
float D_8037D974=130,D_8037D978,D_8037D97C=110,D_8037D980=180,D_8037D9A0;
float D_8037D9A8[3],D_8037D9B8[3],D_8037D9C8[3],D_8037D9E0[3];
float D_8037D9D4,D_8037D9D8,D_8037D9EC,D_8037D9F0,D_8037DB70;
struct {float D_8037DB78[3],D_8037DB84[3],D_8037DB90[3];}cameraStateB;
float D_8037DAC0[3],D_8037DAD0[3],D_8037DADC,D_8037DAE0;
u8 D_8037DAE4=0,D_8037DAE5=0;
int D_8037C010=-1,D_8037C014=-1,D_8037C018=-1,D_8037C01C;
float D_8037C020[3];u8 D_8037C02C,D_8037C062=2,D_8037C060=0;
int dynamic_state=11,preset=2;
float zoom_gains[4];
int time_getDeltaReal_frames(void){return vi_frames;}
int func_802BC428(void){return 0;}
int func_8028F2FC(void){return 0;}
int func_8028B528(void){return 0;}
int player_isStable(void){return stable;}
int player_movementGroup(void){return 0;}
int bs_getState(void){return 1;}
int player_getWaterState(void){return 0;}
int player_getTransformation(void){return 1;}
float func_8028EF88(void){return 0;}
float func_8028E82C(void){return floor_height;}
float func_802BD8D4(void){return profile_r;}
float func_802BD8C8(void){return profile_h;}
float player_getYaw(void){return yaw_deg;}
void player_getPosition(float *p){memcpy(p,player,12);}
void playerPosition_get(float *p){memcpy(p,player,12);}
void ncDynamicCamera_getPosition(float *p){memcpy(p,cameraPosition,12);}
void ncDynamicCamera_setPosition(float *p){memcpy(cameraPosition,p,12);}
void ncDynamicCamera_getRotation(float *p){memcpy(p,cameraRotation,12);}
void ncDynamicCamera_setRotation(float *p){memcpy(cameraRotation,p,12);}
int func_802BE60C(void){return 0;}
int func_802BC84C(int x){return 0;}
void func_802C0150(int x){focus_mode=x;}
void func_802C02D4(float*);
void func_802BE6FC(float*,float*);
typedef struct {int position[3],radius;unsigned unk10_31:28,unk10_3:3,unk10_0:1;} Struct_core2_7AF80_2;
typedef struct {int count,unk4;Struct_core2_7AF80_2 *unk8;} Struct_core2_7AF80_1;
Struct_core2_7AF80_2 cells[256];Struct_core2_7AF80_1 groups[256],*D_8036A9C8=groups;
int D_8036A9C4;unsigned char D_80381FE8[80];
'''
    macros=(ROOT/'include/math.h').read_text()
    for name in ('TUPLE_ADD_COPY','TUPLE_DIFF_COPY','TUPLE_CLEAR'):
        if '#define '+name+'(' in macros:
            for line in macros[macros.index('#define '+name+'('):].splitlines():
                code+=line+'\n'
                if not line.endswith('\\'):break
    for name in ('mlNormalizeAngle','ml_vec3f_clear','ml_vec3f_diff_copy','ml_vec3f_add',
                 'ml_vec3f_normalize','ml_vec3f_set_length_copy','func_80256E24',
                 'ml_acosf','ml_horizontal_and_vertical_angles','func_8025801C',
                 'ml_vec3f_to_vec3w','ml_vec3w_within_horizontal_distance'):
        code+=original('src/core1/ml.c',name)
    for name in ('func_80306EF4','func_80307504','func_803077FC','func_80306D40'):
        fragment=original('src/core2/gccube.c',name)
        # Decomp passes pointers-to-array / prefix-compatible struct pointers.
        # Spell their identical addresses with host-C-correct pointer types.
        fragment=fragment.replace('ml_vec3w_within_horizontal_distance(&sp4C,',
                                  'ml_vec3w_within_horizontal_distance(sp4C,')
        fragment=fragment.replace('sp4C, var_s0, var_s0->radius',
                                  'sp4C, var_s0->position, var_s0->radius')
        code+=fragment
    code+=original('src/core2/code_9290.c','func_80290298')
    code+=original('src/core2/code_34790.c','func_802BC434')
    for name in ('func_802BCA58','func_802BD3CC','func_802BD4C0','func_802BD51C',
                 'func_802BDE10','func_802BDF5C','func_802BE190','func_802BE230','func_802BE244',
                 'func_802BD904','func_802BE6FC'):
        code+=original('src/core2/nc/dynamicCamera.c',name)
    code+='void func_802C02D4(float *p){if(focus_mode==1)func_802BD3CC(p);else func_802BD4C0(p);}\n'
    for name in ('func_802C0370','func_802C0394','func_802C03BC','func_802C0490','func_802C04B0','ncDynamicCamB_init','ncDynamicCamB_update'):
        code+=original('src/core2/nc/dynamicCamB.c',name)
    for name in ('ncDynamicCam11_init','ncDynamicCam11_update'):
        code+=original('src/core2/nc/dynamicCam11.c',name)
    code+=r'''
void ncDynamicCamera_setState(int n){if(n==dynamic_state)return;
 if(n==11)ncDynamicCamB_init();else if(n==17)ncDynamicCam11_init();dynamic_state=n;}
void func_80291488(int n){D_8037C062=n;}
void func_8029028C(int n){D_8037C02C=n;}
void batimer_decrement(int n){}
void func_80290F14(void){}
int func_80290E8C(void){return 0;}
int func_8029105C(int n){return 0;}
#define BUTTON_R 1
int bakey_held(int n){return 0;}
/* No unsupported/manual state is entered by this reference driver. */
void func_80291108(void){} void func_80291268(void){} void func_802912D0(void){}
void func_802911E0(void){} void func_80291328(void){}
int func_80290D48(void){
 if(D_8037C018==32){ncDynamicCamera_setState(17);
   func_802BE230(zoom_gains[0],zoom_gains[1]);func_802BE244(zoom_gains[2],zoom_gains[3]);
   D_8037DAE5=0;func_80291488(9);return 1;}
 return 0;
}
'''
    code+=original('src/core2/code_9BD0.c','func_80291154')
    code+=original('src/core2/code_9BD0.c','cameraMode_update')
    code+=r'''
void ref_setup(const int *records,int count,const float *z){
 D_8036A9C4=count;memset(D_80381FE8,1,sizeof(D_80381FE8));
 for(int i=0;i<count;i++){memcpy(cells[i].position,records+6*i,12);cells[i].radius=records[6*i+3];
  cells[i].unk10_3=records[6*i+5];groups[i].count=1;groups[i].unk4=records[6*i+4];groups[i].unk8=cells+i;}
 memcpy(D_8037DAC0,z,12);for(int i=0;i<3;i++)D_8037DAD0[i]=z[i]+z[i+3];
 memcpy(zoom_gains,z+6,16);D_8037DAE0=z[10];D_8037DADC=z[11];
}
void ref_init(const float *p,float floor,const float *eye,const float *rotation){
 for(int i=0;i<10001;i++)lookup[i]=sinf(i*90.0/10000*M_PI/180)*65535.f;
 memcpy(player,p,12);floor_height=floor;memcpy(cameraPosition,eye,12);memcpy(cameraRotation,rotation,12);
 memset(D_8037D9B8,0,12);memset(D_8037D9C8,0,12);memset(D_8037D9E0,0,12);
 memcpy(D_8037C020,p,12);D_8037C010=D_8037C014=D_8037C018=-1;D_8037C02C=0;D_8037C062=2;
 dynamic_state=11;preset=2;ncDynamicCamB_init();
}
void ref_step(const float *p,float floor,float yaw,float under,float dt,int vi,int on_ground,int distance){
 static const float radii[]={550,850,1100},heights[]={175,375,675};
 memcpy(player,p,12);floor_height=floor;yaw_deg=yaw;D_8037D9A0=under;current_dt=dt;vi_frames=vi;stable=on_ground;
 preset=distance;profile_r=radii[preset-1];profile_h=heights[preset-1];
 cameraMode_update();func_802BCA58();
 if(dynamic_state==11)ncDynamicCamB_update();else ncDynamicCam11_update();
}
void ref_snapshot(float *o,int *ids){
 memcpy(o,cameraPosition,12);memcpy(o+3,cameraRotation,12);func_802C02D4(o+6);
 memcpy(o+9,D_8037D9B8,12);memcpy(o+12,D_8037D9E0,12);memcpy(o+15,D_8037D9C8,12);
 memcpy(o+18,D_8037C020,12);o[21]=D_8037DB70;
 ids[0]=D_8037C062;ids[1]=dynamic_state;ids[2]=D_8037C018;ids[3]=preset;
}
void ref_seed(const float *steps,const float *angular){memcpy(D_8037D9E0,steps,12);memcpy(D_8037D9C8,angular,12);}
void guMtxIdentF(float m[4][4]){memset(m,0,64);for(int i=0;i<4;i++)m[i][i]=1;}
'''
    code+=original('src/core1/code_7F60.c','core1_7F60_guPerspectiveF')
    code+=r'''
int ref_project(const float *eye,const float *rotation,const float *point,float aspect,float near,float far,float *o){
 float d[3],r[3],v[3],m[4][4];
 for(int i=0;i<3;i++)d[i]=point[i]-eye[i];
 /* Original viewport applies inverse yaw followed by inverse pitch. */
 func_80256E24(r,0,-rotation[1],d[0],d[1],d[2]);
 func_80256E24(v,-rotation[0],0,r[0],r[1],r[2]);
 if(v[2]>=0)return 0;
 core1_7F60_guPerspectiveF(m,0,40,aspect,near,far,.5f);
 for(int i=0;i<3;i++)o[i]=(v[i]*m[i][i]+m[3][i])/(-.5f*v[2]);
 return 1;
}
'''
    (directory/'reference.c').write_text(code)
    out=directory/'reference.so'
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(directory/'reference.c'),
                    str(base_dir/'sinf.c'),str(base_dir/'cosf.c'),'-lm','-o',str(out)],check=True)
    lib=C.CDLL(str(out));lib.temporary=tmp
    fp=C.POINTER(F);ip=C.POINTER(C.c_int)
    for name,args,result in (
        ('setup',[ip,C.c_int,fp],None),('init',[fp,F,fp,fp],None),
        ('step',[fp,F,F,F,F,C.c_int,C.c_int,C.c_int],None),('snapshot',[fp,ip],None),
        ('seed',[fp,fp],None),('project',[fp,fp,fp,F,F,F,fp],C.c_int)):
        fn=getattr(lib,'ref_'+name);fn.argtypes=args;fn.restype=result
    return lib

def initial(case):
    p=[0.,1800.,0.] if case.startswith('node_') else [0.,1800.,600.]
    return p,[p[0],2175.,p[2]-850.],[340.,180.,0.]

def commands(case):
    """Explicit camera inputs, not a claim to emulate entire player/collision.
    State-changing paths are real node32 region exits/entries. Jump probe is
    frozen until landing; floor is a diagnostic flat Y=1800 throughout.
    """
    start,_,_=initial(case);p=start[:];vy=f(710);dt=f(1/60)
    is_jump='jump' in case or 'landing' in case
    ground=not is_jump
    original_path={'free_90':'ground_90','free_180':'ground_180_skid'}.get(case)
    frames=list(trace(original_path)) if original_path else None
    for i in range(120):
        visible=0.
        if frames:
            row=dict(zip(H_FIELDS,frames[min(i,len(frames)-1)][1]))
            p[0]=f(start[0]+row['position_x']);p[2]=f(start[2]+row['position_z']);visible=row['visible_yaw']
        elif case=='node_to_free':p[2]=f((i+1)*500/60)
        elif case=='free_to_node':p[2]=f(600-(i+1)*300/60)
        elif case in ('node_movement','free_straight'):p[0]=f(start[0]+(i+1)*(100 if case=='node_movement' else 500)/60)
        elif is_jump:
            if case not in ('free_jump_rest','node_landing','free_landing'):p[2]=f(p[2]+f(500*dt))
        if is_jump and not ground:
            vy=f(vy+f(-1350*dt));p[1]=f(p[1]+f(vy*dt))
            if p[1]<=1800 and vy<0:p[1]=1800.;ground=True
        yield dict(player=p[:],floor=1800.,yaw=visible,under=1800.,dt=dt,vi=1,stable=ground,preset=2)

def snapshot(lib):
    out=(F*22)();ids=(C.c_int*4)();lib.ref_snapshot(out,ids)
    return list(out),list(ids)

def pack(values,ids):return struct.pack('>22f4i',*values,*ids)

def projection_points(player):
    # Player feet, +80 focus/body point, plus one fixed world landmark.
    return (player, [player[0],player[1]+80,player[2]], [0.,1800.,0.])

def projections(lib,values,player):
    out=[]
    for aspect in (f(1.35185182),f(400/240)):
        for point in projection_points(player):
            ndc=(F*3)()
            valid=lib.ref_project((F*3)(*values[:3]),(F*3)(*values[3:6]),(F*3)(*point),aspect,10,20000,ndc)
            out.append([valid,*ndc])
    return out

def pack_projection(rows):
    return b''.join(struct.pack('>i3f',*r) for r in rows)

def golden(opt='-O0'):
    lib=library(opt);records,z=setup();raw=[v for r in records for v in r[1:]]
    lib.ref_setup((C.c_int*len(raw))(*raw),len(records),(F*12)(*z[:12]))
    cases={}
    for case in CASES:
        p,eye,rot=initial(case);lib.ref_init((F*3)(*p),1800,(F*3)(*eye),(F*3)(*rot))
        stream=[];projected=[];checkpoints={}
        for i,cmd in enumerate(commands(case),1):
            lib.ref_step((F*3)(*cmd['player']),cmd['floor'],cmd['yaw'],cmd['under'],cmd['dt'],cmd['vi'],cmd['stable'],cmd['preset'])
            values,ids=snapshot(lib);stream.append(pack(values,ids))
            points=projections(lib,values,cmd['player']);projected.append(pack_projection(points))
            if i in (1,6,15,30,60,63,120):checkpoints[str(i)]=dict(state=values,ids=ids,projected=points)
        cases[case]=dict(frames=len(stream),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),
                         projection_sha256=hashlib.sha256(b''.join(projected)).hexdigest(),checkpoints=checkpoints)
    return dict(asset_sha256=hashlib.sha256(ASSET.read_bytes()).hexdigest(),
                source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in SOURCES},
                packing='>22f4i per frame; no padding',fields=FIELDS,ids=['mode','state','node','preset'],
                projection_packing='6 x >i3f per frame: valid,NDC XYZ; BK then 400/240 aspect; feet,body,landmark; clips 10/20000',cases=cases)

if __name__=='__main__':
    import sys
    Path(sys.argv[1]).write_text(json.dumps(golden(),indent=2)+'\n')
