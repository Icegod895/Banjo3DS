"""Independent actor 3BA/mesh oracle compiled from the original decomp.

Only original routines/assets and existing independent decomp query/camera
oracles are used. Production bridge/state/query headers are never imported.
Unrelated mesh modes/sound/callbacks abort if unexpectedly reached.
"""
import ctypes as C
import functools
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import free_b_reference as free
import horizontal_reference
from segment_reference import function, FLAGS, ROOT
from world_query_reference import original

F=C.c_float

def membership():
    raw=(ROOT/'assets/model/14D0.model.bin').read_bytes()
    pos=struct.unpack_from('>I',raw,36)[0]
    count=struct.unpack_from('>h',raw,pos)[0];pos+=2;out={}
    for _ in range(count):
        uid,n=struct.unpack_from('>hh',raw,pos);pos+=4
        ids=list(struct.unpack_from('>'+str(n)+'h',raw,pos));pos+=2*n
        if uid in (497,498,499):out[uid]=ids
    return out

def actor_setup():
    """Original 071D cube/NodeProp stream, category 6 actor (prop.h:379)."""
    import math
    raw=(ROOT/'assets/lvl_setup/071D.lvl_setup.bin').read_bytes()
    lo=struct.unpack_from('>3i',raw,2);hi=struct.unpack_from('>3i',raw,14)
    assert raw[:2]==b'\1\1'
    p=26;actors=[]
    for _ in range(math.prod(hi[i]-lo[i]+1 for i in range(3))):
        while raw[p]!=1:
            tag=raw[p];p+=1
            if tag==0:p+=24
            elif tag==2:p+=12
            elif tag==3:
                if raw[p] in (10,6):
                    kind,n=raw[p:p+2];p+=2
                    if raw[p]==(11 if kind==10 else 7):
                        p+=1
                        for _ in range(n):
                            fields=struct.unpack_from('>3h2H2B2I',raw,p)
                            if ((fields[3]>>1)&63)==6 and fields[4]==0x3ba:
                                actors.append(dict(offset=p,position=list(fields[:3]),record_hex=raw[p:p+20].hex()))
                            p+=20
                if raw[p]==8:
                    n=raw[p+1];p+=2
                    if raw[p]==9:p+=1+12*n
            else:raise AssertionError((p,tag))
        p+=1
    assert raw[p:p+2]==b'\0\3'
    return dict(setup_sha256=hashlib.sha256(raw).hexdigest(),actors=actors)

def geometry_manifest():
    source=original(0x14d0,1);ids=set(sum(membership().values(),[]));occ=[]
    for cell,(start,n) in enumerate(source['cells']):
        for i in range(start,start+n):
            record=source['records'][i]
            if ids.intersection(record[:3]):occ.append([cell,i,*record])
    return dict(meshes={str(k):v for k,v in membership().items()},
                vertex_ids=sorted(ids),occurrences=occ,
                unique_triangles=len({tuple(x[2:]) for x in occ}),
                source_sha256=source['source_sha'])

