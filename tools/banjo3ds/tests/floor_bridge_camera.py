"""Complete bounded camera chain and explicitly non-Rare final-replay comparison."""
import ctypes as C
import hashlib
import math
import struct
import test_camera as cam
import floor_bridge_reference as ref
import floor_state_reference as fr
from floor_state_corpus import canonical
from segment_reference import load_real
F=C.c_float
REQUIRED=('node_stationary','node_walk','node_jump_landing','node_exit_jump_landing','free_walk','free_jump_landing','roundtrip')

def height(s):return struct.unpack_from('=f',s,64)[0]
def fbase(player,y):
    # Original dynamic camera Fbase vertical rule, float32 intermediates.
    return F(player[1]-50 if F(y+130).value<player[1] else y+80).value

def compare(test,lib,models,opt):
    from test_floor_bridge import Bridge
    class Harness(cam.CameraTests):pass
    Harness.setUpClass()
    try:
        checker=Harness();cl=Harness.libs[0 if opt=='-O0' else 1];oracle=cam.library(opt)
        terrain=fr.library(opt);load_real(terrain);results={}
        records,z=cam.setup();raw=[v for r in records for v in r[1:]]
        for name,rows in ref.trajectories(opt).items():
            if name=='zero_dt':continue # no initial callback -> no publishable floor yet
            originals=ref.states(rows,opt);finals=ref.states(rows,opt,True)
            p=rows[0]['player'];eye=[p[0],p[1]+375,p[2]-850];rotation=[340,180,0]
            s=cam.State();alt=cam.State();m=cam.Math();cl.banjo_camera_math_init(C.byref(m))
            cmd=dict(rows[0],floor=p[1],under=p[1]);inp=cam.make_input(cmd)
            for cs in (s,alt):cl.banjo_camera_init(C.byref(cs),C.byref(m),C.byref(inp),(F*3)(*eye),(F*3)(*rotation))
            oracle.ref_setup((C.c_int*len(raw))(*raw),len(records),(F*12)(*z[:12]))
            oracle.ref_init((F*3)(*p),p[1],(F*3)(*eye),(F*3)(*rotation))
            b=Bridge();lib.bq_bridge_init(C.byref(b),0);stream=[];modes=[];unsupported=None
            metrics=dict(first_floor=None,max_floor=0.,first_fbase=None,max_fbase=0.,first_camera=None,max_camera_xyz=0.,max_camera_focus=0.)
            first_values=None;max_floor_values=None;previous_camera=list(s.position);max_camera_step=0.
            for frame,(row,want,other) in enumerate(zip(rows,originals,finals)):
                test.assertEqual(lib.bq_bridge_begin(C.byref(b)),1)
                for event,p in ref.schedule(row):
                    if event=='reinit':test.assertEqual(lib.bq_bridge_reinit(C.byref(b)),1)
                    else:test.assertEqual(lib.bq_bridge_candidate(C.byref(b),*[C.byref(x) for x in models],(F*3)(*p),b.ordinal),1)
                test.assertEqual(bytes(b.floor),want,(name,frame));lib.bq_bridge_end(C.byref(b))
                a_y,c_y=height(want),height(other);delta=abs(a_y-c_y)
                if delta and metrics['first_floor'] is None:
                    metrics['first_floor']=frame;first_values=dict(candidate=row['candidate'],accepted=row['player'],pre_floor=a_y,final_floor=c_y,events=row['events'])
                if delta>metrics['max_floor']:
                    max_floor_values=dict(frame=frame,candidate=row['candidate'],accepted=row['player'],pre_floor=a_y,final_floor=c_y)
                metrics['max_floor']=max(metrics['max_floor'],delta)
                df=abs(fbase(row['player'],a_y)-fbase(row['player'],c_y))
                if df and metrics['first_fbase'] is None:metrics['first_fbase']=frame
                metrics['max_fbase']=max(metrics['max_fbase'],df)
                if unsupported is not None:continue
                under=F();h=C.c_int();original_under=terrain.ref_terrain(s.position,C.byref(h))
                test.assertEqual(lib.bq_camera_terrain(*[C.byref(x) for x in models],s.position,C.byref(under)),h.value)
                test.assertEqual(bytes(under),bytes(F(original_under)))
                main_cmd=dict(row,floor=b.floor.height,under=under.value);before=bytes(s)
                ok=cl.banjo_camera_update(C.byref(s),C.byref(m),C.byref(Harness.zoom),Harness.triggers,len(Harness.triggers),C.byref(cam.make_input(main_cmd)))
                if not ok:
                    test.assertEqual(bytes(s),before);unsupported=frame
                    test.assertNotIn(name,REQUIRED,(name,frame,row));continue
                oracle.ref_step((F*3)(*row['player']),a_y,row['yaw'],original_under,row['dt'],row['vi'],row['stable'],2)
                checker.same(s,oracle,(name,frame))
                test.assertTrue(all(math.isfinite(v) for v in cam.values(s)))
                max_camera_step=max(max_camera_step,max(abs(a-c) for a,c in zip(s.position,previous_camera)));previous_camera=list(s.position)
                modes.append((s.state,s.node));stream.append(cam.pack(*cam.snapshot(oracle))+canonical(want))
                alternate_under=F();test.assertIn(lib.bq_camera_terrain(*[C.byref(x) for x in models],alt.position,C.byref(alternate_under)),(0,1))
                alt_cmd=dict(row,floor=c_y,under=alternate_under.value)
                test.assertTrue(cl.banjo_camera_update(C.byref(alt),C.byref(m),C.byref(Harness.zoom),Harness.triggers,len(Harness.triggers),C.byref(cam.make_input(alt_cmd))))
                if bytes(s)!=bytes(alt) and metrics['first_camera'] is None:metrics['first_camera']=frame
                metrics['max_camera_xyz']=max(metrics['max_camera_xyz'],max(abs(a-c) for a,c in zip(s.position,alt.position)))
                metrics['max_camera_focus']=max(metrics['max_camera_focus'],max(abs(a-c) for a,c in zip(s.focus,alt.focus)))
            results[name]=dict(frames=len(rows),camera_frames=len(stream),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),
                modes=sorted(set(modes)),unsupported_frame=unsupported,counterfactual_final=metrics,first_difference_values=first_values,
                max_floor_difference_values=max_floor_values,max_camera_step_xyz=max_camera_step)
            if name=='roundtrip':
                sequence=[v for i,v in enumerate(modes) if not i or v!=modes[i-1]]
                test.assertEqual(sequence,[(17,32),(17,-1),(11,-1),(17,32)])
                results[name]['mode_sequence']=sequence
        # The same six B.8 sequences remain byte-exact through the bridge.
        import json
        prior=json.loads((ref.ROOT/'tools/banjo3ds/tests/fixtures/floor_camera_inputs_golden.json').read_text())
        for name in REQUIRED[:-1]:test.assertEqual(results[name]['sha256'],prior[name]['sha256'])
        return results
    finally:Harness.doClassCleanups()
