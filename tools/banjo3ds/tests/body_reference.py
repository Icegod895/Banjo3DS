"""E.2 original normal-player collision loop, compiled from decomp.
No production body, ground or query code is used by this oracle. Existing
independent contact/floor harnesses supply original native asset structs.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import contact_reference
import floor_state_reference
from segment_reference import ROOT, FLAGS, function
F=C.c_float

@functools.lru_cache(None)
def library(opt):
    contact=contact_reference.library(opt)
    text=(Path(contact._tmp.name)/'ref.c').read_text()
    text=text.replace('void collisionList_setStoredTriangle(BKCollisionTriangle *t,BKVertexList *v){(void)t;(void)v;}',
        'float sStoredTriangle[3][3];void collisionList_setStoredTriangle(BKCollisionTriangle*,BKVertexList*);')
    text+=function('src/core2/code_5FD90.c','collisionList_setStoredTriangle')
    text+=function('src/core2/code_5FD90.c','collisionList_getStoredTriangle')
    floor=floor_state_reference.library(opt)
    suffix=(Path(floor._tmp.name)/'ref.c').read_text().split('#include <stddef.h>',1)[1]
    for definition in ('static void ml_vec3f_clear(float*p){memset(p,0,12);}',
                       'static float ml_max_f(float a,float b){return a>b?a:b;}'):
        suffix=suffix.replace(definition,'')
    text+='\n#include <stddef.h>\n'+suffix
    text+='\nstatic u16 body_angles[10001],*D_80276CB8=body_angles;\n'
    text+='\n#define MAX(a,b) ((a)>(b)?(a):(b))\n'
    for n in ('func_80256B54','ml_acosf','ml_cos_deg','ml_vec3f_cross_product','ml_distanceSquared_vec3f','func_80259554','func_802596AC',
              'func_80257918','func_8025778C','func_802578A4','ml_isNonzero_vec3f'):
        text+=function('src/core1/ml.c',n)
    for n in ('func_80244CD0','func_80244E54','func_80244FC0','func_802450DC','func_802457C4'):
        text+=function('src/core1/code_72B0.c',n)
    source=(ROOT/'src/core2/code_C4B0.c').read_text()
    text+=source[source.index('typedef struct {'):source.index('/* .code */')].replace('struct0 * D_8037C200;','#define D_8037C200 state')
    text+='\nint baMarker_8028D694(void){return 0x400000;}\n'
    text+=function('src/core2/code_C4B0.c','func_802946FC').replace('s32 arg1','BKCollisionTriangle *arg1')
    text+=r'''
typedef struct {
 float initial[3],after_line[3],after_floor[3],start_center[3],end_center[3],normal[3],final[3];
 int32_t role,record;uint32_t line_hit,grounded,paths;uint8_t floor[120];
} Iteration;
typedef struct {
 float pushed_previous[3],fallback[3],final[3],normal[3];
 uint32_t iterations,hits,exhausted,forced;Iteration iteration[5];
} BodyTrace;
static BodyTrace bt;
static void identity(BKCollisionTriangle*t,int32_t*out){
 out[0]=out[1]=-1;if(!t)return;
 for(int r=0;r<2;r++){
  BKCollisionList*c=r?mapModel.collision_xlu:mapModel.collision_opa;
  BKCollisionTriangle *first=(BKCollisionTriangle*)(c->data+4*c->geo_count);
  uintptr_t p=(uintptr_t)t,lo=(uintptr_t)first;
  if(p>=lo && p<lo+12*c->tri_count){out[0]=r;out[1]=(p-lo)/12;}
 }
}
'''
    text+=function('src/core2/code_C4B0.c','func_8029350C')
    loop=function('src/core2/code_C4B0.c','func_80293668')
    loop=loop.replace('    for(i = 0;', '    memcpy(bt.pushed_previous,D_8037C228,12);memcpy(bt.fallback,sp390,12);\n    for(i = 0;')
    loop=loop.replace('        ml_vec3f_copy(sp364,', '        bt.iterations=i+1;memcpy(bt.iteration[i].initial,sp88->unk0,12);\n        ml_vec3f_copy(sp364,')
    loop=loop.replace('        func_8029350C(sp88->unk0);','        memcpy(bt.iteration[i].after_line,sp88->unk0,12);bt.iteration[i].line_hit=sp88->unk40!=0;\n        func_8029350C(sp88->unk0);\n        memcpy(bt.iteration[i].after_floor,sp88->unk0,12);bt.iteration[i].grounded=D_8037C279;floor_ref_snapshot(bt.iteration[i].floor);')
    loop=loop.replace('        if (sp88->unk18 != NULL) {','        memcpy(bt.iteration[i].start_center,sp88->unk34,12);memcpy(bt.iteration[i].end_center,sp88->unk28,12);\n        identity(sp88->unk18,&bt.iteration[i].role);memcpy(bt.iteration[i].normal,sp88->unk1C,12);\n        if (sp88->unk18 != NULL) {',1)
    # Original miss leaves unk1C unspecified. Exclude uninitialized data from
    # snapshots (not from the algorithm); no normal is read on that branch.
    loop=loop.replace('memcpy(bt.iteration[i].normal,sp88->unk1C,12);','if(sp88->unk18)memcpy(bt.iteration[i].normal,sp88->unk1C,12);')
    loop=loop.replace('            break;','            memcpy(bt.iteration[i].final,sp88->unk0,12);break;')
    loop=loop.replace('    }\n\n    if ((i == 5)', '        memcpy(bt.iteration[i].final,sp88->unk0,12);\n    }\n\n    if ((i == 5)')
    # Original long-line return is used only as a boolean: fix 64-bit host ABI.
    loop=loop.replace('sp88->unk40 = func_80244E54(', 'sp88->unk40 = NULL != func_80244E54(')
    loop=loop.replace('            sp38C = sp88->unk0[1];','            bt.iteration[i].paths|=64;sp38C = sp88->unk0[1];')
    loop=loop.replace('                    sp88->unk40 = 0;','                    bt.iteration[i].paths|=32;sp88->unk40 = 0;')
    loop=loop.replace('                    ml_vec3f_add(sp380, sp88->unk1C, var_s1->unk1C);','                    bt.iteration[i].paths|=1;ml_vec3f_add(sp380, sp88->unk1C, var_s1->unk1C);')
    loop=loop.replace('                        func_802578A4(sp380, sp88->unk0, sp88->unk68[0]);','                        bt.iteration[i].paths|=2;func_802578A4(sp380, sp88->unk0, sp88->unk68[0]);')
    loop=loop.replace('                    func_802578A4(sp380, sp88->unk0, sp88->unk68[0]);','                    bt.iteration[i].paths|=4;func_802578A4(sp380, sp88->unk0, sp88->unk68[0]);')
    loop=loop.replace('                func_8025778C(sp3AC,','                bt.iteration[i].paths|=8;func_8025778C(sp3AC,')
    loop=loop.replace('                func_802450DC(sp88->unkC,','                bt.iteration[i].paths|=16;func_802450DC(sp88->unkC,')
    text+=loop
    text+=r'''
void body_ref_init(unsigned grounded,unsigned stuck){for(int i=0;i<10001;i++)body_angles[i]=sinf(i*90.0/10000*3.14159265358979323846/180)*65535.f;D_8037C279=grounded;D_8037C280=stuck;}
void body_ref_vertex(unsigned role,unsigned v,const int16_t*xyz){
 BKVertexList *list=role?mapModel.model_bin_xlu:mapModel.model_bin_opa;memcpy(list->vertices[v].v.ob,xyz,6);
}
int body_ref_step(const float*previous,float*candidate,float*vy,unsigned frame_parity,unsigned*grounded,unsigned*stuck,BodyTrace*out){
 memset(&bt,0,sizeof(bt));parity=frame_parity;ncalls=0;overflow=0;
 D_8037C279=*grounded;D_8037C280=*stuck;D_8037C1F8[0]=80;D_8037C1F8[1]=35;
 D_8037C27C=0;D_8037C27D=0;D_8037C204=NULL;
 memcpy(D_8037C218,candidate,12);memcpy(D_8037C228,previous,12);
 ml_vec3f_diff_copy(D_8037C238,D_8037C218,D_8037C228);
 func_8031C608(state);func_80293668();
 if(D_8037C280==3){D_8037C279=1;bt.forced=1;}
 if(D_8037C279 && *vy<0)*vy=-1;
 D_8037C280=D_8037C27C?(D_8037C280<3?D_8037C280+1:3):0;
 memcpy(candidate,D_8037C218,12);*grounded=D_8037C279;*stuck=D_8037C280;
 memcpy(bt.final,D_8037C218,12);memcpy(bt.normal,D_8037C258,12);
 bt.hits=D_8037C27D;bt.exhausted=bt.iterations==5 && bt.hits==5;
 *out=bt;return overflow?-1:1;
}
'''
    # Keep prior contact normal as persistent state, matching original global.
    text=text.replace('D_8037C280=stuck;}','D_8037C280=stuck;memset(D_8037C258,0,12);}')
    tmp=tempfile.TemporaryDirectory(prefix='body-original-');p=Path(tmp.name);(p/'ref.c').write_text(text)
    # Contact oracle contains original camera helpers that reference libultra trig.
    import horizontal_reference
    trig=horizontal_reference.library(opt);td=Path(trig.temporary.name)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),str(td/'sinf.c'),str(td/'cosf.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    lib.ref_load.argtypes=[C.c_int,C.c_void_p];lib.body_ref_vertex.argtypes=[C.c_uint,C.c_uint,C.c_void_p]
    lib.floor_ref_step.argtypes=[C.POINTER(F),F,C.c_uint32,C.c_uint]
    lib.floor_ref_snapshot.argtypes=[C.c_void_p]
    lib.body_ref_step.argtypes=[C.POINTER(F),C.POINTER(F),C.POINTER(F),C.c_uint,C.c_void_p,C.c_void_p,C.c_void_p]
    return lib
