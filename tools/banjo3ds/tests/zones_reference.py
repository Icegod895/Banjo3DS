"""Original-decomp selector/group builder/mode manager + M4.9 original camera.

No production zone, camera or contact imports. Existing original-source C
oracles supply math/contact. Host adapters replace N64 pointers, file IO and
unavailable manual/water/actor inputs; all are explicit normal dry-Banjo inputs.
"""
import ctypes as C
import functools
from pathlib import Path
import struct
import subprocess
import tempfile
import camera_reference as camera
import free_b_reference as free
import horizontal_reference

ROOT=camera.ROOT
F=C.c_float

def asset(order=None):
    raw=camera.ASSET.read_bytes();lo=struct.unpack_from('>3i',raw,2);hi=struct.unpack_from('>3i',raw,14)
    p=26;cells=[];enemy=0
    for x in range(lo[0],hi[0]+1):
        for y in range(lo[1],hi[1]+1):
            for z in range(lo[2],hi[2]+1):
                records=[]
                while raw[p]!=1:
                    tag=raw[p];p+=1
                    if tag in (0,2):p+=24 if tag==0 else 12
                    elif tag==3:
                        if raw[p]==10:
                            n=raw[p+1];p+=2
                            if raw[p]==11:
                                p+=1
                                for _ in range(n):
                                    v=struct.unpack_from('>3h2H2B2I',raw,p);category=(v[3]>>1)&63
                                    if category==7:enemy+=1
                                    if category==9:records.append((p,*v[:3],v[3]>>7,v[4],v[-1]&3))
                                    p+=20
                        if raw[p]==8:
                            n=raw[p+1];p+=2
                            if raw[p]==9:p+=1+12*n
                    else:raise AssertionError(tag)
                p+=1
                if order is None:records.reverse()
                else:
                    indices=(C.c_int*len(records))();order(len(records),indices)
                    records=[records[i] for i in indices]
                cells.append(((z,y,x),records))
    assert raw[p:p+2]==b'\0\3';p+=2;nodes={}
    while raw[p]:
        assert raw[p]==1 and raw[p+3]==2
        node,kind=struct.unpack_from('>hB',raw,p+1)[0],raw[p+4];p+=5;fields={}
        while raw[p]:
            tag=raw[p];p+=1
            fmt='i' if kind==4 else ('3f' if kind==2 else {1:'3f',2:'2f',3:'2f',4:'3f',5:'I',6:'2f'}[tag])
            fields[tag]=struct.unpack_from('>'+fmt,raw,p);p+=struct.calcsize('>'+fmt)
        p+=1;nodes[node]=(kind,fields)
    return [r for _,rs in sorted(cells) for r in rs],nodes,enemy

