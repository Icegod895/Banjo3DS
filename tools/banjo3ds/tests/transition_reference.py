"""Test-only 006F <-> 0003 reference; no production imports.

Original blend, acos lookup and controller functions are compiled unchanged
arithmetically. Checked reads include the two zero words following the declared lookup
table, verified against original decompressed NTSC 1.0 ROM bytes. Existing original-C animation and
independent geo/RSP references supply poses and geometry.
"""
import ctypes as C
import functools
import hashlib
import re
import struct
import subprocess
import tempfile
from pathlib import Path

from idle_animation_reference import (F, ROOT, IdleAnimation, original_function,
                                      original_library, QuantizedPoseReference)
from walk_pose_reference import WalkAnimation


def pack(rows, width):
    return b''.join(struct.pack('>'+str(width)+'f', *row) for row in rows)


def digest(rows, width):
    return hashlib.sha256(pack(rows, width)).hexdigest()


@functools.lru_cache(maxsize=2)
def blend_library(optimization='-O0'):
    tmp = tempfile.TemporaryDirectory(prefix='banjo-transition-reference-')
    directory = Path(tmp.name)
    text = (ROOT/'src/core1/ml.c').read_text()
    table = re.search(r'f32 sLookupTableAcosDegrees\[90\] = \{.*?\};', text, re.S)[0]
    code = r'''
#include <stdbool.h>
#include <stdint.h>
#include <math.h>
#include <string.h>
typedef float f32; typedef int32_t s32;
typedef struct {float unk0[4],scale[3],unk1C[3];} BoneTransform;
typedef struct {BoneTransform *ptr;int count;} BoneTransformList;
#define TRUE 1
#define BAD_PI 3.141592654
#define LENGTH_SQ_VEC4F(v) (v[0]*v[0]+v[1]*v[1]+v[2]*v[2]+v[3]*v[3])
float reference_sinf(float);
#define sinf reference_sinf
static int lookup_error, lookup_max=-1, lookup_count;
''' + table + r'''
float checked_table(int index) {
    ++lookup_count;
    if(index>lookup_max)lookup_max=index;
    if(index<0 || index>=92) {lookup_error=1;return NAN;}
    /* Original ROM 0xf52654..0xf5265b: two zero words after 90 floats.
     * Model the observed memory safely, rather than host C array overread. */
    return index<90?sLookupTableAcosDegrees[index]:0.0f;
}
'''
    # Instrument memory reads only; comparisons, constants and arithmetic stay original.
    acos = original_function('src/core1/ml.c','ml_acosf_deg')
    acos = re.sub(r'table\[(idx|upperIdx|lowerIdx)\]', r'checked_table(\1)', acos)
    acos = acos.replace('f32 *table = sLookupTableAcosDegrees;', '')
    code += acos + r'''
float lookup_probe(float x,int *stats) {
    lookup_error=0;lookup_max=-1;lookup_count=0;
    float result=ml_acosf_deg(x);
    stats[0]=lookup_max;stats[1]=lookup_count;
    return lookup_error?NAN:result;
}
'''
    for name in ('func_80345650','func_803458E4'):
        code += original_function('src/core2/code_BE2C0.c',name)
    blend = original_function('src/core2/code_B3580.c','boneTransformList_interpolate')
    # Correct the decompilation's struct-pointer argument types, not its math.
    blend = blend.replace('func_803458E4(i_xform, start_xform, end_xform, arg3)',
                          'func_803458E4(i_xform->unk0, start_xform->unk0, end_xform->unk0, arg3)')
    code += blend + r'''
int blend_raw(float *out,float *start,float *end,float factor,int *stats) {
    BoneTransform a[109],b[109],o[109];
    memcpy(a,start,sizeof(a));memcpy(b,end,sizeof(b));
    BoneTransformList aa={a,109},bb={b,109},oo={o,109};
    lookup_error=0;lookup_max=-1;lookup_count=0;
    boneTransformList_interpolate(&oo,&aa,&bb,factor);
    memcpy(out,o,sizeof(o));stats[0]=lookup_max;stats[1]=lookup_count;
    return !lookup_error;
}
typedef struct {float timer,duration;} Animation;
typedef struct {Animation *animation;float timer,duration,transition;int playback_direction,smooth_transition;} AnimCtrl;
static float elapsed;
Animation *anctrl_getAnimPtr(AnimCtrl *c) {return c->animation;}
float anim_getTimer(Animation *a) {return a->timer;}
void anim_setTimer(Animation *a,float t) {a->timer=t;}
float anim_getDuration(Animation *a) {return a->duration;}
void anim_setDuration(Animation *a,float t) {a->duration=t;}
float anctrl_getDuration(AnimCtrl *c) {return c->duration;}
float anctrl_getTransistionDuration(AnimCtrl *c) {return c->transition;}
float time_getDelta(void) {return elapsed;}
float ml_min_f(float a,float b) {return a<b?a:b;}
'''
    for name in ('anctrl_80286F90','__anctrl_update_looped'):
        code += original_function('src/core2/anctrl.c',name)
    code += r'''
void advance(float *phase,float *factor,float dt,float duration) {
    Animation a={*phase,*factor};
    AnimCtrl c={.animation=&a,.duration=duration,.transition=0.2f,
                .playback_direction=1,.smooth_transition=1};
    elapsed=dt;__anctrl_update_looped(&c);*phase=a.timer;*factor=a.duration;
}
'''
    (directory/'blend.c').write_text(code)
    original = original_library()
    subprocess.run(['cc','-std=c99',optimization,'-shared','-fPIC','-ffp-contract=off',
                    '-fno-fast-math','-fexcess-precision=standard',
                    str(directory/'blend.c'),str(Path(original._temporary.name)/'sinf.c'),
                    '-lm','-o',str(directory/'blend.so')],check=True,capture_output=True)
    lib = C.CDLL(str(directory/'blend.so'))
    fp = C.POINTER(F)
    lib.blend_raw.argtypes = [fp,fp,fp,F,C.POINTER(C.c_int)]
    lib.blend_raw.restype = C.c_int
    lib.advance.argtypes = [fp,fp,F,F]
    lib.lookup_probe.argtypes=[F,C.POINTER(C.c_int)]
    lib.lookup_probe.restype=F
    lib._temporary = tmp
    return lib


