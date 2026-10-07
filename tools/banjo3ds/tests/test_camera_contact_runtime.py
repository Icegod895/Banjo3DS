"""M4.9C: actual runtime boundary vs frozen, independent original B.6 proof."""
import ctypes as C
import json
from pathlib import Path
import unittest

import free_b_reference as original
import free_b_corpus as corpus
import contact_corpus
import test_camera as cam
import test_camera_runtime as runtime
from test_jump_runtime import Player
from test_movement import Vertex, Triangle
from test_free_b import PostState
from test_world_segment import Model
import floor_bridge_reference as bridge_reference

F=C.c_float

class CameraContactRuntimeTests(unittest.TestCase):
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move

    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:
            lib.bq_open.argtypes=[C.POINTER(Model),C.c_void_p,C.c_size_t]
            lib.banjo_camera_init.argtypes=[C.POINTER(cam.State),C.POINTER(cam.Math),C.POINTER(cam.Input),C.POINTER(F),C.POINTER(F)]
            lib.playerRuntimeMove.argtypes=[C.POINTER(Player),F,F,F,F,C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]

    def test_runtime_boundary_all_frozen_B6_schedules_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/free_b_golden.json').read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            self.assertEqual(corpus.golden(ref),frozen)
            for schedule in corpus.schedules():
                s,p=self.start(lib,schedule['player']);corpus.initialize(ref,schedule)
                # Explicit diagnostic seeds and raw static worlds are identical
                # to B.6; every camera frame runs the actual runtime function.
                buffers=[]
                for model,(_,packet) in zip((s.opa,s.xlu),contact_corpus.world(schedule['world'])):
                    b=C.create_string_buffer(packet);buffers.append(b)
                    self.assertEqual(lib.bq_open(C.byref(model),b,len(b)-1),1)
                lib.banjo_camera_init(C.byref(s.camera),C.byref(s.math),C.byref(cam.make_input(corpus.command(schedule['player']))),
                                     (F*3)(*schedule['eye']),(F*3)(*schedule['rotation']))
                if 'orbit' in schedule:s.camera.orbit_yaw=schedule['orbit']
                s.camera.position_step[:]=schedule.get('position_step',[0]*3)
                s.camera.angular_step[:]=schedule.get('angular_step',[0]*3)
                s.contact=PostState(schedule.get('counter',0),schedule.get('history',0))
                if not schedule['zones']:s.count=0
                protected=(bytes(p),bytes(s.bridge));count=0
                for frame,c in enumerate(schedule['commands'],1):
                    s.camera.preset=c['preset'];legacy=cam.State.from_buffer_copy(s.camera)
                    oldpost=bytes(s.contact);inp=cam.make_input(c)
                    self.assertTrue(lib.banjo_camera_update(C.byref(legacy),C.byref(s.math),s.zoom,s.triggers,s.count,C.byref(inp)))
                    want,ids,history,counter,t=corpus.step(ref,c)
                    self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(inp),(F*3)(*c['target'])),1)
                    v=cam.values(s.camera)
                    self.assertEqual(cam.pack(v[:22],v[22:]),cam.pack(want,ids),(opt,schedule['name'],frame))
                    self.assertEqual(bytes(s.contact),bytes(PostState(counter,history)))
                    self.assertEqual((bytes(p),bytes(s.bridge)),protected)
                    self.assertEqual(s.parity,1)
                    if not t.contact.changed:
                        self.assertEqual(bytes(s.camera),bytes(legacy),(schedule['name'],frame))
                        self.assertEqual(bytes(s.contact),oldpost)
                    if s.camera.state==0x11:
                        self.assertEqual(t.contact.sphere_calls,0)
                        self.assertEqual(bytes(s.camera),bytes(legacy))
                    count+=1
                self.assertEqual(count,frozen['cases'][schedule['name']]['frames'])

    def test_actual_move_floor_chain_target80_and_physics_immutability(self):
        # Independent original camera driven by the actual runtime's proven
        # floor supplier. Player E.1 integration is independently checked in
        # test_ground_runtime; the historical fail-closed player is no longer an oracle.
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for name in ('node_walk','node_jump_landing','node_exit_jump_landing','free_walk','free_jump_landing','orbit_air','rejected_ground','roundtrip'):
                rows=bridge_reference.trajectories(opt)[name]
                s,p=self.start(lib,rows[0]['before'])
                # M4.9C's frozen contract is raw static map geometry.
                s.world_bridge.alive=0
                q=Player.from_buffer_copy(p)
                schedule=dict(player=rows[0]['before'],eye=list(s.camera.position),rotation=list(s.camera.rotation),zones=True,world='real')
                corpus.initialize(ref,schedule)
                for frame,row in enumerate(rows):
                    under=F();self.assertGreaterEqual(lib.bq_camera_terrain(C.byref(s.opa),C.byref(s.xlu),s.camera.position,C.byref(under)),0)
                    x,y,yaw,jump=runtime.inputs(name,frame)
                    result=self.move(lib,s,p,x,y,yaw,row['dt'],row['vi'],jump,row['camera'])
                    if result==-2:break # original unsupported zone is outside bounded oracle
                    self.assertEqual(result,1,(name,frame))
                    a=p.motion.actor
                    cmd=corpus.command([a.x,a.y,a.z],floor=s.bridge.floor.height,yaw=a.yaw,under=under.value,
                                       dt=row['dt'],vi=row['vi'],stable=p.motion.grounded,target=[a.x,F(a.y+80).value,a.z])
                    want,ids,h,counter,t=corpus.step(ref,cmd);v=cam.values(s.camera)
                    self.assertEqual(cam.pack(v[:22],v[22:]),cam.pack(want,ids),(name,frame))
                    self.assertEqual(bytes(s.contact),bytes(PostState(counter,h)))
                    self.assertEqual(s.calls,1);self.assertEqual(s.bridge.frame,frame+1)

    def test_history_lifecycle_and_failure_commit(self):
        for lib in self.libs:
            s,p=self.start(lib);self.assertEqual(bytes(s.contact),bytes(PostState()))
            s.contact=PostState(3,-1)
            self.assertEqual(self.move(lib,s,p),1) # actual node32 init must preserve post-state
            self.assertEqual(bytes(s.contact),bytes(PostState(3,-1)))
            self.assertEqual(lib.bq_bridge_reinit(C.byref(s.bridge)),1)
            self.assertEqual(self.move(lib,s,p),1)
            self.assertEqual(bytes(s.contact),bytes(PostState(3,-1)))
            # Invalid contact inputs fail the query atomically, not a debug fallback.
            s.count=0;s.camera.state=11;s.camera.mode=2;s.camera.node=-1
            inp=cam.make_input(corpus.command([0,1800,600]))
            before=(bytes(s.camera),bytes(s.contact),bytes(s.view),bytes(p))
            self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(inp),(F*3)(float('nan'),0,0)),-1)
            self.assertEqual((bytes(s.camera),bytes(s.contact),bytes(s.view),bytes(p)),before)

    def test_original_normal_banjo_target_offset_writers(self):
        # Evidence guard: +80 is the original normal-Banjo collider input,
        # not one of B.6's independently supplied diagnostic +60 targets.
        from segment_reference import function
        code=function('src/core2/code_C4B0.c','func_80293D74')
        self.assertIn('func_80293D48(80.0f, 35.0f)',code)
        getter=function('src/core2/code_7060.c','func_8028EC64')
        self.assertIn('func_80293D2C(&sp18, &sp1C)',getter)
        self.assertIn('arg0[1] += sp18',getter)
        self.assertIn('*arg0 = D_8037C1F8[0]',function('src/core2/code_C4B0.c','func_80293D2C'))

if __name__=='__main__':unittest.main()
