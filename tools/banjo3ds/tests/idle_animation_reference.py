"""Test-only 006F reference using original C evaluator/matrix routines.

No production Banjo3DS imports. C fragments are read from the decompilation
and compiled into a temporary host library with contraction/fast-math disabled.
Original libultra sin/cos polynomials are used, not host sin/cos. N64 bitfields
are unpacked explicitly before assigning host C fields. The golden pose is the
unblended target at normalized time zero, not a history-dependent transition.

Geometry uses the existing independent canonical traversal, quantizing each
loaded RSP modelview matrix to signed 16.16 (truncation toward zero). XYZ is
affine model-space output, not a claim of bit-exact RSP projection/clipping.
Hash packing: 109 bones in ID order, >10f = quaternion XYZW, scale XYZ,
translation XYZ. Geometry: triangle corners in traversal order, each >3f.
"""
import ctypes as C
import functools
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from banjo_pose_reference import PoseReference

ROOT = Path(__file__).resolve().parents[3]
ANIMATION_SHA = 'f9df06acf7e20bfb284b24aaca388c97db416a0b0884628e1f13ed5ea5d7d32b'
CANONICAL_TIME = 0.0
F = C.c_float
FP = C.POINTER(F)


def f32(value):
    return F(value).value


def original_function(path, name):
    text = (ROOT / path).read_text()
    match = re.search(r'(?m)^(?:static\s+)?(?:void|f32|s32|bool)\s+' + name + r'\([^;]*?\)\s*\{', text)
    if not match:
        raise ValueError(f'Original function not found: {name}')
    start, end, depth = match.start(), match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


@functools.lru_cache(maxsize=1)
def original_library():
    temporary = tempfile.TemporaryDirectory(prefix='banjo-idle-reference-')
    directory = Path(temporary.name)
    # Preserve original polynomial constants by value on either host endianness.
    for name, alias in [('sinf','fsin'), ('cosf','fcos')]:
        text = (ROOT / f'lib/ultralib/src/gu/{name}.c').read_text()
        text = re.sub(r'^#(?:include|pragma|define).*$','',text,flags=re.M)
        text = re.sub(r'\{(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)\}',
                      lambda m: '{.d=' + struct.unpack('>d',struct.pack('>II',
                          int(m[1],16),int(m[2],16)))[0].hex() + '}',text)
        prefix = ('#include <math.h>\n#include <stdint.h>\n'
                  'typedef union {double d;} du;\n'
                  'typedef union {uint32_t i;float f;} fu;\n'
                  '#define ROUND(d) (int)(((d)>=0.0)?((d)+0.5):((d)-0.5))\n'
                  '#define ABS(x) ((x)<0?-(x):(x))\n#define __libm_qnan_f NAN\n'
                  f'#define {alias} reference_{name}\n')
        (directory / f'{name}.c').write_text(prefix+text)
    header = (ROOT / 'include/core2/animationfile.h').read_text()
    header = re.sub(r'^#.*$', '', header, flags=re.M)
    code = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef float f32; typedef int32_t s32; typedef uint32_t u32;
typedef int16_t s16; typedef uint16_t u16;
typedef struct {float m[4][4];} MtxF;
typedef struct BoneTransformList BoneTransformList;
#define BAD_PI 3.141592654
#define BAD_DTOR (BAD_PI/180.0)
#define LENGTH_SQ_VEC4F(v) (v[0]*v[0]+v[1]*v[1]+v[2]*v[2]+v[3]*v[3])
float reference_sinf(float); float reference_cosf(float);
#define sinf reference_sinf
#define cosf reference_cosf
MtxF D_80282810[32], *s_mtx_stack;
f32 D_80276578=BAD_DTOR, D_8027657C=BAD_DTOR;
s32 D_80371ED0[3]={1,2,0};
f32 D_803709E0[]={0,0,0,1,1,1,0,0,0,0,0,0};
MtxF *mlMtx_get_stack_pointer(void) {return s_mtx_stack;}
'''+header
    files = {
        'src/core2/code_B9770.c': ['func_80340700','glspline_catmull_rom_interpolate'],
        'src/core2/animationfile.c': ['animationfilebin_func_8033ABA0',
                                    'animationfilebin_func_8033AA10','animationfilebin_func_8033AC38'],
        'src/core1/mlmtx.c': ['mlMtxIdent','mlMtxRotPitch','mlMtxRotYaw','mlMtxRotRoll',
                             'mlMtxScale_xyz','mlMtxTranslate','func_802515D4'],
        'src/core2/code_BE2C0.c': ['func_80345274','vec4f_isZero','func_80345A44','func_80345CD4'],
    }
    for path, names in files.items():
        code += ''.join(original_function(path,name) for name in names)
    code += r'''
