"""M4.10C: actual runtime + generated zones vs original-decomp selector/camera."""
import ctypes as C
import unittest
import math
import struct
import hashlib
import json
from pathlib import Path
import test_camera_runtime as runtime
import test_camera as camera
import test_camera_zones as zones
import zones_reference as original
import zones_corpus as corpus
import free_b_corpus as free
import floor_bridge_reference as trajectories
from test_free_b import PostState

F=C.c_float

class CameraZonesRuntimeTests(unittest.TestCase):
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move

    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:
            lib.banjo_camera_init.argtypes=[C.POINTER(camera.State),C.POINTER(camera.Math),C.POINTER(camera.Input),C.POINTER(F),C.POINTER(F)]

    def assert_original(self,s,ref,result,context):
        v=camera.values(s.camera)
        self.assertEqual(camera.pack(v[:22],v[22:]),camera.pack(result[0],result[1]),context)
        self.assertEqual(bytes(s.contact),bytes(PostState(result[3],result[2])),context)
        self.assertEqual([s.zones.group,s.zones.local,s.zones.profile,s.zones.last_zoom],corpus.select_state(ref),context)
        self.assertEqual(s.parity,1)
        self.assertTrue(all(math.isfinite(x) for row in s.view for x in row))

    def test_generated_full_dataset_and_original_group_hash(self):
        expected,keep,_=zones.production_data()
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_zones_golden.json').read_text())
        for lib in self.libs:
            s,p=self.start(lib);d=s.zone_data.contents
            self.assertEqual((d.count,d.node_count),(27,43))
            self.assertEqual(C.string_at(d.triggers,150*C.sizeof(camera.Trigger)),bytes(keep[0]))
            self.assertEqual(C.string_at(d.groups,27*C.sizeof(zones.Group)),bytes(keep[1]))
            self.assertEqual(C.string_at(d.nodes,43*C.sizeof(zones.Node)),bytes(keep[2]))
            stream=[]
            for g in d.groups[:d.count]:
                stream.extend((g.node,g.count))
                for t in d.triggers[g.first:g.first+g.count]:stream.extend((*t.position,t.radius,t.mask))
            self.assertEqual(hashlib.sha256(struct.pack('>'+str(len(stream))+'i',*stream)).hexdigest(),frozen['groups_sha256'])

    def test_runtime_all_1412_frozen_camera_updates_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for scenario in corpus.schedules():
                p,eye,rot=corpus.initialize(ref,scenario)
                s,player=self.start(lib,p);s.contact=PostState(scenario['counter'],scenario['history'])
                # Supply the identical explicit viewport seed used by B's golden,
                # avoiding Python-double versus C-float bootstrap addition.
                lib.banjo_camera_init(C.byref(s.camera),C.byref(s.math),C.byref(camera.make_input(scenario['commands'][0])),
                                     (F*3)(*eye),(F*3)(*rot))
                before=(bytes(player),bytes(s.bridge),bytes(s.body),bytes(s.world_bridge))
                for i,c in enumerate(scenario['commands']):
                    s.camera.preset=c['preset'];_,result=corpus.snapshot(ref,c)
                    self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(camera.make_input(c)),(F*3)(*c['target'])),1)
                    self.assert_original(s,ref,result,(opt,scenario['name'],i))
                    self.assertEqual((bytes(player),bytes(s.bridge),bytes(s.body),bytes(s.world_bridge)),before)

    def test_actual_player_floor_camera_order_against_original_O0_O2(self):
        # Same authoritative E.2 player and floor inputs, independently evaluated
        # ORIGINAL zone/camera chain. Raw published world isolates camera parity;
        # both progress lifecycles are separately exercised below.
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for name in ('node_walk','node_jump_landing','node_exit_jump_landing','free_walk',
                         'free_jump_landing','orbit_air','rejected_ground','roundtrip'):
                rows=trajectories.trajectories(opt)[name]
                s,p=self.start(lib,rows[0]['before']);s.world_bridge.alive=0
                scenario=dict(commands=[free.command(rows[0]['before'])],history=0,counter=0)
                corpus.initialize(ref,scenario)
                for i,row in enumerate(rows):
                    under=F();self.assertGreaterEqual(lib.bq_camera_terrain(C.byref(s.opa),C.byref(s.xlu),s.camera.position,C.byref(under)),0)
                    x,y,yaw,jump=runtime.inputs(name,i)
                    self.assertEqual(self.move(lib,s,p,x,y,yaw,row['dt'],row['vi'],jump,row['camera']),1,(name,i))
                    a=p.motion.actor
                    c=free.command([a.x,a.y,a.z],floor=s.bridge.floor.height,yaw=a.yaw,under=under.value,
                        dt=row['dt'],vi=row['vi'],stable=p.motion.grounded,target=[a.x,F(a.y+80).value,a.z])
                    _,result=corpus.snapshot(ref,c);self.assert_original(s,ref,result,(opt,name,i))
                    self.assertEqual(s.calls,1);self.assertEqual(s.bridge.frame,i+1)

    def test_camera_selection_cannot_change_player_or_bridge_publication(self):
        for lib in self.libs:
            for bits in (0,0x9db1):
                a,p=self.start(lib);b,q=self.start(lib)
                lib.cameraRuntimeSetLearnedAbilities(C.byref(a),bits);lib.cameraRuntimeSetLearnedAbilities(C.byref(b),bits)
                b.zones.enabled[:]=[0]*80
                for i in range(180):
                    kw=dict(y=156,jump=i==15,orbit=40<=i<65)
                    self.assertEqual(self.move(lib,a,p,**kw),1)
                    self.assertEqual(self.move(lib,b,q,**kw),1)
                    self.assertEqual(bytes(p),bytes(q))
                    self.assertEqual(bytes(a.bridge),bytes(b.bridge))
                    self.assertEqual(bytes(a.body),bytes(b.body))
                    self.assertEqual(bytes(a.player_ground),bytes(b.player_ground))
                    self.assertEqual(bytes(a.world_bridge),bytes(b.world_bridge))
                    self.assertEqual([m.applied for m in a.world_bridge.mesh],
                                     [0,0,-5000] if bits==0 else [-5000,-5000,0])
                    self.assertEqual(C.addressof(a.xlu.bridge_state.contents),C.addressof(a.world_bridge))

    def test_unsupported_payload_and_query_failure_preserve_zone_history(self):
        for lib in self.libs:
            s,p=self.start(lib);self.assertEqual(self.move(lib,s,p),1)
            data=zones.Data.from_buffer_copy(s.zone_data.contents)
            nodes=(zones.Node*43).from_buffer_copy(C.string_at(data.nodes,43*C.sizeof(zones.Node)))
            nodes[32].type=1;data.nodes=nodes;s.zone_data=C.pointer(data)
            before=(bytes(s.camera),bytes(s.zones),bytes(s.contact),bytes(s.view))
            c=free.command([0,1800,0]);inp=camera.make_input(c)
            self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(inp),(F*3)(0,1880,0)),-2)
            self.assertEqual((bytes(s.camera),bytes(s.zones),bytes(s.contact),bytes(s.view)),before)
            nodes[32].type=3;s.zones.enabled[:]=[0]*80;s.camera.state=11;s.camera.mode=2
            before=(bytes(s.camera),bytes(s.zones),bytes(s.contact),bytes(s.view))
            self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(inp),(F*3)(float('nan'),0,0)),-1)
            self.assertEqual((bytes(s.camera),bytes(s.zones),bytes(s.contact),bytes(s.view)),before)