@functools.lru_cache(None)
def library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='zones-original-');p=Path(tmp.name)
    code=(Path(free.library(opt).temporary.name)/'reference.c').read_text()
    code=code.replace('*D_8036A9C8=groups','*D_8036A9C8=NULL')
    code=free.transform(code,'func_80290D48',lambda _: 'int func_80290D48(void);')
    code=free.transform(code,'ref_step',lambda s:s.replace('profile_r=radii[preset-1];profile_h=heights[preset-1];',''))
    # Full original group construction/merging; enemy lists only supply the
    # original merge guard, independently counted in canonical 071D (27).
    extra='''
#include <stdlib.h>
#define bk_realloc realloc
#define bk_malloc malloc
#define bk_free free
#define bk_memcpy memcpy
Struct_core2_7AF80_1 *D_8036A9CC,*D_8036A9BC;int D_8036A9B8;
'''
    for name in ('func_803063A8','func_80306534','func_80306840','func_8030688C','__code7AF80_concatElementsAndRemoveEmpty'):
        extra+=camera.original('src/core2/gccube.c',name)
    # Pointer-return original extractor separate from camera.original regex.
    text=(ROOT/'src/core2/gccube.c').read_text();start=text.index('Struct_core2_7AF80_1 *func_8030644C(');end=text.index('\n}\n',start)+3
    extra=extra.replace('void func_8030688C',text[start:end]+'\nvoid func_8030688C',1)
    extra+='''
#define PROP_1_CATEGORY_6_ACTOR 6
#define PROP_1_CATEGORY_8_PATH 8
#define PROP_1_CATEGORY_7_ENEMY_BOUNDARY 7
#define PROP_1_CATEGORY_9_CAMERA_TRIGGER 9
#define PROP_1_CATEGORY_A_FLAG 10
typedef struct {int category,bit0,unk10_6,identity;} ZoneOriginalProp;
typedef struct {int unk0_4;ZoneOriginalProp *prop1Ptr;} ZoneOriginalCube;
'''
    extra+=camera.original('src/core2/code_A5BC0.c','__codeA5BC0_initPropPointerForCube').replace('NodeProp','ZoneOriginalProp').replace('Cube *','ZoneOriginalCube *')
    extra+='''
void zone_reorder(int n,int *out){
 ZoneOriginalProp *input=calloc(n?n:1,sizeof(*input)),*output=calloc(n?n:1,sizeof(*output));
 for(int i=0;i<n;i++){input[i].category=9;input[i].identity=i;}
 ZoneOriginalCube cube={0,output};__codeA5BC0_initPropPointerForCube(input,&cube,n);
 for(int i=0;i<n;i++)out[i]=output[i].identity;free(output);
}
'''
    extra+='''
typedef struct {float position[3],horizontalSpeed,verticalSpeed,rotation,accelaration,
 closeDistance,farDistance,pitchYawRoll[3];uint32_t unknownFlag;} ZoomCameraNode;
ZoomCameraNode zone_nodes[70];int zone_types[70],zone_profiles[70];
float D_8037DAE8,D_8037DAEC;
int func_802903CC(void){return D_8037C018;}
int ncCameraNodeList_nodeIsValid(int n){return n>=0 && n<70 && zone_types[n];}
int ncCameraNodeList_getNodeType(int n){return zone_types[n];}
ZoomCameraNode *ncCameraNodeList_getZoomCameraNode(int n){return zone_nodes+n;}
void *ncCameraNodeList_getRandomCameraNode(int n){return zone_profiles+n;}
int code33250_func_802BA234(void *p){return *(int*)p;}
int bsBeeFly_inSet(int n){return 0;}
void *ncCameraNodeList_getPivotCameraNode(int n){abort();}
int code336F0_func_802BA89C(void *p){abort();}
void ncDynamicCam8_func_802BF9B8(int n){abort();}
'''
    for name in ('__code33310_func_802BA2D0','code33310_func_802BA4D0','code33310_func_802BA4F0',
                 'cameraNodeType3_getPositionWithPitchYawRoll','cameraNodeType3_getPosition',
                 'cameraNodeType3_getHorizontalAndVerticalSpeed','cameraNodeType3_getRotationAndAccelaration',
                 'cameraNodeType3_getCloseDistance','cameraNodeType3_getFarDistance'):
        extra+=camera.original('src/core2/code_33310.c',name)
    # Decompiled undeclared register-carried node argument made explicit; N64
    # pointer-valued s32 locals changed to pointer-width types on 64-bit host.
    f=camera.original('src/core2/nc/dynamicCam11.c','func_802BF798').replace('(void)','(int node)',1)
    f=f.replace('s32 temp_v0;','ZoomCameraNode *temp_v0;').replace('ncCameraNodeList_getZoomCameraNode()','ncCameraNodeList_getZoomCameraNode(node)')
    f=f.replace('&D_8037DAD0','D_8037DAD0').replace('&D_8037DAC0','D_8037DAC0')
    f=f.replace('D_8037DAE5 = 0;', 'D_8037DAE5 = 0; last_configured=node;')
    extra=extra.replace('float D_8037DAE8,D_8037DAEC;', 'float D_8037DAE8,D_8037DAEC;int last_configured=-1;')
    extra+=f
    table=(ROOT/'src/core2/code_35520.c').read_text()
    extra+="\ntypedef int16_t s16;\n#define MAP_1_SM_SPIRAL_MOUNTAIN 1\n#define MAP_0_NIL 0\n"
    extra+=table[table.index('struct camera_node_type4_vectors_s {'):table.index('struct overlay_table_map_s {')]
    start=table.index('static struct camera_node_type4_vectors_s sCode35520Table_SM[]')
    extra+=table[start:table.index('};',start)+2]
    extra+="\nstatic struct camera_node_type4_vectors_s *sCode35520_activeTable=sCode35520Table_SM;\n"
    start=table.index('static struct camera_node_type4_vectors_s *code35520_findTableEntry(')
    extra+=table[start:table.index('\n}',start)+2]
    extra+=camera.original('src/core2/code_35520.c','code35520_getDistanceVectors')
    extra+="\n#define D_8037C061 preset\nint selected_profile,D_8037C064,D_8037C068,D_8037C06C,D_8037C070,D_8037C074,D_8037C078,D_8037C07C,D_8037C080,D_8037C084;\n"
    extra+='void func_80290B60(int n){preset=n;}\nvoid func_802BD8A4(float r,float unused,float h){profile_r=r;profile_h=h;}\n'
    extra+=camera.original('src/core2/code_9BD0.c','func_80290BC0').replace('code35520_getDistanceVectors(arg0,','selected_profile=arg0; code35520_getDistanceVectors(arg0,')
    extra+=camera.original('src/core2/code_9BD0.c','func_80290D48').replace('s32 sp28;','void *sp28;')
    extra+='''
void zone_setup(const int *r,int count,int enemies,const float *z,const uint32_t *flags,const int *types,const int *profiles,int n){
 for(int g=0;g<D_8036A9C4;g++)if(D_8036A9C8)free(D_8036A9C8[g].unk8);
 free(D_8036A9C8);D_8036A9C8=NULL;D_8036A9C4=0;
 D_8036A9B8=enemies;D_8036A9BC=enemies?groups:NULL;
 for(int i=0;i<count;i++)func_8030688C(r[i*6+4],(int*)r+i*6,r[i*6+3],r[i*6+5]);
 __code7AF80_concatElementsAndRemoveEmpty(&D_8036A9C4,&D_8036A9C8);
 memset(D_80381FE8,1,80);memset(zone_types,0,sizeof(zone_types));
 for(int i=0;i<n;i++){
  ZoomCameraNode *v=zone_nodes+i;zone_types[i]=types[i];zone_profiles[i]=profiles[i];
  memcpy(v->position,z+12*i,12);memcpy(v->pitchYawRoll,z+12*i+3,12);
  v->horizontalSpeed=z[12*i+6];v->verticalSpeed=z[12*i+7];v->rotation=z[12*i+8];v->accelaration=z[12*i+9];
  v->closeDistance=z[12*i+10];v->farDistance=z[12*i+11];v->unknownFlag=flags[i];
 }
 last_configured=-1;selected_profile=0;profile_r=850;profile_h=375;
}
int zone_groups(int *out){int k=0;for(int g=0;g<D_8036A9C4;g++){
 out[k++]=D_8036A9C8[g].unk4;out[k++]=D_8036A9C8[g].count;
 for(int j=0;j<D_8036A9C8[g].count;j++){
  Struct_core2_7AF80_2 *r=D_8036A9C8[g].unk8+j;
  for(int i=0;i<3;i++)out[k++]=r->position[i];out[k++]=r->radius;out[k++]=r->unk10_3;
 }}return k;}
int zone_select(const float *p){int hit=func_803077FC((float*)p,&D_8037C010,&D_8037C014,300,1);return hit?func_80306D40(D_8037C010):-1;}
void zone_enable(int node,int value){D_80381FE8[node]=value;}
'''
    code+=extra
    (p/'reference.c').write_text(code)
    trig=Path(horizontal_reference.library(opt).temporary.name)
    subprocess.run(['cc',*camera.FLAGS,opt,'-shared','-fPIC',str(p/'reference.c'),str(trig/'sinf.c'),str(trig/'cosf.c'),'-lm','-o',str(p/'reference.so')],check=True)
    lib=C.CDLL(str(p/'reference.so'));lib.temporary=tmp
    fp=C.POINTER(F);ip=C.POINTER(C.c_int)
    for name,args,restype in (
        ('zone_setup',[ip,C.c_int,C.c_int,fp,C.POINTER(C.c_uint32),ip,ip,C.c_int],None),
        ('zone_reorder',[C.c_int,ip],None),('zone_groups',[ip],C.c_int),('zone_select',[fp],C.c_int),('zone_enable',[C.c_int,C.c_int],None),
        ('composition_init',[fp,F,fp,fp],None),('composition_seed',[F,C.c_uint32],None),
        ('composition_step',[fp,F,F,F,F,C.c_int,C.c_int,C.c_int,fp],C.c_int),
        ('ref_snapshot',[fp,ip],None),('ref_load',[C.c_int,C.c_void_p],None),
        ('composition_state',[fp,C.POINTER(C.c_uint32),C.c_void_p],None)):
        f=getattr(lib,name);f.argtypes=args;f.restype=restype
    return lib

def configure(lib):
    records,nodes,enemy=asset(lib.zone_reorder);rows=[x for r in records for x in r[1:]];floats=[];flags=[];types=[];profiles=[]
    for n in range(70):
        kind,fields=nodes.get(n,(0,{}));types.append(kind);profiles.append(fields[1][0] if kind==4 else 0)
        floats.extend((*fields[1],*fields[4],*fields[2],*fields[3],*fields[6]) if kind==3 else [0]*12)
        flags.append(fields[5][0] if kind==3 else 0)
    lib.zone_setup((C.c_int*len(rows))(*rows),len(records),enemy,(F*len(floats))(*floats),
        (C.c_uint32*70)(*flags),(C.c_int*70)(*types),(C.c_int*70)(*profiles),70)
