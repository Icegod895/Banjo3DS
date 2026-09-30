"""Original code_94A20.c compiled against original static map query.
No production floor/query code. Host pointer ABI adapted; original unspecified
storage is zeroed solely for canonical snapshots, never as a gameplay rule.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import segment_reference as segment

@functools.lru_cache(None)
def library(opt):
    base=segment.library(opt)
    text=(Path(base._tmp.name)/'ref.c').read_text()
    text+=r'''
#include <stddef.h>
typedef int16_t s16;typedef uint16_t u16;typedef uint8_t u8;
typedef BKVertexList BKModelBin;
typedef struct {
 void *model;BKCollisionTriangle unk4,unk10;
 float unk1C[3],unk28[3],normX,normY,normZ,posX,posY,posZ;
 u32 unk4C;s16 unk50,pad52;u32 unk54;
 u8 unk58,unk59,unk5A,unk5B,unk5C,unk5D,unk5E,pad5f;
} struct0;
typedef struct {float unk0[3],unkC;s32 flags;s16 unk14,pad;void *unk18;} struct86s;
static struct0 *state;static unsigned parity;
static int identities[2][3];
static float calls[64][6];static u32 masks[64];static unsigned ncalls;
static void *bk_malloc(size_t n){(void)n;return calloc(1,sizeof(struct0));}
static void bk_free(void*p){free(p);}
static void ml_vec3f_clear(float*p){memset(p,0,12);}
static float ml_max_f(float a,float b){return a>b?a:b;}
static float mlAbsF(float x){return fabsf(x);}
static unsigned globalTimer_getTimeMasked(unsigned m){return parity&m;}
static void *func_803209EC(void){return (void*)mapModel.unk20;}
static void collisionTri_copy(BKCollisionTriangle *dst,BKCollisionTriangle *src){
 *dst=*src;int which=dst==&state->unk4?0:1;
 for(int role=0;role<2;role++){
  BKCollisionList *c=role?mapModel.collision_xlu:mapModel.collision_opa;
  BKCollisionTriangle *first=(BKCollisionTriangle*)(c->data+4*c->geo_count);
  uintptr_t p=(uintptr_t)src,a=(uintptr_t)first;
  if(p>=a && p<a+12*c->tri_count){identities[which][0]=role;identities[which][1]=(p-a)/12;identities[which][2]=ref_cell;}
 }
}
'''
    src=(segment.ROOT/'src/core2/code_94A20.c').read_text()
    src='\n'.join(l for l in src.splitlines() if not l.startswith('#include') and not l.startswith('BKCollisionTriangle *func_80309B48('))
    # Source pointer-to-array spelling only: same pointer and arithmetic.
    for name in ('sp34','sp28','sp38','sp30','D_8036DDC0'):
        src=src.replace('&'+name+',',name+',')
    src=src.replace('&this->normX', '(float *)((char *)this + offsetof(struct0,normX))')
    src=src.replace('    return sp24;', '''    if(ncalls<64){
        memcpy(calls[ncalls],arg0,12);calls[ncalls][3]=arg1;calls[ncalls][4]=arg2;
        calls[ncalls][5]=sp24!=NULL;masks[ncalls++]=arg3;
    }
    return sp24;''')
    text+=src+r'''
void floor_ref_init(void){free(state);state=func_8031B9D8();memset(identities,255,sizeof(identities));ncalls=0;}
void floor_ref_reinit(void){func_8031BA7C(state);}
void floor_ref_step(float*p,float upper,u32 mask,unsigned frame_parity){
 parity=frame_parity;ncalls=0;func_8031C618(state,p);func_8031C5FC(state,upper);func_8031C638(state,mask);func_8031C44C(state);
}
unsigned floor_ref_calls(float*out,u32*filters){memcpy(out,calls,ncalls*24);memcpy(filters,masks,ncalls*4);return ncalls;}
void floor_ref_snapshot(uint8_t*out){
 memset(out,0,120);u32 model=state->model?(state->model==mapModel.model_bin_xlu?2:1):0;
 memcpy(out,&model,4);memcpy(out+4,&state->unk4,24);
 memcpy(out+28,state->unk1C,48);memcpy(out+76,&state->unk4C,4);
 memcpy(out+80,&state->unk50,2);memcpy(out+84,&state->unk54,4);
 memcpy(out+88,&state->unk58,7);memcpy(out+96,identities,24);
}
'''
    tmp=tempfile.TemporaryDirectory(prefix='floor-original-');p=Path(tmp.name)
    (p/'ref.c').write_text(text)
    subprocess.run(['cc',*segment.FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    lib.ref_load.argtypes=[C.c_int,C.c_void_p]
    lib.floor_ref_step.argtypes=[C.POINTER(C.c_float),C.c_float,C.c_uint32,C.c_uint]
    lib.floor_ref_snapshot.argtypes=[C.c_void_p]
    lib.floor_ref_calls.argtypes=[C.c_void_p,C.c_void_p]
    lib.ref_terrain.argtypes=[C.POINTER(C.c_float),C.POINTER(C.c_int)];lib.ref_terrain.restype=C.c_float
    return lib

def snapshot(lib):
    b=C.create_string_buffer(120);lib.floor_ref_snapshot(b);return b.raw

def calls(lib):
    values=(C.c_float*(64*6))();masks=(C.c_uint32*64)()
    n=lib.floor_ref_calls(values,masks)
    return [list(values[i*6:i*6+6])+[masks[i]] for i in range(n)]