typedef struct {float timer;} Animation;
typedef struct {Animation *animation;float timer,duration;int playback_direction;} AnimCtrl;
float elapsed;
Animation *anctrl_getAnimPtr(AnimCtrl *c) {return c->animation;}
void anctrl_80286F90(AnimCtrl *c) {(void)c;} /* No cross-animation blend in fixture. */
float anim_getTimer(Animation *a) {return a->timer;}
void anim_setTimer(Animation *a,float t) {a->timer=t;}
float time_getDelta(void) {return elapsed;}
float anctrl_getDuration(AnimCtrl *c) {return c->duration;}
'''
    code += original_function('src/core2/anctrl.c','__anctrl_update_looped')
    code += r'''
float loop_time(float timer,float delta,float duration) {
    Animation a={.timer=timer}; AnimCtrl c={.animation=&a,.duration=duration,.playback_direction=1};
    elapsed=delta;__anctrl_update_looped(&c);return a.timer;
}
float evaluate(int first,int last,int channel,int count,uint16_t *words,int16_t *values,float time) {
    BKAnimationFileBin file={.unk0=first,.unk2=last};
    BKAnimationFileElement *e=calloc(1,sizeof(*e)+count*sizeof(*e->data));
    e->unk0_3=channel; e->data_count=count;
    for(int i=0;i<count;i++) {
        e->data[i].unk0_15=words[i]>>15;
        e->data[i].unk0_14=(words[i]>>14)&1;
        e->data[i].unk0_13=words[i]&0x3fff; e->data[i].unk2=values[i];
    }
    float result=animationfilebin_func_8033AC38(&file,e,time); free(e); return result;
}
float frame(float progress) {BKAnimationFileBin f={.unk0=0,.unk2=110};
    return animationfilebin_func_8033ABA0(&f,progress);}
float normalized(int frame) {BKAnimationFileBin f={.unk0=0,.unk2=110};
    return animationfilebin_func_8033AA10(&f,frame);}
