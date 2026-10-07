"""Independent static-contact oracle: compile ORIGINAL decomp routines.

No production contact imports. Raw assets populate native original structs.
Edits to extracted C are limited to host pointer width, bounded-buffer guards,
and observers. The original float expressions and control flow are retained.
Dynamic providers are deliberately absent, not approximated.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import segment_reference as segment
import horizontal_reference

ROOT=segment.ROOT
FLAGS=segment.FLAGS
F=C.c_float
FP=C.POINTER(F)

@functools.lru_cache(None)
def library(opt):
    base=segment.library(opt)
    trig=horizontal_reference.library(opt)
    tmp=tempfile.TemporaryDirectory(prefix='contact-reference-');p=Path(tmp.name)
    text=(Path(base._tmp.name)/'ref.c').read_text()
    # Larger *reference-only* storage permits detecting the source's undefined
    # >100 overflow before execution escapes; such inputs are not goldens.
    text=text.replace('list[100]', 'list[10000]')
    text+=r'''
#define TRUE 1
#define FALSE 0
#define BAD_DTOR (3.141592654/180.0)
#define LENGTH_VEC3F(v) sqrtf(LENGTH_SQ_VEC3F(v))
#define _SQ2(x,y) ((x)*(x)+(y)*(y))
#define _SQ3(x,y,z) ((x)*(x)+(y)*(y)+(z)*(z))
#define vtxList_getVertices(v) ((v)->vertices)
#define vtxList_getGlobalNorm(v) ((v)->global_norm)
float ref_sinf(float);float ref_cosf(float);
#define sinf ref_sinf
#define cosf ref_cosf
typedef struct {float edgeAB[3],edgeAC[3],normal[3];BKCollisionTriangle *tri_ptr;float tri_coord[3][3];int observer_cell;} BKProcessedCollisionTriangle;
BKProcessedCollisionTriangle sActiveCollTris[102];
int overflow;
typedef struct {uint32_t sphere_calls,line_calls,moving_calls,gated_calls,obstruction_calls,recovery_attempts,changed,recovered;float pushed_previous[3],extended_end[3],subtracted_end[3];} Trace;
Trace trace;
typedef struct {uint32_t counter;float position_step[3],angular_step[3];} State;
'''
    for n in ('ml_vec3f_normalize','ml_vec3f_diff','ml_vec3f_diff_copy','ml_vec3f_scale',
              'ml_vec3f_set_length_copy','ml_vec3f_add','ml_vec3f_clear','ml_vec3f_dot_product',
              'ml_vec3f_distance','ml_vec3f_length','ml_vec3f_yaw_rotate_copy','ml_max_f'):
        text+=segment.function('src/core1/ml.c',n)
    text+=segment.function('src/core2/code_B6640.c','core2_B6640_calculateLineBoundingBox')
    f=segment.function('src/core2/code_5FD90.c','collisionList_getIntersecting_f32')
    text+=f.replace('*end_ptr = sActiveCollisionLists.current;', '*end_ptr = sActiveCollisionLists.current; if(sActiveCollisionLists.current-sActiveCollisionLists.list>100)overflow=1;')
    for n in ('collisionList_intersectMovingSphere_FastCheck','collisionList_intersectMovingSphere_Iteration',
              'collisionList_intersectMovingSphere','collisionList_intersectSphere'):
        f=segment.function('src/core2/code_5FD90.c',n)
        f=f.replace('return NULL;', 'return 0;') if n.endswith('FastCheck') else f
        f=f.replace('(cur_processed_tri++)->tri_ptr = i_tri;',
            'cur_processed_tri->observer_cell=(int)(*i_geo-(BKCollisionGeometry*)this->data); (cur_processed_tri++)->tri_ptr = i_tri;')
        f=f.replace('if (cur_processed_tri - sActiveCollTris > 100) {',
            'if (cur_processed_tri - sActiveCollTris > 100) { overflow=1;')
        f=f.replace('matched_tri = i_tri;', 'matched_tri = i_tri; ref_cell=(int)(*i_geo-(BKCollisionGeometry*)this->data);')
        f=f.replace('return coll_tri->tri_ptr;', 'ref_cell=coll_tri->observer_cell; return coll_tri->tri_ptr;')
        text+=f
    for n in ('func_80309DBC','func_80309EB0'):
        source=(ROOT/'src/core2/mapModel.c').read_text()
        begin=source.index('UNK_TYPE(s32) '+n)
        end=source.index('\n}',begin)+2
        f=source[begin:end]+'\n'
        f=f.replace('UNK_TYPE(s32)', 'BKCollisionTriangle *')
        for v in ('sp34','sp24','temp_v0_2'):
            f=f.replace('s32 '+v+';', 'BKCollisionTriangle *'+v+';')
        text+=f.replace('(s32) mapModel.', '(intptr_t) mapModel.')
    text=text.replace('last_hit=func_80309B48', 'trace.line_calls++;last_hit=func_80309B48')
    # Trace declaration must precede the existing line adapter.
    begin=text.index('typedef struct {uint32_t sphere_calls')
    end=text.index('typedef struct {uint32_t counter',begin)
    decl=text[begin:end];text=text[:begin]+text[end:]
    text=text.replace('BKCollisionTriangle *last_hit;',decl+'\nBKCollisionTriangle *last_hit;')
    text+=r'''
BKCollisionTriangle *func_80320DB0(float *p,float r,float *n,uint32_t f){trace.sphere_calls++;return func_80309EB0(p,r,n,f);}
BKCollisionTriangle *func_80320C94(float *p,float *e,float r,float *n,int steps,uint32_t f){trace.moving_calls++;return func_80309DBC(p,e,r,n,steps,f);}
'''
    for n in ('func_80244D94','func_8024575C'):
        f=segment.function('src/core1/code_72B0.c',n)
        if n=='func_8024575C':f=f.replace('if(arg2 <', 'trace.gated_calls++; if(arg2 <')
        text+=f
    # Exact original tables, including unused modes solely for compilation.
    source=(ROOT/'src/core2/nc/dynamicCamera.c').read_text()
    text+='typedef struct {float *unk0;int unk4;} Struct_core2_356B0_0;\n'
    text+=source[source.index('f32 D_80365CD0[]'):source.index('enum ncdynamiccamera_state_e')]
    text+=r'''
#define TRANSFORM_3_PUMPKIN 3
uint8_t D_8037D9F6;
float D_8037D9C8[3],D_8037D9E0[3],explicit_target[3];
int player_getTransformation(void){return 1;}
void player_getPosition(float *p){memcpy(p,explicit_target,12);}
void func_8028EC64(float *p){memcpy(p,explicit_target,12);}
void ncDynamicCamera_getPosition(float *p){memcpy(p,cameraPosition,12);}
void ncDynamicCamera_setPosition(float *p){memcpy(cameraPosition,p,12);}
'''
    for n in ('func_802BE258','func_802BE384','func_802BE484','func_802BC640','func_802BC84C'):
        f=segment.function('src/core2/nc/dynamicCamera.c',n)
        f=f.replace('sp2C = func_80320B98(sp48, sp3C, sp54, 0x9e0000);',
            'memcpy(trace.extended_end,sp3C,12); sp2C = func_80320B98(sp48, sp3C, sp54, 0x9e0000)!=NULL;')
        f=f.replace('tmp_v0 = func_8024575C(sp48, sp3C, 35.0f, sp54, 3, 0x9e0000);',
            'memcpy(trace.subtracted_end,sp3C,12); tmp_v0 = func_8024575C(sp48, sp3C, 35.0f, sp54, 3, 0x9e0000)!=NULL;')
        f=f.replace('func_802BE258(arg0, 35.0f);','func_802BE258(arg0, 35.0f); memcpy(trace.pushed_previous,arg0,12);')
        f=f.replace('phi_f20 = *phi_s0;', 'trace.recovery_attempts++; phi_f20 = *phi_s0;')
        f=f.replace('ml_vec3f_add(sp20, sp2C, sp44);', 'ml_vec3f_add(sp20, sp2C, sp44); trace.obstruction_calls++;')
        text+=f
    text+=r'''
int ref_contact_query(int kind,float *a,float *b,float r,int steps,uint32_t filter,float *n,int32_t *info){
 overflow=0;ref_cell=-1;BKCollisionTriangle *t=NULL;
 if(kind==0)t=func_80309EB0(a,r,n,filter);
 if(kind==1)t=func_80309DBC(a,b,r,n,steps,filter);
 if(kind==2)t=func_8024575C(a,b,r,n,steps,filter);
 if(kind==3)t=func_80309B48(a,b,n,filter);
 if(overflow)return -1;
 if(!t)return 0;
 for(int role=0;role<2;role++){
  BKCollisionList *cl=role?mapModel.collision_xlu:mapModel.collision_opa;
  BKCollisionTriangle *start=(BKCollisionTriangle*)(cl->data+cl->geo_count*4);
  uintptr_t ptr=(uintptr_t)t,lo=(uintptr_t)start;
  if(ptr<lo || ptr>=lo+cl->tri_count*sizeof(*t))continue;
  info[0]=role;info[1]=t-start;info[2]=ref_cell;info[3]=t->unk6;info[4]=t->flags;
  for(int i=0;i<3;i++)info[5+i]=t->unk0[i];
 }
 return 1;
}
int ref_contact_update(int obstruction,float *previous,float *camera,float *target,State *s,Trace *t){
 memset(&trace,0,sizeof(trace));overflow=0;
 D_8037D9F6=s->counter;memcpy(D_8037D9E0,s->position_step,12);memcpy(D_8037D9C8,s->angular_step,12);
 memcpy(explicit_target,target,12);memcpy(cameraPosition,camera,12);
 func_802BE484(previous,cameraPosition);
 trace.changed=cameraPosition[0]!=camera[0] || cameraPosition[1]!=camera[1] || cameraPosition[2]!=camera[2];
 if(obstruction && trace.changed)trace.recovered=func_802BC84C(1);
 memcpy(camera,cameraPosition,12);s->counter=D_8037D9F6;
 memcpy(s->position_step,D_8037D9E0,12);memcpy(s->angular_step,D_8037D9C8,12);*t=trace;
 return overflow?-1:(int)trace.changed;
}
'''
    (p/'ref.c').write_text(text)
    td=Path(trig.temporary.name)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),str(td/'sinf.c'),str(td/'cosf.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    lib.ref_load.argtypes=[C.c_int,C.c_void_p]
    lib.ref_contact_query.argtypes=[C.c_int,FP,FP,F,C.c_int,C.c_uint32,FP,C.POINTER(C.c_int32)]
    lib.ref_contact_update.argtypes=[C.c_int,FP,FP,FP,C.c_void_p,C.c_void_p]
    return lib