@functools.lru_cache(None)
def library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='bridge-original-');p=Path(tmp.name)
    source=(Path(free.library(opt).temporary.name)/'reference.c').read_text()
    source+='''
#include <assert.h>
typedef uint16_t u16;typedef int16_t s16;
typedef struct S {
 int unk0,unk28,unk29,unk4C,unk4E;float unk4,unk8,unk44,unk48;
 float unk70,unk74,unk98,unk9C,unk20,unk24; s16 unk14[3],unk1A[3];
 void (*unkC)(struct S *);void (*unk10)(struct S *);
} Struct6Ds;
typedef struct {Vtx v;int vtx_id;} BKModelVtxRef;
typedef struct {int unused;} BKModel;
typedef struct Actor {int volatile_initialized;void *marker;} Actor;
static Actor bridge_actor;static Struct6Ds mesh[3];
static BKModelVtxRef saved[3][32];static int counts[3],bridge_alive,despawns;
static uint32_t learnedAbilities;
void marker_despawn(void *m){(void)m;bridge_alive=0;despawns++;}
void model_getMeshCoordRange(BKModel *m,int id,s16 *a,s16 *b){
 (void)m;(void)id;memset(a,0,6);memset(b,0,6); /* unused in vertical mode */
}
Struct6Ds *func_8034C528(int id){assert(id>=497&&id<=499);return &mesh[id-497];}
void model_transformMesh(BKModel *m,int id,void (*fn)(s32 *,BKModelVtxRef *,Vtx *,Struct6Ds *),intptr_t state){
 (void)m;int i=id-497;
 for(int j=0;j<counts[i];j++)fn((s32 *)(intptr_t)id,&saved[i][j],&mapModel.model_bin_xlu->vertices[saved[i][j].vtx_id],(Struct6Ds *)state);
}
#define UNUSED_TRANSFORM(n) void n(s32 *id,BKModelVtxRef *s,Vtx *d,Struct6Ds *m){abort();}
UNUSED_TRANSFORM(func_8034D240)
UNUSED_TRANSFORM(func_8034D554)
UNUSED_TRANSFORM(func_8034D634)
UNUSED_TRANSFORM(func_8034D740)
UNUSED_TRANSFORM(func_8034D9C8)
UNUSED_TRANSFORM(func_8034DA7C)
float func_8030E200(int x){abort();} int sfxSource_getSampleRate(int x){abort();}
float randf2(float a,float b){abort();} int randi2(int a,int b){abort();}
void sfxsource_playSfxAtVolume(int x,float f){abort();}
void sfxsource_setSampleRate(int x,int r){abort();}
void sfxsource_freeSfxsourceByIndex(int x){abort();}
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
'''
    enum=(ROOT/'include/core2/abilityprogress.h').read_text()
    begin=enum.index('enum ability_e {');end=enum.index('};',begin)+2
    source+=enum[begin:end]+'\n'
    source+=function('src/core2/abilityprogress.c','ability_hasLearned')
    source+=function('src/core2/code_7060.c','player_isAbilityUnlocked')
    source+=function('src/core2/ch/mole.c','chmole_learnedAllSpiralMountainAbilities')
    for name in ('func_8034D700','func_8034DBB8','func_8034DD74','subaddie_positionMoveVertical','func_8034DEB4','func_8034E26C'):
        # Pointer width adaptation ONLY; mathematical/branch body untouched.
        source+=function('src/core2/code_C62B0.c',name).replace('(s32) arg0','(intptr_t) arg0')
    for name in ('func_80363440','func_80363470','func_803634BC','func_80363500'):
        source+=function('src/core2/code_DC4B0.c',name)
    source+='''
void bridge_ref_reset(const uint8_t *raw){
 ref_load(1,raw);bridge_actor=(Actor){0};bridge_alive=1;despawns=0;
 memset(mesh,0,sizeof(mesh));memset(counts,0,sizeof(counts));
 unsigned pos=read32(raw+36),n=read16(raw+pos);pos+=2;
 for(unsigned k=0;k<n;k++){
  int id=read16(raw+pos),count=read16(raw+pos+2);pos+=4;
  if(id>=497&&id<=499){int i=id-497;counts[i]=count;assert(count<=32);
   for(int j=0;j<count;j++){int v=read16(raw+pos+2*j);saved[i][j]=(BKModelVtxRef){mapModel.model_bin_xlu->vertices[v],v};}
   func_8034DD74(&mesh[i],0,NULL,id);
  }pos+=2*count;
 }
}
void bridge_ref_actor(uint32_t abilities){learnedAbilities=abilities;if(bridge_alive)func_80363500(&bridge_actor);}
void bridge_ref_mesh(float dt){current_dt=dt;for(int i=0;i<3;i++)func_8034E26C(&mesh[i],NULL,497+i);}
void bridge_ref_xyz(int role,int vertex,int16_t *p){
 BKVertexList *m=role?mapModel.model_bin_xlu:mapModel.model_bin_opa;
 memcpy(p,m->vertices[vertex].v.ob,6);
}
void bridge_ref_state(float *values,int32_t *flags){
 for(int i=0;i<3;i++){values[i*2]=mesh[i].unk4;values[i*2+1]=mesh[i].unk44;
  flags[i*2]=mesh[i].unk29!=0;flags[i*2+1]=mesh[i].unk4C;}
 flags[6]=bridge_actor.volatile_initialized;flags[7]=bridge_alive;flags[8]=despawns;
}
'''
    (p/'ref.c').write_text(source)
    td=Path(horizontal_reference.library(opt).temporary.name)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),str(td/'sinf.c'),str(td/'cosf.c'),'-lm','-o',str(p/'ref.so')],check=True,capture_output=True)
    lib=C.CDLL(str(p/'ref.so'));lib.temporary=tmp
    # Keep all existing original camera/query signatures exactly.
    parent=free.library(opt)
    for name in ('ref_load','ref_setup','composition_init','composition_step','composition_state','composition_seed','ref_snapshot','ref_seed'):
        getattr(lib,name).argtypes=getattr(parent,name).argtypes
        getattr(lib,name).restype=getattr(parent,name).restype
    lib.bridge_ref_reset.argtypes=[C.c_void_p]
    lib.bridge_ref_actor.argtypes=[C.c_uint32]
    lib.bridge_ref_mesh.argtypes=[F]
    lib.bridge_ref_xyz.argtypes=[C.c_int,C.c_int,C.POINTER(C.c_int16)]
    lib.bridge_ref_state.argtypes=[C.POINTER(F),C.POINTER(C.c_int32)]
    lib.ref_contact_query.argtypes=[C.c_int,C.POINTER(F),C.POINTER(F),F,C.c_int,C.c_uint32,C.POINTER(F),C.POINTER(C.c_int32)]
    return lib