void quaternion(float *angles,float *out) {func_80345CD4(out,angles);}
void bone_matrix(float *parent,float *pivot,float factor,float *trs,float *out) {
    float rotation[3][3]; mlMtxIdent(); memcpy(s_mtx_stack->m,parent,64);
    mlMtxTranslate(pivot[0]+factor*trs[7],pivot[1]+factor*trs[8],pivot[2]+factor*trs[9]);
    if (!vec4f_isZero(trs)) {func_80345274(trs,rotation);func_802515D4(rotation);}
    mlMtxScale_xyz(trs[4],trs[5],trs[6]);
    mlMtxTranslate(-pivot[0],-pivot[1],-pivot[2]); memcpy(out,s_mtx_stack->m,64);
}
'''
    (directory / 'reference.c').write_text(code)
    subprocess.run(['cc','-std=c99','-O0','-shared','-fPIC','-ffp-contract=off',
                    '-fno-fast-math','-fno-strict-aliasing','-fexcess-precision=standard',
                    str(directory/'reference.c'),str(directory/'sinf.c'),str(directory/'cosf.c'),
                    '-lm','-o',str(directory/'reference.so')],check=True,capture_output=True)
    lib = C.CDLL(str(directory/'reference.so'))
    lib.evaluate.argtypes=[C.c_int]*4+[C.POINTER(C.c_uint16),C.POINTER(C.c_int16),F]
    lib.evaluate.restype=F
    lib.frame.argtypes=[F];lib.frame.restype=F
    lib.normalized.argtypes=[C.c_int];lib.normalized.restype=F
    lib.loop_time.argtypes=[F,F,F];lib.loop_time.restype=F
    lib.quaternion.argtypes=[FP,FP]
    lib.bone_matrix.argtypes=[FP,FP,F,FP,FP]
    lib._temporary = temporary
    return lib


class IdleAnimation:
    def __init__(self):
        data=(ROOT/'assets/anim/006F.anim.bin').read_bytes()
        if hashlib.sha256(data).hexdigest()!=ANIMATION_SHA:
            raise ValueError('006F hash mismatch')
        self.first,self.last,count,pad=struct.unpack_from('>hhhH',data)
        self.channels=[]; offset=8
        for _ in range(count):
            packed,n=struct.unpack_from('>Hh',data,offset)
            keys=[struct.unpack_from('>Hh',data,offset+4+4*i) for i in range(n)]
            self.channels.append((packed>>4,packed&15,keys));offset+=4+4*n
        assert offset==len(data) and (self.first,self.last,pad)==(0,110,0)
        self.library=original_library()

    def channel_value(self, bone, channel, frame):
        keys=next(keys for b,c,keys in self.channels if (b,c)==(bone,channel))
        n=len(keys)
        return self.library.evaluate(self.first,self.last,channel,n,
                (C.c_uint16*n)(*(k for k,v in keys)),(C.c_int16*n)(*(v for k,v in keys)),frame)

    def transforms(self, time=CANONICAL_TIME):
        frame=self.library.frame(time)
        channels=[[0.,0.,0.,1.,1.,1.,0.,0.,0.] for _ in range(109)]
        for bone,channel,_ in self.channels:
            channels[bone][channel]=self.channel_value(bone,channel,frame)
        bones=[]
        for values in channels:
            q=(F*4)();self.library.quaternion((F*3)(*values[:3]),q)
            bones.append(tuple(q)+tuple(values[3:]))
        return bones,channels

    def matrices(self, bones):
        data=(ROOT/'assets/model/034D.model.bin').read_bytes()
        offset=struct.unpack_from('>I',data,24)[0]
        factor,count=struct.unpack_from('>fh',data,offset)
        matrices=[]
        identity=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        for i in range(count):
            x,y,z,bone,parent=struct.unpack_from('>3fhh',data,offset+8+16*i)
            assert parent<i and -1<=parent and 0<=bone<len(bones)
            out=(F*16)()
            self.library.bone_matrix((F*16)(*(identity if parent==-1 else matrices[parent])),
                                     (F*3)(x,y,z),factor,(F*10)(*bones[bone]),out)
            matrices.append(tuple(out))
        # Transpose Rare's stored row matrices for the independent traversal.
        return {i:tuple(tuple(m[c*4+r] for c in range(4)) for r in range(4))
                for i,m in enumerate(matrices)}


class QuantizedPoseReference(PoseReference):
    def push(self, location, matrix):
        # mlMtxApply -> core1_7F60_guMtxF2L: float32 * 65536, s32 truncation.
        fixed=tuple(tuple(int(f32(f32(v)*65536))/65536 for v in row) for row in matrix)
        super().push(location,fixed)


def idle_reference(time=CANONICAL_TIME):
    animation=IdleAnimation()
    bones,channels=animation.transforms(time)
    pose=QuantizedPoseReference((ROOT/'assets/model/034D.model.bin').read_bytes(),
                                bone_overrides=animation.matrices(bones)).run()
    return animation,bones,channels,pose


def transform_hash(bones):
    return hashlib.sha256(b''.join(struct.pack('>10f',*bone) for bone in bones)).hexdigest()


if __name__=='__main__':
    animation,bones,channels,pose=idle_reference()
    print(json.dumps(dict(time=CANONICAL_TIME,animation_sha=ANIMATION_SHA,
                         bone_hash=transform_hash(bones),bones=bones,channels=channels,
                         summary=pose.summary(),loads=pose.loads),indent=2))
