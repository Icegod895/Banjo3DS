"""Host-only input plumbing on real current player-runtime trajectories.
A test observer captures candidates BEFORE movement floor/swept landing. This
is NOT Rare's volume solver cadence: explicitly one observed candidate per tick.
Both independent original suppliers and production suppliers receive that same
schedule. No dynamic collision provider is registered in either path.
"""
import ctypes as C
import hashlib
from pathlib import Path
import subprocess
import tempfile
from segment_reference import ROOT, FLAGS
import segment_reference
import floor_state_reference as floor_ref
from floor_state_corpus import canonical
from test_floor_state import State as FloorState
import test_camera as cam
import test_jump_runtime as runtime
from test_jump import Motion, arrays
from test_movement import Actor, Vertex, Triangle
from tools.banjo3ds.floor_collision import scene_collision

F=C.c_float

def player_library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='floor-player-observer-');p=Path(tmp.name)
    source=(ROOT/'tools/banjo3ds/jump/jump.c').read_text()
    source=source.replace('#include "jump.h"','#include "jump.h"\nfloat floor_test_candidate[3];')
    hook='if(movementFollowFloorOverlay(v,t,n,s->actor.x,s->actor.y,s->actor.z,x,z,&height,overlay)) {'
    assert source.count(hook)==1
    source=source.replace(hook,
        'floor_test_candidate[0]=x;floor_test_candidate[1]=s->actor.y;floor_test_candidate[2]=z;\n                    '+hook)
    source=source.replace('float hit[3];\n    if(banjo_jump_sweep',
        'memcpy(floor_test_candidate,end,12);\n    float hit[3];\n    if(banjo_jump_sweep')
    (p/'jump.c').write_text(source)
    sources=['platform/3ds/source/player_runtime.c','platform/3ds/source/movement.c',
        'tools/banjo3ds/camera_first_person/first_person.c',
        'tools/banjo3ds/pose/pose.c','tools/banjo3ds/gait/gait.c','tools/banjo3ds/gait/gait_motion.c',
        'tools/banjo3ds/horizontal/horizontal.c','tools/banjo3ds/jump/jump_animation.c']
    subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
       *['-I'+str(ROOT/d) for d in ('platform/3ds/source','tools/banjo3ds/jump','tools/banjo3ds/pose','tools/banjo3ds/gait')],
       *[str(ROOT/s) for s in sources],str(p/'jump.c'),'-lm','-o',str(p/'lib.so')],check=True)
    lib=C.CDLL(str(p/'lib.so'));lib._tmp=tmp
    lib.playerRuntimeMove.argtypes=[C.POINTER(runtime.Player),F,F,F,F,C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
    return lib

def traces(opt):
    lib=player_library(opt);v,t=arrays(*scene_collision([ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0')]))
    result={}
    for name,z,y,speed,jump in (
        ('node_stationary',0,1800,0,-1),('node_walk',0,1800,54,-1),
        ('node_jump_landing',0,1800,0,10),('node_exit_jump_landing',0,1800,156,10),
        ('free_walk',-1000,1625.77783203125,54,-1),('free_jump_landing',-1000,1625.77783203125,-156,10)):
        p=runtime.Player(motion=Motion(actor=Actor(0,y,z,0),grounded=True));rows=[]
        for i in range(240):
            lib.playerRuntimeMove(C.byref(p),speed if name=='free_walk' else 0,0 if name=='free_walk' else speed,0,F(1/60),i==jump,False,v,t,len(t))
            a=p.motion.actor;cand=list((F*3).in_dll(lib,'floor_test_candidate'))
            rows.append(dict(candidate=cand,player=[a.x,a.y,a.z],yaw=a.yaw,stable=bool(p.motion.grounded),dt=F(1/60).value,vi=1,parity=i&1))
        result[name]=rows
    lib._tmp.cleanup()
    return result

def compare(test, floor_lib, models, opt):
    # Reuse existing camera test wiring, not its input/golden values.
    class Harness(cam.CameraTests):pass
    Harness.setUpClass()
    try:
        checker=Harness();camera_lib=Harness.libs[0 if opt=='-O0' else 1]
        oracle=cam.library(opt);fr=floor_ref.library(opt);segment_reference.load_real(fr)
        results={}
        for name,rows in traces(opt).items():
            first=rows[0];position=first['player'];eye=[position[0],position[1]+375,position[2]-850];rot=[340,180,0]
            m=cam.Math();camera_lib.banjo_camera_math_init(C.byref(m));s=cam.State()
            cmd=dict(first,floor=position[1],under=position[1]);inp=cam.make_input(cmd)
            camera_lib.banjo_camera_init(C.byref(s),C.byref(m),C.byref(inp),(F*3)(*eye),(F*3)(*rot))
            records,z=cam.setup();raw=[v for r in records for v in r[1:]]
            oracle.ref_setup((C.c_int*len(raw))(*raw),len(records),(F*12)(*z[:12]));oracle.ref_init((F*3)(*position),position[1],(F*3)(*eye),(F*3)(*rot))
            fs=FloorState();floor_lib.bq_floor_init(C.byref(fs));fr.floor_ref_init();stream=[];modes=[];air=land=0
            previous=True
            for i,row in enumerate(rows):
                candidate=(F*3)(*row['candidate'])
                fr.floor_ref_step(candidate,56,0x400000,row['parity'])
                test.assertEqual(floor_lib.bq_floor_update(C.byref(fs),*[C.byref(x) for x in models],candidate,56,0x400000,row['parity']),1)
                test.assertEqual(bytes(fs),floor_ref.snapshot(fr),(name,i))
                under=F();hit=C.c_int();original_under=fr.ref_terrain(s.position,C.byref(hit))
                test.assertEqual(floor_lib.bq_camera_terrain(*[C.byref(x) for x in models],s.position,C.byref(under)),hit.value)
                test.assertEqual(bytes(under),bytes(F(original_under)))
                cmd=dict(row,floor=fs.height,under=under.value)
                checker.step(camera_lib,oracle,s,m,cmd,(name,i))
                values=cam.values(s);stream.append(cam.pack(*cam.snapshot(oracle))+canonical(floor_ref.snapshot(fr)))
                modes.append((s.state,s.node));air+=not row['stable'];land+=row['stable'] and not previous;previous=row['stable']
            results[name]=dict(frames=len(rows),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),modes=sorted(set(modes)),air=air,landings=land)
        test.assertIn((17,32),results['node_stationary']['modes'])
        test.assertIn((11,-1),results['node_exit_jump_landing']['modes'])
        test.assertGreater(results['node_jump_landing']['landings'],0)
        test.assertGreater(results['free_jump_landing']['landings'],0)
        test.assertEqual(results['free_walk']['modes'],[(11,-1)])
        test.assertEqual(results['free_jump_landing']['modes'],[(11,-1)])
        return results
    finally:Harness.doClassCleanups()
