"""D.2: actual runtime/query/VBO publication vs original actor/mesh routines."""
import ctypes as C
import struct
import unittest

import bridge_reference as original
import bridge_corpus as corpus
import contact_corpus
import free_b_corpus as free
import floor_state_reference as floor_ref
import floor_bridge_reference as cadence_ref
import segment_reference
import test_camera as cam
import test_camera_runtime as runtime
from test_bridge_state import View
from test_world_segment import Model
from test_jump_runtime import Player
from test_movement import Vertex, Triangle, Actor
from test_free_b import PostState
from tools.banjo3ds.bridge_state.render_binding import binding, export

F=C.c_float
ROOT=original.ROOT


def original_corners():
    """Independent F3DEX cache scan of raw 14D0 (no production decoder)."""
    data=(ROOT/'assets/model/14D0.model.bin').read_bytes()
    at=int.from_bytes(data[12:16],'big')
    count=int.from_bytes(data[at:at+4],'big');cache=[None]*32;corners=[]
    for p in range(at+8,at+8+count*8,8):
        w0,w1=struct.unpack_from('>II',data,p);op=w0>>24
        if op==4:
            n=(w0&65535)>>10;slot=((w0>>16)&255)//2
            first=(w1-0x1000000)//16
            cache[slot:slot+n]=range(first,first+n)
        elif op in (0xbf,0xb1):
            for word in ([w1] if op==0xbf else [w0,w1]):
                corners.extend(cache[(word>>shift&255)//2] for shift in (16,8,0))
    assert None not in corners
    return corners


def original_vbo():
    text=(ROOT/'platform/3ds/source/generated_model.h').read_text()
    rows=text.split('static const Banjo3DSVertex banjo_vertices[] = {\n')[1].split('};')[0]
    result=[]
    for row in rows.strip().splitlines():
        values=[v.strip().rstrip('f') for v in row.strip(' {},\n').split(',')]
        result.append(struct.pack('=5f4B',*[float(x) for x in values[:5]],*[int(x) for x in values[5:]]))
    return b''.join(result)


class BridgeRuntimeTests(unittest.TestCase):
    body_observer=True
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move

    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        cls.vbo=original_vbo();cls.first,cls.ids,total=binding(ROOT/'assets/model/14D0.model.bin')
        cls.first+=len(cls.vbo)//24-total
        cls.id_array=(C.c_uint16*len(cls.ids))(*cls.ids)
        for lib in cls.libs:
            lib.bridge_component.argtypes=[C.POINTER(Model),C.c_uint,C.c_uint];lib.bridge_component.restype=C.c_int16
            lib.bridge_render_y.argtypes=[C.POINTER(View),C.c_void_p,C.c_size_t,C.c_size_t,C.c_size_t,C.POINTER(C.c_uint16),C.c_size_t]
            lib.bridge_camera_terrain.argtypes=[C.POINTER(Model),C.POINTER(Model),C.POINTER(F),C.POINTER(F)]
            lib.playerRuntimeMove.argtypes=[C.POINTER(Player),F,F,F,F,C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
            lib.banjo_camera_init.argtypes=[C.POINTER(cam.State),C.POINTER(cam.Math),C.POINTER(cam.Input),C.POINTER(F),C.POINTER(F)]

    def assert_geometry(self,lib,ref,s,full=True):
        for role,model in enumerate((s.opa,s.xlu)):
            for vertex in (range(model.nv) if full else range(134,166) if role else ()):
                xyz=(C.c_int16*3)();ref.bridge_ref_xyz(role,vertex,xyz)
                self.assertEqual([lib.bridge_component(C.byref(model),vertex,a) for a in range(3)],list(xyz))
        f=(F*6)();i=(C.c_int32*9)();ref.bridge_ref_state(f,i)
        self.assertEqual(struct.pack('=6f',*[v for m in s.world_bridge.mesh for v in (m.offset,m.elapsed)]),bytes(f))
        self.assertEqual([v for m in s.world_bridge.mesh for v in (m.pending,m.completed)]+[s.world_bridge.initialized,s.world_bridge.alive],list(i)[:8])

    def write(self,lib,s,vbo,ids=None):
        return lib.bridge_render_y(C.cast(C.byref(s.xlu),C.POINTER(View)),vbo,len(self.vbo)//24,24,self.first,
                                  self.id_array if ids is None else ids,len(self.ids))

    def test_binding_all_source_ids_and_actual_generated_corners(self):
        corners=original_corners();meshes=original.membership();affected=set(sum(meshes.values(),[]))
        selected=[(i,v) for i,v in enumerate(corners) if v in affected]
        self.assertEqual(len(corners),1107);self.assertEqual(len(selected),48)
        self.assertEqual([i for i,_ in selected],list(range(162,210)))
        self.assertEqual(tuple(v for _,v in selected),self.ids)
        self.assertEqual(affected-set(corners),set(meshes[497]))
        self.assertEqual((self.first,len(self.vbo)//24),(11655,12600))
        raw=original.geometry_manifest();self.assertEqual(len(raw['vertex_ids']),32);self.assertEqual(len(raw['occurrences']),20)
        from world_query_reference import original as asset
        xyz=asset(0x14d0,1)['xyz']
        for k,v in enumerate(corners):
            self.assertEqual(struct.unpack_from('=3f',self.vbo,24*(11493+k)),tuple(float(x) for x in xyz[v]))
        self.assertIn('#define BANJO_BRIDGE_CORNER_COUNT 48',export(ROOT/'assets/model/14D0.model.bin'))

    def test_actual_lifecycle_render_query_sync_and_no_packet_copy_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for initial in (0,0x9db1):
                s,p=self.start(lib);contact_corpus.load(ref,'real');corpus.configure(ref,'raw')
                vbo=C.create_string_buffer(self.vbo);self.assert_geometry(lib,ref,s)
                packets=[C.string_at(lib.packet(r),lib.packet_size(r)) for r in (0,1)]
                for step,bits in enumerate((initial,0x9db1,0,0xffffffff,0)):
                    lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
                    ref.bridge_ref_actor(bits);ref.bridge_ref_mesh(F(1/60))
                    self.assertEqual(self.move(lib,s,p),1);self.assertEqual(s.camera.node,32)
                    self.assert_geometry(lib,ref,s)
                    self.assertEqual(s.calls,1);self.assertEqual(s.bridge.frame,step+1)
                    self.assertIn(self.write(lib,s,vbo),(0,1))
                    expected=bytearray(self.vbo)
                    for k,v in enumerate(self.ids):
                        xyz=(C.c_int16*3)();ref.bridge_ref_xyz(1,v,xyz)
                        struct.pack_into('=f',expected,24*(self.first+k)+4,float(xyz[1]))
                    self.assertEqual(vbo.raw[:-1],expected)
                    self.assertEqual(self.write(lib,s,vbo),0) # absolute, never cumulative
                    self.assertEqual([C.string_at(lib.packet(r),lib.packet_size(r)) for r in (0,1)],packets)
                    self.assertEqual(C.addressof(s.opa.bridge_state.contents),C.addressof(s.world_bridge))
                    self.assertEqual(C.addressof(s.xlu.bridge_state.contents),C.addressof(s.world_bridge))
                # Full map initialization, unlike progress setter/player recovery,
                # creates a fresh actor and starts from immutable original XYZ.
                self.assertEqual(lib.init(C.byref(s),C.byref(p)),1)
                contact_corpus.load(ref,'real');corpus.configure(ref,'raw');self.assert_geometry(lib,ref,s)
                self.assertEqual(s.learned_abilities,0)
                self.move(lib,s,p);self.assertTrue(s.world_bridge.alive)
                self.assertEqual([m.applied for m in s.world_bridge.mesh],[0,0,-5000])

    def test_writer_validation_atomic_and_skipped_render_catches_up(self):
        for lib in self.libs:
            s,p=self.start(lib);vbo=C.create_string_buffer(self.vbo)
            self.move(lib,s,p) # skip VBO publication, like failed FrameBegin
            lib.cameraRuntimeSetLearnedAbilities(C.byref(s),0x9db1);self.move(lib,s,p)
            bad=(C.c_uint16*len(self.ids))(*self.ids);bad[-1]=0
            self.assertEqual(self.write(lib,s,vbo,bad),-1);self.assertEqual(vbo.raw[:-1],self.vbo)
            self.assertEqual(self.write(lib,s,vbo),1)
            for k,v in enumerate(self.ids):
                self.assertEqual(struct.unpack_from('=f',vbo.raw,24*(self.first+k)+4)[0],lib.bridge_component(C.byref(s.xlu),v,1))
            self.assertEqual(self.write(lib,s,vbo),0)

    def test_three_D1_diagnostics_actual_runtime_view_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for seed in corpus.seeds():
                for mode in ('before_all','all_learned'):
                    frames=corpus.run(ref,seed,mode)
                    s,p=self.start(lib);lib.cameraRuntimeSetLearnedAbilities(C.byref(s),corpus.MODES[mode]);self.move(lib,s,p)
                    lib.banjo_camera_init(C.byref(s.camera),C.byref(s.math),C.byref(cam.make_input(free.command(seed['player']))),
                        (F*3)(*seed['eye']),(F*3)(*seed['rotation']))
                    s.count=0;s.contact=PostState();protected=bytes(p)
                    for frame,(cmd,want) in enumerate(frames,1):
                        under=F();self.assertGreaterEqual(lib.bridge_camera_terrain(C.byref(s.opa),C.byref(s.xlu),s.camera.position,C.byref(under)),0)
                        self.assertEqual(bytes(under),bytes(F(cmd['under'])))
                        self.assertEqual(lib.cameraRuntimeUpdateView(C.byref(s),C.byref(cam.make_input(cmd)),(F*3)(*cmd['target'])),1)
                        v=cam.values(s.camera)
                        self.assertEqual(cam.pack(v[:22],v[22:]),cam.pack(want[0],want[1]),(opt,seed['name'],mode,frame))
                        self.assertEqual(bytes(s.contact),bytes(PostState(want[3],want[2])))
                        self.assertEqual(bytes(p),protected)

    @unittest.skip("superseded by the E.2B runtime observer and body-frame corpus")
    def test_actual_move_query_before_publication_vs_original_floor_and_camera(self):
        from test_body_runtime import Capture
        # Original floor oracle owns a persistent native vertex block. Publish
        # ORIGINAL mesh routine outputs into it without rebuilding identities,
        # bounds, grid or floor history. Production algorithms are not used.
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt);floor=floor_ref.library(opt)
            for mode in ('before_all','all_learned'):
                for name in ('node_stationary','node_jump_landing','free_jump_landing','free_walk','roundtrip','void_recovery'):
                    rows=cadence_ref.trajectories(opt)[name]
                    s,p=self.start(lib,rows[0]['before']);q=Player.from_buffer_copy(p)
                    free.initialize(ref,dict(player=rows[0]['before'],eye=list(s.camera.position),rotation=list(s.camera.rotation),zones=True,world='real'))
                    corpus.configure(ref,'raw');segment_reference.load_real(floor);floor.floor_ref_init()
                    vertex_block=(C.c_void_p*5).in_dll(floor,'mapModel')[3]
                    bits=corpus.MODES[mode];lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
                    unsupported=False
                    for frame,row in enumerate(rows):
                        # Include a real lifetime progress change during flight.
                        if name=='free_jump_landing' and frame==60:
                            bits=0x9db1;lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
                        ref.bridge_ref_actor(bits)
                        eye=(F*3).in_dll(ref,'cameraPosition')
                        terrain=contact_corpus.query(ref,('terrain','real',3,(eye[0],eye[1]+10,eye[2]),(eye[0],eye[1]-600,eye[2]),0,0,0x800000))
                        self.assertGreaterEqual(terrain[0],0)
                        under=F(terrain[1][1] if terrain[0] else F(eye[1]-600).value)
                        if name=='void_recovery' and frame==20:
                            for player in (p,q):player.motion.actor=Actor(9000,-1000,9000,0);player.motion.grounded=False;player.motion.vy=-1000
                        x,y,yaw,jump=runtime.inputs(name,frame)
                        result=self.move(lib,s,p,x,y,yaw,row['dt'],row['vi'],jump,row['camera'])
                        # Replay each REAL E.2 iteration candidate to the original
                        # floor oracle, preserving one parity and pre-publication world.
                        observed=Capture()
                        lib.body_runtime_capture.argtypes=[C.POINTER(Capture)]
                        lib.body_runtime_capture(C.byref(observed))
                        for i in range(observed.queries.floors):
                            self.assertEqual(bytes(observed.queries.before[i]),floor_ref.snapshot(floor))
                            self.assertEqual(observed.queries.parity[i],frame&1)
                            floor.floor_ref_step(observed.queries.candidate[i],56,0x400000,frame&1)
                            self.assertEqual(bytes(observed.queries.after[i]),floor_ref.snapshot(floor))
                        if p.events&4:
                            floor.floor_ref_reinit()
                            a=p.motion.actor
                            floor.floor_ref_step((F*3)(a.x,a.y,a.z),56,0x400000,frame&1)
                        self.assertEqual(bytes(s.bridge.floor),floor_ref.snapshot(floor),(opt,mode,name,frame))
                        self.assertEqual(s.calls,1);self.assertEqual(s.bridge.frame,frame+1)
                        if result==-2:unsupported=True
                        else:self.assertEqual(result,1)
                        if not unsupported:
                            a=p.motion.actor;cmd=free.command([a.x,a.y,a.z],floor=s.bridge.floor.height,yaw=a.yaw,under=under.value,
                                dt=row['dt'],vi=row['vi'],stable=p.motion.grounded,target=[a.x,F(a.y+80).value,a.z])
                            want,ids,h,counter,t=free.step(ref,cmd);v=cam.values(s.camera)
                            self.assertEqual(cam.pack(v[:22],v[22:]),cam.pack(want,ids),(opt,mode,name,frame))
                            self.assertEqual(bytes(s.contact),bytes(PostState(counter,h)))
                            if s.camera.state==0x11:self.assertEqual(t.contact.sphere_calls,0)
                        ref.bridge_ref_mesh(row['dt'])
                        for vertex in range(134,166):
                            xyz=(C.c_int16*3)();ref.bridge_ref_xyz(1,vertex,xyz)
                            C.memmove(vertex_block+24+16*vertex,xyz,6)
                        self.assert_geometry(lib,ref,s,full=False)

    def test_gpu_publication_order_and_normal_build_policy(self):
        text=(ROOT/'platform/3ds/source/main.c').read_text()
        self.assertLess(text.index('cameraRuntimeMove(&rareCamera'),text.index('C3D_FrameBegin(C3D_FRAME_SYNCDRAW)'))
        self.assertLess(text.index('C3D_FrameBegin(C3D_FRAME_SYNCDRAW)'),text.index('bridge_render_y(&rareCamera.xlu'))
        self.assertLess(text.index('bridge_render_y(&rareCamera.xlu'),text.index('if (bridgeChanged)'))
        self.assertLess(text.index('if (bridgeChanged)'),text.index('            sceneRender();'))
        make=(ROOT/'platform/3ds/Makefile').read_text()
        self.assertIn('BANJO3DS_LEARNED_ABILITIES ?= 0x9DB1',make)
        self.assertIn('BANJO3DS_DEBUG_CAMERA ?= 0',make)

if __name__=='__main__':unittest.main()
