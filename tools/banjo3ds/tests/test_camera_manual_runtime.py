"""D-C actual runtime -> compiled original manual controller, no physical mapping.

The D-B oracle compiles decomp routines. Bridge cases obtain transformed native
vertices from the separate original actor/mesh oracle, not production overlays.
The neutral comparator executes the accepted M4.10C zone path in a test-only
link wrapper; it never ships in the viewer.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import unittest
import manual_reference as original
import manual_corpus as corpus
import contact_corpus as contact
import bridge_reference
import bridge_corpus
import test_camera as camera
import test_camera_runtime as runtime
from test_camera_manual import State, Trace, values
from test_bridge_state import State as BridgeState
F=C.c_float
ROOT=original.ROOT

class ManualRuntimeTests(unittest.TestCase):
    manual_observer=True
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move

    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:
            lib.bm_init.argtypes=[C.POINTER(State),C.POINTER(camera.Math),C.POINTER(camera.Input),C.POINTER(F),C.POINTER(F)]
            lib.runtime_manual_trace.argtypes=[C.POINTER(Trace)]
            lib.runtime_legacy_camera.argtypes=[C.c_int]
            lib.bridge_model_open.argtypes=[C.POINTER(runtime.RuntimeModel),C.c_void_p,C.c_size_t,C.POINTER(BridgeState)]
            lib.bridge_actor_tick.argtypes=[C.POINTER(BridgeState),C.c_uint32]
            lib.bridge_mesh_tick.argtypes=[C.POINTER(BridgeState),F]

    def run_history(self,lib,ref,spec,bridge=None):
        corpus.initialize(ref,spec)
        c=spec['commands'][0];p=c['player']
        eye=spec.get('eye',[p[0],p[1]+375,p[2]-850]);rot=spec.get('rotation',[340,180,0])
        s,player=self.start(lib,p);buffers=[]
        for model,(_,packet) in zip((s.opa,s.xlu),contact.world(spec['world'])):
            b=C.create_string_buffer(packet);buffers.append(b)
            self.assertEqual(lib.bridge_model_open(C.byref(model),b,len(packet),C.byref(s.world_bridge)),1)
        lib.bm_init(C.byref(s.manual),C.byref(s.math),C.byref(camera.make_input(c)),(F*3)(*eye),(F*3)(*rot))
        if spec.get('disable_zones'):s.zones.enabled[:]=[0]*80
        s.contact.history=spec.get('history',0);s.contact.counter=spec.get('counter',0)
        if bridge is not None:
            bits,native=bridge
            # Publish with the existing state lifecycle; feed the independently
            # transformed ORIGINAL vertex block to the original query oracle.
            lib.bridge_actor_tick(C.byref(s.world_bridge),bits)
            lib.bridge_mesh_tick(C.byref(s.world_bridge),F(1/60))
            ref.ref_load(1,C.create_string_buffer(native))
        protected=(bytes(player),bytes(s.bridge),bytes(s.body),bytes(s.player_ground),bytes(s.world_bridge))
        stream=[];different=0
        adapter=getattr(self,'physical_adapter',None)
        if adapter is not None:adapter.reset()
        for index,c in enumerate(spec['commands']):
            before=bytes(s.manual);old_yaw=s.manual.viewport_rotation[1]
            adapted=(F*3)();lib.cameraRuntimeMovementInput(C.byref(s),False,0,156,0,adapted)
            self.assertEqual(bytes(adapted),struct.pack('=3f',-156,0,F(180-old_yaw).value))
            self.assertEqual(bytes(s.manual),before)
            want=corpus.step(ref,c)
            buttons=c['buttons'] if adapter is None else adapter.translate(lib,c['buttons'])
            self.assertEqual(buttons,c['buttons'])
            lib.cameraRuntimeManualInput(C.byref(s),buttons,c['enabled'])
            target=c.get('target',[c['player'][0],c['player'][1]+80,c['player'][2]])
            self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(camera.make_input(c)),(F*3)(*target)),1,(spec['name'],index))
            trace=Trace();lib.runtime_manual_trace(C.byref(trace))
            got=corpus.packed(values(s.manual,trace));expected=corpus.packed(want)
            self.assertEqual(got,expected,(spec['name'],index))
            stream.append(got)
            visible=camera.State.from_buffer_copy(s.camera)
            visible.position[:]=s.manual.viewport_position;visible.rotation[:]=s.manual.viewport_rotation
            view=(F*16)();parity=C.c_int()
            self.assertTrue(lib.cameraRareView(C.byref(visible),view,C.byref(parity)))
            self.assertEqual(bytes(view),bytes(s.view));self.assertEqual(s.parity,parity.value)
            different+=bytes(visible.position)!=bytes(s.camera.position) or bytes(visible.rotation)!=bytes(s.camera.rotation)
            self.assertEqual((bytes(player),bytes(s.bridge),bytes(s.body),bytes(s.player_ground),bytes(s.world_bridge)),protected)
        return b''.join(stream),different

    def test_all_43_original_histories_through_actual_runtime_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_manual_golden.json').read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt);streams=[];frames=0;visible_difference=0
            for spec in corpus.schedules():
                stream,different=self.run_history(lib,ref,spec)
                self.assertEqual(hashlib.sha256(stream).hexdigest(),frozen['cases'][spec['name']]['sha256'])
                streams.append(stream);frames+=len(spec['commands']);visible_difference+=different
            self.assertEqual(frames,7360)
            self.assertEqual(hashlib.sha256(b''.join(streams)).hexdigest(),frozen['sha256'])
            self.assertGreater(visible_difference,0)

    def test_manual_queries_observe_original_published_bridge_O0_O2(self):
        all_streams=[]
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt);actor=bridge_reference.library(opt);stream=[]
            for bits in (0,0x9db1):
                contact.load(actor,'real')
                native=bytearray((ROOT/'assets/model/14D0.model.bin').read_bytes())
                actor.bridge_ref_reset(C.create_string_buffer(bytes(native)))
                actor.bridge_ref_actor(bits);actor.bridge_ref_mesh(F(1/60))
                vertex_block=struct.unpack_from('>I',native,16)[0]
                for ids in bridge_reference.membership().values():
                    for v in ids:
                        xyz=(C.c_int16*3)();actor.bridge_ref_xyz(1,v,xyz)
                        struct.pack_into('>3h',native,vertex_block+24+v*16,*xyz)
                for seed in bridge_corpus.seeds():
                    for button in (0,1,2,4):
                        spec=dict(name=seed['name']+'-'+str(bits)+'-'+str(button),world='real',
                            disable_zones=True,eye=seed['eye'],rotation=seed['rotation'],
                            commands=[corpus.command(seed['player'],buttons=button if (button==1 and i<45) or i==0 else 0,
                                                      yaw=90) for i in range(90)])
                        rows,_=self.run_history(lib,ref,spec,(bits,bytes(native)));stream.append(rows)
            all_streams.append(hashlib.sha256(b''.join(stream)).hexdigest())
        self.assertEqual(all_streams[0],all_streams[1])

    def test_neutral_player_floor_body_bridge_and_view_match_accepted_runtime(self):
        starts=((0,1800,0),(-37.666668,1784,-3751),(0,1576,-1800),(-2094,133.333344,-383.666656))
        for lib in self.libs:
            for bits in (0,0x9db1):
                for start in starts:
                    new,p=self.start(lib,start);old,q=self.start(lib,start)
                    for s in (new,old):lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
                    for i in range(180):
                        pad=156 if i<100 else 0;orbit=60<=i<75
                        velocities=[];statuses=[]
                        for legacy,s,player in ((False,new,p),(True,old,q)):
                            lib.runtime_legacy_camera(legacy)
                            lib.cameraRuntimeManualInput(C.byref(s),0,35)
                            adapted=(F*3)();lib.cameraRuntimeMovementInput(C.byref(s),False,0,0,pad,adapted)
                            velocities.append(bytes(adapted))
                            statuses.append(self.move(lib,s,player,*adapted,jump=i==20,orbit=orbit))
                        lib.runtime_legacy_camera(0)
                        self.assertEqual(statuses,[1,1]);self.assertEqual(velocities[0],velocities[1])
                        self.assertEqual(bytes(p),bytes(q),(bits,start,i))
                        for field in ('bridge','body','player_ground','world_bridge','camera','zones','contact','view'):
                            self.assertEqual(bytes(getattr(new,field)),bytes(getattr(old,field)),(bits,start,i,field))
                        self.assertEqual(bytes(new.manual.viewport_position),bytes(old.manual.viewport_position))
                        self.assertEqual(bytes(new.manual.viewport_rotation),bytes(old.manual.viewport_rotation))

    def test_injected_manual_through_real_player_frame_and_original_viewport(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            ref.ref_contact_query.argtypes=[C.c_int,C.POINTER(F),C.POINTER(F),F,C.c_int,C.c_uint32,C.POINTER(F),C.POINTER(C.c_int32)]
            for start in ((0,1800,0),(0,1800,800)):
                s,p=self.start(lib,start);s.world_bridge.alive=0 # explicit raw-world oracle scope
                corpus.initialize(ref,dict(world='real',commands=[corpus.command(start)]))
                for i in range(240):
                    previous=corpus.snapshot(ref)
                    xyz=previous[0][:3]
                    a=(F*3)(xyz[0],F(xyz[1]+10).value,xyz[2]);b=(F*3)(xyz[0],F(xyz[1]-600).value,xyz[2])
                    hit=ref.ref_contact_query(3,a,b,0,0,0x800000,(F*3)(),(C.c_int32*8)())
                    self.assertGreaterEqual(hit,0)
                    under=b[1] if hit else F(xyz[1]-600).value
                    buttons=1 if 10<=i<55 else {70:2,90:4,125:8,180:2}.get(i,0)
                    pad=156 if i<140 else 0;out=(F*3)()
                    lib.cameraRuntimeMovementInput(C.byref(s),False,0,0,pad,out)
                    self.assertEqual(bytes(out),struct.pack('=3f',-0.0,pad,F(180-previous[0][44]).value))
                    lib.cameraRuntimeManualInput(C.byref(s),buttons,35)
                    self.assertEqual(self.move(lib,s,p,*out,jump=i==30,orbit=95<=i<110),1)
                    actor=p.motion.actor
                    c=corpus.command([actor.x,actor.y,actor.z],buttons=buttons,floor=s.bridge.floor.height,
                        yaw=actor.yaw,under=under,stable=p.motion.grounded)
                    want=corpus.step(ref,c);trace=Trace();lib.runtime_manual_trace(C.byref(trace))
                    self.assertEqual(corpus.packed(values(s.manual,trace)),corpus.packed(want),(start,i))
                    self.assertEqual(s.bridge.frame,i+1);self.assertEqual(s.calls,1)

    def test_previous_visible_yaw_and_debug_input_boundary(self):
        for lib in self.libs:
            s,p=self.start(lib)
            # Deliberately distinct internal/viewport yaw makes an accidental
            # internal-camera read or a second update detectable.
            s.camera.rotation[1]=90;s.manual.viewport_rotation[1]=270
            before=bytes(s.manual);out=(F*3)()
            lib.cameraRuntimeMovementInput(C.byref(s),False,33,156,0,out)
            self.assertEqual(list(out),[-156,0,-90])
            lib.cameraRuntimeMovementInput(C.byref(s),True,33,156,0,out)
            self.assertEqual(list(out),[156,0,33]);self.assertEqual(bytes(s.manual),before)
        main=(ROOT/'platform/3ds/source/main.c').read_text()
        self.assertIn('cameraRuntimeManualInput(&rareCamera, BANJO_DEBUG_CAMERA ? 0 : controls.manual, 0x23)',main)
        self.assertLess(main.index('cameraRuntimeMovementInput(&rareCamera'),main.index('cameraRuntimeMove(&rareCamera'))
        self.assertIn('rareCamera.manual.viewport_position[0]',main)
        self.assertNotIn('rareCamera.camera',main)
        # D-D supplies translated normal input; debug still supplies neutral.
        # There remains exactly one controller-input submission per frame.
        self.assertEqual(main.count('cameraRuntimeManualInput('),1)

    def test_invalid_manual_update_preserves_committed_view_and_state(self):
        for lib in self.libs:
            s,p=self.start(lib);self.assertEqual(self.move(lib,s,p),1)
            before=(bytes(s.manual),bytes(s.view),bytes(p),bytes(s.bridge),bytes(s.world_bridge))
            lib.cameraRuntimeManualInput(C.byref(s),16,35)
            c=corpus.command((0,1800,0));self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(camera.make_input(c)),(F*3)(0,1880,0)),-1)
            self.assertEqual((bytes(s.manual),bytes(s.view),bytes(p),bytes(s.bridge),bytes(s.world_bridge)),before)
