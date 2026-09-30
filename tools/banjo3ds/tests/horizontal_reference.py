"""Independent M4.7B reference. No production Banjo3DS imports.

Compile ORIGINAL decomp functions + libultra trig in a temporary host library.
Only adapters stub out terrain (flat), gravity (irrelevant to XZ), and global
state. Python drives the documented frame ordering, idle-entry delay and skid
fixture; this is not a general player-state/collision emulator. Hashes use >19f
per frame in FIELDS order. Arithmetic/contraction flags are part of the contract.

Run: python -B tools/banjo3ds/tests/horizontal_reference.py /tmp/golden.json
This does not regenerate checked-in goldens implicitly during tests.
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
import sys
import tempfile

from idle_animation_reference import ROOT, original_function

F = C.c_float
FP = C.POINTER(F)
f = lambda x: F(x).value
FLAGS = ['-std=c99', '-ffp-contract=off', '-fno-fast-math',
         '-fexcess-precision=standard', '-fno-strict-aliasing']
FIELDS = ('magnitude desired_yaw target_speed target_x target_z velocity_x velocity_z '
          'candidate_x candidate_z accepted_x accepted_z ideal_yaw visible_yaw heading '
          'physics_speed accepted_speed position_x position_z path_length').split()
SOURCES = ['src/core1/joy.c', 'src/core1/ml.c', 'include/math.h',
           'src/core2/bastick.c', 'src/core2/ba/physics.c', 'src/core2/yaw.c',
           'src/core2/bs/walk.c', 'src/core2/bs/stand.c', 'src/core2/bs/turn.c',
           'src/core2/bs/jump.c', 'src/core2/bsmethods.c', 'src/core2/anctrl.c',
           'src/core2/commonParticle.c', 'lib/ultralib/src/gu/sinf.c',
           'lib/ultralib/src/gu/cosf.c']

@functools.lru_cache(maxsize=2)
def library(opt='-O0'):
    tmp = tempfile.TemporaryDirectory(prefix='banjo-horizontal-reference-')
    directory = Path(tmp.name)
    # Preserve original trig constants by value, independent of host endianness.
    for name, alias in [('sinf', 'fsin'), ('cosf', 'fcos')]:
        text = (ROOT / f'lib/ultralib/src/gu/{name}.c').read_text()
        text = re.sub(r'^#(?:include|pragma|define).*$', '', text, flags=re.M)
        text = re.sub(r'\{(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)\}',
            lambda m: '{.d=' + struct.unpack('>d', struct.pack('>II', int(m[1],16), int(m[2],16)))[0].hex() + '}', text)
        prefix = ('#include <math.h>\n#include <stdint.h>\n'
                  'typedef union {double d;} du;\ntypedef union {uint32_t i;float f;} fu;\n'
                  '#define ROUND(d) (int)(((d)>=0.0)?((d)+0.5):((d)-0.5))\n'
                  '#define ABS(x) ((x)<0?-(x):(x))\n#define __libm_qnan_f NAN\n'
                  f'#define {alias} ref_{name}\n')
        (directory / f'{name}.c').write_text(prefix + text)
    code = r'''
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef float f32; typedef int32_t s32;
#define BAD_DTOR (3.141592654/180.0)
#define ANTI_TAMPER 0
#define mlAbsF fabsf
float ref_sinf(float); float ref_cosf(float);
#define sinf ref_sinf
#define cosf ref_cosf
#define LENGTH_SQ_VEC3F(v) ((v)[0]*(v)[0]+(v)[1]*(v)[1]+(v)[2]*(v)[2])
float current_dt, current_coefficient;
float time_getDelta(void) {return current_dt;}
float func_8029CED0(void) {return current_coefficient;}
int func_80294548(void) {return 0;} /* flat unobstructed reference */
void func_80294480(float *v) {v[0]=v[2]=0;v[1]=1;}
float get_slope_timer(void) {return 0;}
int player_isActive(void) {return 1;}
float s_player_velocity[3], baphysics_target_velocity[3], s_delta_position[3], s_next_position[3];
float baphysics_target_horizontal_velocity, baphysics_target_yaw;
float s_gravity=0, s_terminal_velocity=-4000;
float yaw_deg, yawIdeal_deg;
struct {float distance, zone_position, zone_markers[5];int zone;} bastick;
int player_isOnDangerousGround(void) {return 0;}
float bastick_distance(void) {return bastick.distance;}
float bastick_getZonePosition(void) {return bastick.zone_position;}
int bastick_getZone(void) {return bastick.zone;}
void baphysics_set_target_horizontal_velocity(float v) {baphysics_target_horizontal_velocity=v;}
'''
    macros = (ROOT / 'include/math.h').read_text()
    for name in ('TUPLE_COPY', 'TUPLE_DIFF', 'TUPLE_SCALE', 'TUPLE_SCALE_COPY', 'TUPLE_DOT_PRODUCT'):
        lines = macros[macros.index('#define '+name+'('):].splitlines()
        for line in lines:
            code += line + '\n'
            if not line.endswith('\\'): break
    ml_names = ('ml_vec3f_copy', 'ml_vec3f_diff', 'ml_vec3f_scale', 'ml_vec3f_scale_copy',
                'ml_vec3f_normalize_copy', 'ml_vec3f_dot_product', 'ml_map_f',
                'ml_interpolate_f', 'ml_clamp_f', 'mlDiffDegF', 'func_80256D0C')
    for name in ml_names:
        code += original_function('src/core1/ml.c', name)
    walk = (ROOT / 'src/core2/bs/walk.c').read_text()
    for declaration in re.findall(r'^f32 bsWalk\w+ =[^;]+;', walk, re.M):
        code += declaration + '\n'
    for path, names in (
        ('src/core1/joy.c', ('controller_clampAndNormaliseJoyAxis',)),
        ('src/core2/bastick.c', ('bastick_calculateZonePosition', 'bastick_updateZone')),
        ('src/core2/bs/walk.c', ('func_802B6D00',)),
        ('src/core2/ba/physics.c', ('__baphysics_update_normal',)),
        ('src/core2/yaw.c', ('__yaw_update_limited',))):
        for name in names: code += original_function(path, name)
    code += r'''
float ref_axis(int raw,int maximum) {return controller_clampAndNormaliseJoyAxis(raw,7,maximum);}
float ref_target(float magnitude) {
    const float markers[5]={.12f,.2f,.5f,.75f,1.f};
    memcpy(bastick.zone_markers,markers,sizeof(markers));
    bastick.distance=magnitude>1.0?1.f:magnitude;
    bastick_updateZone();func_802B6D00();return baphysics_target_horizontal_velocity;
}
float ref_magnitude(float x,float y) {float m=sqrtf(x*x+y*y);if(m>1.0)m=1;return m;}
float ref_yaw(float visible,float ideal,float dt) {
    yaw_deg=visible;yawIdeal_deg=ideal;current_dt=dt;
    __yaw_update_limited(700.f,7.5f);return yaw_deg;
}
int ref_skid(float ideal,float visible,float speed) {return 135.f<fabsf(mlDiffDegF(ideal,visible)) && 125.f<speed;}
float ref_skid_target(float phase,float start) {return ml_map_f(phase,.18f,1.f,start,0.f);}
void ref_vector(float speed,float heading,float *out) {
    float y;func_80256D0C(0,heading,0,0,speed,out,&y,out+1);
}
void ref_response(float speed,float heading,float vx,float vz,float dt,float c,float *out) {
    baphysics_target_horizontal_velocity=speed;baphysics_target_yaw=heading;
    s_player_velocity[0]=vx;s_player_velocity[1]=0;s_player_velocity[2]=vz;
    memset(s_next_position,0,sizeof(s_next_position));current_dt=dt;current_coefficient=c;
    __baphysics_update_normal();
    out[0]=baphysics_target_velocity[0];out[1]=baphysics_target_velocity[2];
    out[2]=s_player_velocity[0];out[3]=s_player_velocity[2];
    out[4]=s_delta_position[0];out[5]=s_delta_position[2];
}
'''
    (directory / 'reference.c').write_text(code)
    out = directory / 'reference.so'
    subprocess.run(['cc', *FLAGS, opt, '-shared', '-fPIC', str(directory/'reference.c'),
                    str(directory/'sinf.c'), str(directory/'cosf.c'), '-lm', '-o', str(out)], check=True)
    lib = C.CDLL(str(out));lib.temporary = tmp
    for name, args, result in (
        ('axis', [C.c_int,C.c_int], F), ('target',[F],F), ('magnitude',[F,F],F),
        ('yaw',[F,F,F],F), ('skid',[F,F,F],C.c_int), ('skid_target',[F,F],F),
        ('vector',[F,F,FP],None), ('response',[F,F,F,F,F,F,FP],None)):
        fn = getattr(lib,'ref_'+name);fn.argtypes=args;fn.restype=result
    return lib


def norm(x,z):
    return f(math.sqrt(f(f(x*x)+f(z*z))))


class Reference:
    def __init__(self, opt='-O0'):
        self.lib=library(opt)
        self.m=self.desired=self.speed=self.ideal=self.visible=self.heading=0.
        self.target=[0.,0.];self.velocity=[0.,0.];self.candidate=[0.,0.];self.accepted=[0.,0.]

    def intent(self,m,yaw):
        self.m,self.desired=f(m),f(yaw%360)
        self.speed=self.lib.ref_target(self.m)

    def takeoff(self):
        if self.m!=0:self.ideal=self.desired
        self.heading=self.ideal;self.speed=self.lib.ref_target(self.m)
        out=(F*2)();self.lib.ref_vector(self.speed,self.heading,out)
        self.target=list(out);self.velocity=list(out)

    def step(self,mode,dt):
        if mode==0:self.heading=self.ideal
        elif mode==1 and self.m>0:self.heading=self.desired
        out=(F*6)()
        self.lib.ref_response(self.speed,self.heading,*self.velocity,dt,.07 if mode==1 else .29,out)
        self.target=list(out[:2]);self.velocity=list(out[2:4]);self.candidate=list(out[4:6]);self.accepted=[0.,0.]
        if mode==0 and self.m!=0:self.ideal=self.desired
        if mode!=2:self.visible=self.lib.ref_yaw(self.visible,self.ideal,dt)

    def snapshot(self,dt):
        return [self.m,self.desired,self.speed,*self.target,*self.velocity,*self.candidate,
                *self.accepted,self.ideal,self.visible,self.heading,norm(*self.velocity),
                f(norm(*self.accepted)/dt) if dt>0 else 0.]


CASES = ('start_stop','constant_25','constant_50','constant_75','constant_100',
         'ground_90','ground_180_skid','jump_rest_neutral','jump_rest_full',
         'jump_steady_full','jump_neutral_before','jump_release_after','air_90','air_180')


def trace(name,opt='-O0'):
    """Yield commands and independent expected snapshots (no production calls).

    Geometry-free accepted displacement equals candidate in these fixtures.
    Skid is TEST DRIVER state only; caller eligibility WALK/FAST is assumed.
    Ground traces model the stand entry delay but not unrelated gameplay events.
    Air traces stop at 1 s (hold-A learned, level floor landing is later).
    """
    r=Reference(opt);dt=f(1/60);position=[0.,0.];path=0.
    steady=name.startswith('ground_') or name in ('jump_steady_full','jump_neutral_before','jump_release_after','air_90','air_180')
    if steady:r.velocity=[0.,500.]
    count=180 if name=='start_stop' else 120 if name.startswith('constant_') else 60
    phase=0.;skid_start=0.;skid=False;stopped=False
    for i in range(count):
        m=1.;yaw=0.;mode=0
        if name.startswith('constant_'):m=int(name.split('_')[1])/100
        if name=='start_stop' and i>=120:m=0.
        if name=='ground_90':yaw=90.
        if name=='ground_180_skid':yaw=180.
        airborne=name.startswith('jump_') or name.startswith('air_')
        if airborne:
            mode=1
            if name in ('jump_rest_neutral','jump_neutral_before') or (name=='jump_release_after' and i>0):m=0.
            if i>0 and name=='air_90':yaw=90.
            if i>0 and name=='air_180':yaw=180.
        r.intent(m,yaw)
        command={'m':m,'yaw':yaw,'mode':mode,'takeoff':airborne and i==0}
        if command['takeoff']:r.takeoff()
        if not airborne and not steady and i==0:
            r.speed=0.;command['idle_entry']=True
        if name=='ground_180_skid':
            if skid:
                command['skid_phase']=phase;command['skid_start']=skid_start
                r.speed=r.lib.ref_skid_target(phase,skid_start)
                if stopped:
                    skid=False;r.visible=f((r.visible-180)%360);command['skid_exit']=True
                else:mode=2
            elif r.lib.ref_skid(r.ideal,r.visible,norm(*r.velocity)):
                skid=True;phase=0.;stopped=False;skid_start=norm(*r.velocity);mode=2
                command['skid_enter']=True
            command['mode']=mode
        r.step(mode,dt)
        r.accepted=list(r.candidate)
        position=[f(p+d) for p,d in zip(position,r.accepted)]
        path=f(path+norm(*r.accepted))
        if skid:
            phase=f(phase+f(dt/f(.3)))
            if phase>.999999:phase=f(.9999989867210388);stopped=True
        yield command, r.snapshot(dt)+position+[path]


def golden(opt='-O0'):
    result={'packing':'>19f per frame, no padding','fields':FIELDS,'dt':f(1/60),
            'sources':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},'cases':{}}
    for name in CASES:
        rows=[row for _,row in trace(name,opt)]
        data=b''.join(struct.pack('>19f',*row) for row in rows)
        result['cases'][name]={'frames':len(rows),'sha256':hashlib.sha256(data).hexdigest(),
            'checkpoints':{str(i):rows[i-1] for i in (6,15,30,60,120,126,135,150,180) if i<=len(rows)}}
    return result


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: horizontal_reference.py OUTPUT.json')
    Path(sys.argv[1]).write_text(json.dumps(golden(),indent=2)+'\n')
