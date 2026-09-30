"""Compile original NTSC static-map query, never production query/packet code.
Native host structs are populated directly from original asset blocks.
"""
import ctypes as C
import functools
from pathlib import Path
import re
import subprocess
import tempfile
from world_query_reference import ROOT, original

FLAGS=['-std=c99','-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard','-fno-strict-aliasing']

def function(path,name):
    s=(ROOT/path).read_text()
    m=re.search(r'(?m)^[\w *]+\b'+name+r'\([^;]*?\)\s*\{',s)
    if not m:raise ValueError(name)
    end=m.end();depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[m.start():end]+'\n'

@functools.lru_cache(None)
def library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='segment-reference-');p=Path(tmp.name)
    text=r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>
typedef float f32;typedef int32_t s32;typedef uint32_t u32;
typedef struct {struct {int16_t ob[3];uint8_t rest[10];} v;} Vtx;
typedef struct {int16_t minCoord[3],maxCoord[3],centerCoord[3],local_norm,count,global_norm;Vtx vertices[];} BKVertexList;
typedef struct {int16_t start_tri_index,tri_count;} BKCollisionGeometry;
typedef struct {int16_t unk0[3],unk6;uint32_t flags;} BKCollisionTriangle;
typedef struct {int16_t min[3],max[3],y_stride,z_stride,geo_count,scale,tri_count;uint8_t pad16[2],data[];} BKCollisionList;
struct {BKCollisionGeometry *list[100],**current;} sActiveCollisionLists;
struct {BKCollisionList *collision_opa,*collision_xlu;BKVertexList *model_bin_opa,*model_bin_xlu;intptr_t unk20;} mapModel;
int ref_cell=-1;
#define ABS_F(x) ((x)>=0.0f?(x):-(x))
#define modelbin_getVtxList(x) (x)
void collisionList_setStoredTriangle(BKCollisionTriangle *t,BKVertexList *v){(void)t;(void)v;}
'''
    text+=(ROOT/'include/math.h').read_text()+'\n'
    for n in ('ml_vec3f_copy','ml_vec3f_scale_copy','ml_vec3f_normalize_copy'):
        text+=function('src/core1/ml.c',n)
    for n in ('collisionList_getIntersecting_s32','collisionList_calculateBoundsAndDirection','collisionList_intersectLine'):
        f=function('src/core2/code_5FD90.c',n)
        # Only observer instrumentation; no intersection arithmetic edits.
        f=f.replace('result_collision = i_tri;', 'result_collision = i_tri; ref_cell=(int)(*i_geo-(BKCollisionGeometry*)this->data);')
        text+=f
    text+=function('src/core2/mapModel.c','func_80309B48').replace('(s32) mapModel.', '(intptr_t) mapModel.')
    text+='''\nBKCollisionTriangle *last_hit;
BKCollisionTriangle *func_80320B98(float *a,float *b,float *n,uint32_t f){last_hit=func_80309B48(a,b,n,f);return last_hit;}
'''
    text+=function('src/core1/code_72B0.c','func_80245314')
    text+='''\nfloat cameraPosition[3],D_8037D9A0;int D_8037D940=0;
int func_802BC428(void){return 0;}
'''
    text+=function('src/core2/nc/dynamicCamera.c','func_802BCD60').replace('temp_v0 = func_80245314(sp28, sp34, 10.0f, -600.0f, 0x800000);', 'temp_v0 = func_80245314(sp28, sp34, 10.0f, -600.0f, 0x800000) != NULL;')
    text+=r'''
static unsigned read16(const uint8_t*p){return (unsigned)p[0]*256+p[1];}
static uint32_t read32(const uint8_t*p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
void ref_load(int role,const uint8_t *raw){
 unsigned vo=read32(raw+16),co=read32(raw+28);
 const uint8_t *v=raw+vo,*c=raw+co;int nv=read16(v+20),nc=read16(c+16),nt=read16(c+20);
 BKVertexList *vl=calloc(1,24+nv*16);BKCollisionList *cl=calloc(1,24+nc*4+nt*12);
 for(int i=0;i<12;i++)((int16_t*)vl)[i]=read16(v+2*i);
 for(int i=0;i<nv;i++)for(int j=0;j<3;j++)vl->vertices[i].v.ob[j]=read16(v+24+16*i+2*j);
 for(int i=0;i<11;i++)((int16_t*)cl)[i]=read16(c+2*i);
 for(int i=0;i<nc*2;i++)((int16_t*)cl->data)[i]=read16(c+24+2*i);
 BKCollisionTriangle *ts=(BKCollisionTriangle*)(cl->data+nc*4);
 for(int i=0;i<nt;i++){
  for(int j=0;j<3;j++)ts[i].unk0[j]=read16(c+24+nc*4+12*i+2*j);
  ts[i].unk6=read16(c+24+nc*4+12*i+6);ts[i].flags=read32(c+24+nc*4+12*i+8);
 }
 if(role){free(mapModel.model_bin_xlu);free(mapModel.collision_xlu);mapModel.model_bin_xlu=vl;mapModel.collision_xlu=cl;}
 else {free(mapModel.model_bin_opa);free(mapModel.collision_opa);mapModel.model_bin_opa=vl;mapModel.collision_opa=cl;}
}
int ref_query(float *start,float *end,uint32_t mask,float *normal,int32_t *info){
 ref_cell=-1;BKCollisionTriangle *t=func_80309B48(start,end,normal,mask);
 if(!t)return 0;
 int role=mapModel.unk20==(intptr_t)mapModel.model_bin_xlu;
 BKCollisionList *cl=role?mapModel.collision_xlu:mapModel.collision_opa;
 info[0]=role;info[1]=(int)(t-(BKCollisionTriangle*)(cl->data+cl->geo_count*4));
 info[2]=ref_cell;info[3]=t->unk6;info[4]=t->flags;
 for(int i=0;i<3;i++)info[5+i]=t->unk0[i];return 1;
}
float ref_terrain(float *camera,int *hit){
 memcpy(cameraPosition,camera,12);last_hit=NULL;
 float y=func_802BCD60();*hit=last_hit!=NULL;return y;
}
'''
    (p/'ref.c').write_text(text)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    fp=C.POINTER(C.c_float);ip=C.POINTER(C.c_int32)
    lib.ref_load.argtypes=[C.c_int,C.c_void_p]
    lib.ref_query.argtypes=[fp,fp,C.c_uint32,fp,ip];lib.ref_query.restype=C.c_int
    lib.ref_terrain.argtypes=[fp,ip];lib.ref_terrain.restype=C.c_float
    return lib

def load_real(lib):
    for role,asset in enumerate((0x14cf,0x14d0)):
        data=(ROOT/f'assets/model/{asset:04X}.model.bin').read_bytes()
        lib.ref_load(role,C.create_string_buffer(data))
