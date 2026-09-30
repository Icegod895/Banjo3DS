"""Independent scheduling + observed CURRENT runtime, not a Rare solver port.
Reference clock/events are Python; original floor C evaluates supplied schedules.
Final-position replay is an explicitly COUNTERFACTUAL comparison, never Rare.
"""
import ctypes as C
import functools
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import floor_camera_inputs as old
import floor_state_reference as reference
from floor_state_corpus import canonical
from segment_reference import ROOT, FLAGS, load_real
from test_jump import Motion,arrays
from test_jump_runtime import Player
from test_movement import Actor,Vertex,Triangle
from tools.banjo3ds.floor_collision import scene_collision
F=C.c_float

@functools.lru_cache(None)
def observer(opt):
    # Existing observer's original source copy; additional count/reset observers
    # are inserted into TEMPORARY files only, never into live player sources.
    base=old.player_library(opt);tmp=tempfile.TemporaryDirectory(prefix='bridge-observer-');p=Path(tmp.name)
    jump=(Path(base._tmp.name)/'jump.c').read_text();base._tmp.cleanup()
    jump=jump.replace('float floor_test_candidate[3];','float floor_test_candidate[3];unsigned floor_test_count;')
    jump=jump.replace('floor_test_candidate[0]=x;', '++floor_test_count;floor_test_candidate[0]=x;')
    jump=jump.replace('memcpy(floor_test_candidate,end,12);','++floor_test_count;memcpy(floor_test_candidate,end,12);')
    (p/'jump.c').write_text(jump)
    player=(ROOT/'platform/3ds/source/player_runtime.c').read_text().replace('#include <string.h>','#include <string.h>\nextern unsigned floor_test_count;')
    player=player.replace('if(!s || !isfinite(dt)', 'floor_test_count=0;\n    if(!s || !isfinite(dt)',1)
    (p/'player_runtime.c').write_text(player)
    sources=['platform/3ds/source/movement.c','tools/banjo3ds/pose/pose.c','tools/banjo3ds/gait/gait.c',
        'tools/banjo3ds/gait/gait_motion.c','tools/banjo3ds/horizontal/horizontal.c','tools/banjo3ds/jump/jump_animation.c']
    subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
       *['-I'+str(ROOT/d) for d in ('platform/3ds/source','tools/banjo3ds/jump','tools/banjo3ds/pose','tools/banjo3ds/gait')],
       *[str(ROOT/s) for s in sources],str(p/'jump.c'),str(p/'player_runtime.c'),'-lm','-o',str(p/'lib.so')],check=True)
    lib=C.CDLL(str(p/'lib.so'));lib._tmp=tmp
    lib.playerRuntimeMove.argtypes=[C.POINTER(Player),F,F,F,F,C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
    return lib

@functools.lru_cache(None)
def trajectories(opt):
    lib=observer(opt);v,t=arrays(*scene_collision([ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0')]))
    result={}
    for name,z,y,speed,jump in (
        ('node_stationary',0,1800,0,-1),('node_walk',0,1800,54,-1),
        ('node_jump_landing',0,1800,0,10),('node_exit_jump_landing',0,1800,156,10),
        ('free_walk',-1000,1625.77783203125,54,-1),('free_jump_landing',-1000,1625.77783203125,-156,10),
        ('rejected_ground',0,1800,156,-1),('orbit_ground',0,1800,156,-1),
        ('orbit_air',0,1800,156,10),('void_recovery',0,1800,0,-1),
        ('reinitialize',0,1800,54,-1),('slope_down',0,1800,0,-1),
        ('slope_up',0,1800,0,-1),('zero_dt',0,1800,0,-1),
        ('roundtrip',0,1800,156,-1)):
        p=Player(motion=Motion(actor=Actor(0,y,z,0),grounded=True));rows=[]
        if name.startswith('slope_'):
            p.motion.actor=Actor(-2094,133.333344,-383.666656,135 if name=='slope_down' else 315)
        for i in range(600 if name=='roundtrip' else 240):
            x= speed if name=='free_walk' else 0;yy=0 if name=='free_walk' else speed;heading=0;dt=F(1/60).value
            camera=name in ('orbit_air','orbit_ground') and i>=20
            if name.startswith('slope_'):yy=156;heading=-135 if name=='slope_down' else -315
            if name=='zero_dt' and i%3==0:dt=0
            if name=='roundtrip':
                # Full-speed northward escape/return, real movement (no teleports).
                yy=-156 if i<120 else 156
            if name=='void_recovery' and i==20:
                # Explicit fault injection: current diagnostic recovery, real mesh.
                p.motion.actor=Actor(9000,-1000,9000,0);p.motion.grounded=False;p.motion.vy=-1000
            before=[p.motion.actor.x,p.motion.actor.y,p.motion.actor.z]
            lib.playerRuntimeMove(C.byref(p),x,yy,heading,dt,i==jump,camera,v,t,len(t))
            a=p.motion.actor;n=C.c_uint.in_dll(lib,'floor_test_count').value;assert n in (0,1)
            cand=list((F*3).in_dll(lib,'floor_test_candidate')) if n else None
            row=dict(candidate=cand,player=[a.x,a.y,a.z],before=before,yaw=a.yaw,stable=bool(p.motion.grounded),
                events=p.events,physics_speed=p.metrics.physics_speed,dt=dt,vi=1,parity=i&1,reinit=name=='reinitialize' and i==20,camera=camera)
            rows.append(row)
        result[name]=rows
    return result

def schedule(row,final=False):
    """One proposal; no post-accept/reject replay. Recovery is a separate event."""
    out=[]
    if row.get('reinit'):out.append(('reinit',None))
    if row['candidate'] is not None:out.append(('candidate',row['player'] if final else row['candidate']))
    if row.get('events',0)&4:
        out.extend([('reinit',None),('candidate',row['player'])])
    return out

def states(rows,opt,final=False):
    lib=reference.library(opt);load_real(lib);lib.floor_ref_init();out=[]
    for frame,row in enumerate(rows):
        for event,p in schedule(row,final):
            if event=='reinit':lib.floor_ref_reinit()
            else:lib.floor_ref_step((F*3)(*p),56,0x400000,frame&1)
        out.append(reference.snapshot(lib))
    return out