def raw_blend(source, destination, factor, optimization='-O0'):
    out=(F*(109*10))();stats=(C.c_int*2)()
    start=(F*(109*10))(*(v for b in source for v in b))
    end=(F*(109*10))(*(v for b in destination for v in b))
    if not blend_library(optimization).blend_raw(out,start,end,factor,stats):
        raise ValueError(f'Original acos lookup outside verified ROM lookup memory: {tuple(stats)}')
    return tuple(tuple(out[10*i+j] for j in range(10)) for i in range(109)),tuple(stats)


def blend_pose(source, destination, factor, optimization='-O0'):
    if not 0 <= factor <= 1:
        raise ValueError('Transition factor outside [0,1]')
    # Explicit minimal-port endpoint contract. At 1 Rare itself bypasses blend
    # (code_2240.c:87-92). At 0 preserve the frozen bytes, including signed zero.
    if factor == 0:return tuple(tuple(b) for b in source),(-1,0)
    if factor == 1:return tuple(tuple(b) for b in destination),(-1,0)
    return raw_blend(source,destination,factor,optimization)


def pose_summary(bones):
    matrices = IdleAnimation().matrices(bones)
    pose = QuantizedPoseReference((ROOT/'assets/model/034D.model.bin').read_bytes(),
                                  bone_overrides=matrices).run()
    assert (len(pose.calls),len(pose.loads),len(pose.triangles)) == (49,723,695)
    return dict(
        bones=digest(bones,10),
        matrices=digest((tuple(matrices[i][c][r] for r in range(4) for c in range(4))
                         for i in range(60)),16),
        loads=digest((e['xyz'] for e in pose.loads),3),
        corners=digest((pose.loads[i]['xyz'] for tri in pose.triangles for i in tri),3),
        bounds=pose.summary()['bounds'])


class Transition:
    """Frozen source VALUES; no source clip/time exists to advance or evaluate.

    Destination starts at phase zero, clip duration .6 (0003) or 5.5 (006F).
    Both loop in this minimal-port fixture; no original stand-event sequence.
    """
    def __init__(self, source, destination, optimization='-O0'):
        self.source=tuple(tuple(F(v).value for v in b) for b in source)
        self.animation={'006F':IdleAnimation,'0003':WalkAnimation}[destination]()
        self.duration={'006F':5.5,'0003':.6}[destination]
        self.phase=0.;self.factor=0.;self.optimization=optimization

    def step(self,dt):
        if not 0 <= dt <= .05:raise ValueError('Diagnostic frame dt outside [0,.05]')
        phase,factor=F(self.phase),F(self.factor)
        blend_library(self.optimization).advance(C.byref(phase),C.byref(factor),dt,self.duration)
        self.phase,self.factor=phase.value,factor.value
        return self.sample()

    def sample(self):
        destination,_=self.animation.transforms(self.phase)
        bones,stats=blend_pose(self.source,destination,self.factor,self.optimization)
        return bones,dict(phase=self.phase,factor=self.factor,
                          source_hash=digest(self.source,10),destination_hash=digest(destination,10),
                          lookup_max=stats[0],lookup_reads=stats[1],**pose_summary(bones))


def scenarios(optimization='-O0'):
    idle,_=IdleAnimation().transforms(.37)
    walk,_=WalkAnimation().transforms(.625)
    idle_tail,_=IdleAnimation().transforms(.625)
    result={}
    for name,source,destination in [('idle_to_walk',idle,'0003'),('walk_to_idle',walk,'006F'),
                                    ('idle_tail_to_walk',idle_tail,'0003')]:
        t=Transition(source,destination,optimization)
        result[name]=[t.sample()[1]]+[t.step(.025)[1] for _ in range(8)]
    first=Transition(idle,'0003',optimization)
    for _ in range(3):blended,interrupt=first.step(.025)
    second=Transition(blended,'006F',optimization)
    result['interruption']=dict(at=interrupt,return_to_idle=[second.sample()[1]]+
                                [second.step(.025)[1] for _ in range(8)])
    return result
