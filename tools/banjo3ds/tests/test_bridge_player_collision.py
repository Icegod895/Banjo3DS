"""D.3B: shared published BridgeState -> sparse reads -> unchanged player solver.
Independent original actor/mesh callbacks supply the reference coordinates.
"""
import ctypes as C
import unittest

import bridge_reference as original
import bridge_corpus as corpus
import floor_state_reference as floor_ref
import segment_reference
import contact_corpus
import test_camera_runtime as runtime
from test_bridge_movement_binding import reference, OPA, XLU
from test_bridge_state import State
from test_jump_runtime import Player
from test_jump import Motion
from test_movement import Vertex, Triangle, Actor

F=C.c_float
VP=C.POINTER(Vertex)
TP=C.POINTER(Triangle)
FP=C.POINTER(F)
class Overlay(C.Structure):
    _fields_=[('binding',C.POINTER(C.c_uint16*3)),('count',C.c_size_t),
              ('state',C.c_void_p),('offset',C.c_void_p)]


class BridgePlayerTests(unittest.TestCase):
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move

    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        cls.manifest=reference(OPA.read_bytes(),XLU.read_bytes())
        cls.rows=cls.manifest['vertices']
        cls.affected={r['movement_vertex'] for r in cls.rows}
        cls.touched={r['movement_triangle'] for r in cls.manifest['triangles']}
        for lib in cls.libs:
            lib.bridge_movement_overlay.argtypes=[C.POINTER(State)]
            lib.bridge_movement_overlay.restype=Overlay
            lib.bridge_actor_tick.argtypes=[C.POINTER(State),C.c_uint32]
            lib.bridge_mesh_tick.argtypes=[C.POINTER(State),F]
            lib.movement_read.argtypes=[VP,C.c_uint,C.POINTER(Overlay),VP]
            lib.movementFloor.argtypes=[VP,TP,C.c_size_t,F,F,F,FP]
            lib.movementFloor.restype=C.c_bool
            lib.movementFloorOverlay.argtypes=lib.movementFloor.argtypes+[C.POINTER(Overlay)]
            lib.movementFloorOverlay.restype=C.c_bool
            lib.movementFollowFloor.argtypes=[VP,TP,C.c_size_t,F,F,F,F,F,FP]
            lib.movementFollowFloor.restype=C.c_bool
            lib.movementFollowFloorOverlay.argtypes=lib.movementFollowFloor.argtypes+[C.POINTER(Overlay)]
            lib.movementFollowFloorOverlay.restype=C.c_bool
            lib.banjo_jump_sweep.argtypes=[VP,TP,C.c_size_t,FP,FP,FP,C.POINTER(C.c_size_t)]
            lib.banjo_jump_sweep.restype=C.c_bool
            lib.banjo_jump_sweep_overlay.argtypes=lib.banjo_jump_sweep.argtypes+[C.POINTER(Overlay)]
            lib.banjo_jump_sweep_overlay.restype=C.c_bool
            lib.playerRuntimeMove.argtypes=[C.POINTER(Player),F,F,F,F,C.c_bool,C.c_bool,VP,TP,C.c_size_t]

    def expected(self,ref):
        # Only test/reference storage is materialized. Production never copies it.
        vertices=(Vertex*len(self.vertices)).from_buffer_copy(self.vertices)
        for row in self.rows:
            xyz=(C.c_int16*3)()
            ref.bridge_ref_xyz(1,row['source_vertex'],xyz)
            vertices[row['movement_vertex']]=Vertex(*xyz)
        return vertices

    def world(self,opt,lib,bits):
        ref=original.library(opt)
        contact_corpus.load(ref,'real');corpus.configure(ref,'raw')
        s,p=self.start(lib)
        lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
        ref.bridge_ref_actor(bits)
        self.move(lib,s,p)  # Both paths publish only AFTER their queries.
        ref.bridge_ref_mesh(F(1/60))
        return s,p,ref,self.expected(ref)

    def floor(self,lib,vertices,triangles,x,z,y,overlay=None):
        out=F(9876)
        args=[vertices,triangles,len(triangles),x,z,y,C.byref(out)]
        ok=lib.movementFloor(*args) if overlay is None else lib.movementFloorOverlay(*args,C.byref(overlay))
        return ok,bytes(out)

    def follow(self,lib,vertices,overlay=None):
        out=F(9876)
        args=[vertices,self.triangles,len(self.triangles),0,1576,-1800,0,-1825,C.byref(out)]
        ok=lib.movementFollowFloor(*args) if overlay is None else lib.movementFollowFloorOverlay(*args,C.byref(overlay))
        return ok,bytes(out)

    def sweep(self,lib,vertices,triangles,start,end,overlay=None):
        out=(F*3)(9876,9876,9876);index=C.c_size_t(9876)
        args=[vertices,triangles,len(triangles),(F*3)(*start),(F*3)(*end),out,C.byref(index)]
        ok=lib.banjo_jump_sweep(*args) if overlay is None else lib.banjo_jump_sweep_overlay(*args,C.byref(overlay))
        return ok,bytes(out),index.value

    def test_all_coordinates_against_original_and_absent_498_O0_O2(self):
        protected=bytes(self.vertices),bytes(self.triangles)
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for bits in (0,0x9db1):
                s,p,ref,want=self.world(opt,lib,bits)
                o=lib.bridge_movement_overlay(C.byref(s.world_bridge))
                self.assertEqual(o.state,C.addressof(s.world_bridge))
                rows=[tuple(o.binding[i]) for i in range(o.count)]
                self.assertEqual(rows,[(r['movement_vertex'],r['source_vertex'],r['mesh_slot']) for r in self.rows])
                self.assertEqual(sorted(r[0] for r in rows),[r[0] for r in rows])
                self.assertEqual({r[2] for r in rows},{0,2})
                for i in range(len(self.vertices)):
                    got=Vertex();lib.movement_read(self.vertices,i,C.byref(o),C.byref(got))
                    self.assertEqual(bytes(got),bytes(want[i]),(opt,bits,i))
                    if i not in self.affected:self.assertEqual(bytes(got),bytes(self.vertices[i]))
                self.assertEqual((bytes(self.vertices),bytes(self.triangles)),protected)

    def test_three_hardware_cases_and_every_bridge_face_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for bits in (0,0x9db1):
                s,p,ref,want=self.world(opt,lib,bits)
                o=lib.bridge_movement_overlay(C.byref(s.world_bridge))
                got=self.floor(lib,self.vertices,self.triangles,0,-1800,1576,o)
                self.assertEqual(got,self.floor(lib,want,self.triangles,0,-1800,1576))
                self.assertEqual(got[0],bool(bits))
                got=self.follow(lib,self.vertices,o)
                self.assertEqual(got,self.follow(lib,want));self.assertEqual(got[0],bool(bits))
                got=self.sweep(lib,self.vertices,self.triangles,(0,1600,-1800),(0,1540,-1800),o)
                self.assertEqual(got,self.sweep(lib,want,self.triangles,(0,1600,-1800),(0,1540,-1800)))
                self.assertEqual(got[0],bool(bits))
                top=[]
                for row in self.manifest['triangles']:
                    i=row['movement_triangle'];triangle=(Triangle*1)(self.triangles[i])
                    ids=row['movement_vertices']
                    x,y,z=[sum(getattr(self.vertices[j],axis) for j in ids)/3 for axis in ('x','y','z')]
                    shifted=sum(want[j].y for j in ids)/3
                    for height in (y,shifted):
                        got=self.floor(lib,self.vertices,triangle,x,z,height,o)
                        self.assertEqual(got,self.floor(lib,want,triangle,x,z,height),(opt,bits,i,height))
                        a=(x,height+40,z);b=(x,height-40,z)
                        self.assertEqual(self.sweep(lib,self.vertices,triangle,a,b,o),self.sweep(lib,want,triangle,a,b))
                    if self.floor(lib,self.vertices,triangle,x,z,shifted,o)[0]:top.append(i)
                self.assertEqual(top,[3042,3043,3044,3045]) # expectation ONLY, not runtime input

    def test_unaffected_triangle_queries_bit_exact_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for bits in (0,0x9db1):
                s,p,ref,want=self.world(opt,lib,bits)
                o=lib.bridge_movement_overlay(C.byref(s.world_bridge))
                for i,t in enumerate(self.triangles):
                    if i in self.touched:continue
                    one=(Triangle*1)(t);ids=(t.a,t.b,t.c)
                    x,y,z=[sum(getattr(self.vertices[j],a) for j in ids)/3 for a in ('x','y','z')]
                    self.assertEqual(self.floor(lib,self.vertices,one,x,z,y,o),self.floor(lib,self.vertices,one,x,z,y))
                    self.assertEqual(self.sweep(lib,self.vertices,one,(x,y+40,z),(x,y-40,z),o),
                                     self.sweep(lib,self.vertices,one,(x,y+40,z),(x,y-40,z)))

    def test_actual_runtime_player_uses_prepublication_geometry_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for bits in (0,0x9db1):
                for airborne in (False,True):
                    s,p=self.start(lib,(0,1600 if airborne else 1576,-1800),180)
                    p.motion.grounded=not airborne
                    if airborne:p.motion.vy=-1100
                    ref=original.library(opt);contact_corpus.load(ref,'real');corpus.configure(ref,'raw')
                    floor=floor_ref.library(opt);segment_reference.load_real(floor);floor.floor_ref_init()
                    vertex_block=(C.c_void_p*5).in_dll(floor,'mapModel')[3]
                    # First raw query; progress flips, despawn, then attempted resurrection.
                    for frame,progress in enumerate((bits,bits,0x9db1,0,0)):
                        if frame==1:
                            p.motion.actor=Actor(0,1600 if airborne else 1576,-1800,180)
                            p.motion.grounded=not airborne;p.motion.vy=-1100 if airborne else 0
                        q=Player.from_buffer_copy(p)
                        lib.cameraRuntimeSetLearnedAbilities(C.byref(s),progress)
                        ref.bridge_ref_actor(progress)
                        expected=self.expected(ref)
                        self.move(lib,s,p,0,156,180,.05)
                        floor.floor_ref_step((F*3)(*s.pre),56,0x400000,frame&1)
                        self.assertEqual(bytes(s.bridge.floor),floor_ref.snapshot(floor),(opt,bits,airborne,frame))
                        self.assertEqual(s.calls,1)
                        ref.bridge_ref_mesh(F(.05))
                        for vertex in range(134,166):
                            xyz=(C.c_int16*3)();ref.bridge_ref_xyz(1,vertex,xyz)
                            C.memmove(vertex_block+24+16*vertex,xyz,6)
                        if frame==1 and not bits:
                            self.assertFalse(p.motion.grounded)
                            self.assertFalse(p.events&2) # no landing on vanished top
                    self.assertEqual([m.applied for m in s.world_bridge.mesh],[-5000,-5000,0])
                    self.assertEqual(lib.init(C.byref(s),C.byref(p)),1)
                    self.assertEqual([m.applied for m in s.world_bridge.mesh],[0,0,0])

    def test_published_shared_state_takeoff_and_recovery_support_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for bits in (0,0x9db1):
                s,p,ref,want=self.world(opt,lib,bits)
                for mode in ('jump','recovery','orbit'):
                    p=Player(motion=Motion(actor=Actor(0,1576,-1800,180),grounded=True))
                    if mode=='recovery':
                        p.motion.actor=Actor(9000,-1100,9000,180);p.motion.grounded=False
                        p.motion.has_safe=True;p.motion.safe[:]=(0,1576,-1800)
                    q=Player.from_buffer_copy(p)
                    lib.playerRuntimeMove(C.byref(q),0,156,180,.05,mode=='jump',mode=='orbit',
                                          want,self.triangles,len(self.triangles))
                    self.move(lib,s,p,0,156,180,.05,jump=mode=='jump',orbit=mode=='orbit')
                    # Jump/recovery geometry decision remains the D.3B one;
                    # absent support now uses E.1 gravity, not the old jump fall.
                    self.assertEqual(p.events&5,q.events&5,(opt,bits,mode))
                    if mode=='jump':self.assertEqual(bool(p.events&1),bool(bits))
                    if mode=='recovery':self.assertEqual(bool(p.events&4),bool(bits))


if __name__=='__main__':unittest.main()
