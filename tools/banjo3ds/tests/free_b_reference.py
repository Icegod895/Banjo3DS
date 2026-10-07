"""Original free-B + original static contact in one independent translation unit.

No production algorithms/headers imported. Reuse source extraction from the
existing independent oracles, remove duplicate ORIGINAL utility definitions,
replace the old unobstructed stubs with original contact, add observers only.
"""
import ctypes as C
import functools
from pathlib import Path
import re
import subprocess
import tempfile
import camera_reference as camera
import contact_reference as contact
import segment_reference
import horizontal_reference

ROOT=camera.ROOT
FLAGS=camera.FLAGS
F=C.c_float

def span(text,name):
    m=re.search(r'(?m)^(?:static[ \t]+)?(?:void|f32|s32|bool|int|float|BKCollisionTriangle[ \t]*\*)[ \t]+'+re.escape(name)+r'\([^;]*?\)\s*\{',text)
    if not m:raise ValueError(name)
    end=m.end();depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return m.start(),end

def transform(text,name,fn):
    a,b=span(text,name);return text[:a]+fn(text[a:b])+text[b:]

@functools.lru_cache(None)
def library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='free-b-original-');p=Path(tmp.name)
    c=(Path(camera.library(opt).temporary.name)/'reference.c').read_text()
    q=(Path(contact.library(opt)._tmp.name)/'ref.c').read_text()
    q=re.sub(r'(?m)^#define LENGTH_SQ_VEC3F.*\n','',q)
    c=c.replace('int func_802BE60C(void){return 0;}','int func_802BE60C(void);')
    c=c.replace('int func_802BC84C(int x){return 0;}','int func_802BC84C(int);')
    # All duplicated bodies below are the SAME original math/adapters, not
    # production equivalents. Keep camera's player/camera context adapters.
    names=re.findall(r'(?m)^(?:static[ \t]+)?(?:void|f32|s32|bool|int|float)[ \t]+(\w+)\([^;]*?\)\s*\{',c)
    for name in names:
        try:a,b=span(q,name)
        except ValueError:continue
        q=q[:a]+q[b:]
    begin=q.index('typedef struct {uint32_t sphere_calls')
    end=q.index('Trace trace;',begin)+len('Trace trace;')
    decl=q[begin:end];q=q[:begin]+q[end:]
    prefix='''
#include <stdint.h>
'''+decl+'''
typedef struct {
 float previous[3],desired[3],smoothed[3],corrected[3],final_position[3],look[3],dot;
 uint32_t rollback_executed,rolled_back,free_b;Trace contact;
} Frame;
Frame observed;
float original_rollback_history,D_8037D948[3];
int viewport_noop;
'''
    # Local-static -> file-static storage adapter exposes the same persistent
    # value for snapshot/lifecycle fixtures. B-init is NOT modified to reset it.
    def rollback(f):
        f=f.replace('static f32 D_8037DB9C;','')
        f=f.replace('D_8037DB9C','original_rollback_history')
        f=f.replace('ncDynamicCamera_getPosition(cameraStateB.D_8037DB78);',
                    'observed.rollback_executed=1; ncDynamicCamera_getPosition(cameraStateB.D_8037DB78);')
        f=f.replace('ncDynamicCamera_setPosition(cameraStateB.D_8037DB84);',
                    'observed.rolled_back=1; ncDynamicCamera_setPosition(cameraStateB.D_8037DB84);')
        return f.replace('original_rollback_history = sp1C;', 'original_rollback_history = sp1C; observed.dot=sp1C;')
    c=transform(c,'func_802C03BC',rollback)
    c=transform(c,'func_802BE190',lambda f:f.replace('{','{\n memcpy(observed.desired,arg0,12);',1).replace(
        'ncDynamicCamera_setPosition(sp34);','ncDynamicCamera_setPosition(sp34); memcpy(observed.smoothed,cameraPosition,12); memcpy(observed.corrected,cameraPosition,12);'))
    c=transform(c,'func_802BD904',lambda f:f.replace('{','{\n memcpy(observed.look,target_rotation,12);',1))
    c=c.replace('cameraMode_update();func_802BCA58();',
                'cameraMode_update();memcpy(D_8037D948,cameraPosition,12);memcpy(observed.previous,cameraPosition,12);func_802BCA58();')
    # Original BE60C implements the component comparison after BE484; set
    # ordinary gameplay map/snap guards explicitly, without production calls.
    q+='\n#define MAP_91_FILE_SELECT 0x91\nint gsworld_getMap(void){return 0x01;}\n'
    f=segment_reference.function('src/core2/nc/dynamicCamera.c','func_802BE60C')
    f=f.replace('return !(sp1C[0]', 'memcpy(observed.corrected,cameraPosition,12); return trace.changed = !(sp1C[0]')
    q+=f
    q=transform(q,'func_802BC84C',lambda f:f.replace('func_802BC84C','original_obstruction',1))
    q+='''
int func_802BC84C(int mode){int r=original_obstruction(mode);trace.recovered=r;memcpy(observed.corrected,cameraPosition,12);return r;}
'''
    # Original final viewport transition, explicitly inactive. Its entire body
    # is compiled, but no active-transition trigger exists in this fixture.
    q+='\nstatic float s_position[3],s_rotation[3],s_time_remaining_s,s_duration;static uint8_t s_state;\n'
    for name in ('func_802C2258','func_802C22C0'):
        q+=segment_reference.function('src/core2/code_3B2C0.c',name)
    q+='''
void composition_init(const float *p,float floor,const float *eye,const float *rotation){
 profile_r=850;profile_h=375;
 ref_init(p,floor,eye,rotation);original_rollback_history=0;D_8037D9F6=0;
 func_802C2258();memset(&observed,0,sizeof(observed));
}
int composition_step(const float *p,float floor,float yaw,float under,float dt,int vi,int stable,int preset,const float *target){
 memset(&trace,0,sizeof(trace));memset(&observed,0,sizeof(observed));overflow=0;
 memcpy(explicit_target,target,12);ref_step(p,floor,yaw,under,dt,vi,stable,preset);
 observed.free_b=dynamic_state==11;observed.contact=trace;memcpy(observed.final_position,cameraPosition,12);
 float pos[3],rot[3];memcpy(pos,cameraPosition,12);memcpy(rot,cameraRotation,12);
 func_802C22C0(pos,rot);
 viewport_noop=s_state==0 && memcmp(pos,cameraPosition,12)==0 && memcmp(rot,cameraRotation,12)==0;
 return !overflow && viewport_noop;
}
void composition_state(float *dot,uint32_t *counter,Frame *frame){*dot=original_rollback_history;*counter=D_8037D9F6;*frame=observed;}
void composition_seed(float history,uint32_t counter){original_rollback_history=history;D_8037D9F6=counter;}
void composition_rollback(float *previous,float *desired,float *corrected,float *history,float *dot,int *rolled){
 memcpy(cameraStateB.D_8037DB84,previous,12);memcpy(cameraStateB.D_8037DB90,desired,12);memcpy(cameraPosition,corrected,12);
 original_rollback_history=*history;observed.rolled_back=0;func_802C03BC();
 memcpy(corrected,cameraPosition,12);*history=original_rollback_history;*dot=observed.dot;*rolled=observed.rolled_back;
}
'''
    code=prefix+c+q
    (p/'reference.c').write_text(code)
    td=Path(horizontal_reference.library(opt).temporary.name)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'reference.c'),str(td/'sinf.c'),str(td/'cosf.c'),'-lm','-o',str(p/'reference.so')],check=True)
    lib=C.CDLL(str(p/'reference.so'));lib.temporary=tmp
    fp=C.POINTER(F);ip=C.POINTER(C.c_int)
    for n,args,ret in (
        ('ref_setup',[ip,C.c_int,fp],None),('ref_load',[C.c_int,C.c_void_p],None),
        ('composition_init',[fp,F,fp,fp],None),
        ('composition_step',[fp,F,F,F,F,C.c_int,C.c_int,C.c_int,fp],C.c_int),
        ('ref_snapshot',[fp,ip],None),('ref_seed',[fp,fp],None),
        ('composition_seed',[F,C.c_uint32],None),
        ('composition_state',[fp,C.POINTER(C.c_uint32),C.c_void_p],None),
        ('composition_rollback',[fp,fp,fp,fp,fp,ip],None)):
        fn=getattr(lib,n);fn.argtypes=args;fn.restype=ret
    return lib
