"""Actual portable viewer integration: movement -> controller -> VBO XYZ."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT
from test_jump import Motion, Animation, floor, arrays
from test_gait_production import State as GaitState
from test_walk_runtime import Vertex, FIRST, COUNT, TOTAL
from test_movement import Actor, Vertex as FloorVertex, Triangle
from tools.banjo3ds.pose_binding import export_jump_packet
from tools.banjo3ds.floor_collision import scene_collision
from tools.banjo3ds.export_3ds_model import export_scene
from transition_reference import pack

from test_horizontal import State as Horizontal, Metrics
F=C.c_float
class GaitMotion(C.Structure):
    _fields_=[('timer',F),('gait',C.c_uint8)]
class Player(C.Structure):
    _fields_=[('motion',Motion),('gait',GaitState),('jump',Animation),('events',C.c_uint),
              ('speed',F),('accepted',C.c_bool),('jumpActive',C.c_bool),
              ('horizontal',Horizontal),('metrics',Metrics),('locomotion',GaitMotion),
              ('horizontalInitialized',C.c_bool)]

class JumpRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-jump-runtime-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            output=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc','-std=c99',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                *['-I'+str(ROOT/p) for p in ('platform/3ds/source','tools/banjo3ds/pose','tools/banjo3ds/gait','tools/banjo3ds/jump')],
                *[str(ROOT/p) for p in ('tools/banjo3ds/pose/pose.c','tools/banjo3ds/gait/gait.c','tools/banjo3ds/gait/gait_motion.c',
                  'tools/banjo3ds/horizontal/horizontal.c','tools/banjo3ds/jump/jump.c','tools/banjo3ds/jump/jump_animation.c',
                  'platform/3ds/source/movement.c','platform/3ds/source/player_runtime.c')],'-lm','-o',str(output)],check=True)
            lib=C.CDLL(str(output))
            lib.playerRuntimeMove.argtypes=[C.POINTER(Player),F,F,F,F,C.c_bool,C.c_bool,
                C.POINTER(FloorVertex),C.POINTER(Triangle),C.c_size_t]
            lib.playerRuntimeAnimate.argtypes=[C.POINTER(Player),C.c_char_p,C.c_size_t,F]
            lib.playerRuntimeAnimate.restype=C.c_bool
            lib.playerRuntimeWriteVertices.argtypes=[C.POINTER(Player),C.c_char_p,C.c_void_p,C.c_size_t,C.c_size_t,C.c_size_t,C.c_size_t]
            lib.playerRuntimeWriteVertices.restype=C.c_bool
            lib.banjo_gait_update.argtypes=[C.POINTER(GaitState),C.c_char_p,C.c_size_t,C.c_bool,F,F]
            lib.banjo_gait_update.restype=C.c_bool
            cls.libs.append(lib)
        cls.paths=[ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0','034D')]
        cls.anims={a:ROOT/f'assets/anim/{a}.anim.bin' for a in ('0003','006F','0002','000C','0008')}
        cls.packet=export_jump_packet(cls.paths[2],*(cls.anims[a] for a in ('0003','006F','0002','000C','0008')))
        cls.real=arrays(*scene_collision(cls.paths[:2]))
        cls.golden=json.loads((Path(__file__).parent/'fixtures/jump_golden.json').read_text())

    def player(self):return Player(motion=Motion(actor=Actor(0,1800,0,0),grounded=True))
    def tick(self,lib,p,dt=.025,x=0,y=0,jump=False,camera=False,mesh=None,upload=None):
        v,t=self.real if mesh is None else mesh
        lib.playerRuntimeMove(C.byref(p),x,y,0,dt,jump,camera,v,t,len(t))
        self.assertTrue(lib.playerRuntimeAnimate(C.byref(p),self.packet,len(self.packet),dt))
        if upload is not None:self.assertTrue(lib.playerRuntimeWriteVertices(C.byref(p),self.packet,upload,TOTAL,FIRST,COUNT,C.sizeof(Vertex)))

    def test_a_edge_hold_apex_descent_landing_and_rejump(self):
        for lib in self.libs:
            p=self.player();held=False;takeoffs=0;rising=falling=False
            # Exactly as main.c: down contains a press only on held's rising edge.
            for frame in range(100):
                now=True;edge=now and not held;held=now
                self.tick(lib,p,jump=edge)
                takeoffs+=bool(p.events&1)
                rising |= p.motion.vy>0;falling |= p.motion.vy<0
                if frame==0:self.assertFalse(p.motion.grounded);self.assertTrue(p.jumpActive)
            self.assertEqual(takeoffs,1);self.assertTrue(rising and falling)
            self.assertTrue(p.motion.grounded);self.assertFalse(p.jumpActive)
            self.assertEqual((p.motion.actor.y,p.gait.gait),(1800,0))
            self.tick(lib,p,jump=False);self.tick(lib,p,jump=True)
            self.assertTrue(p.events&1);self.assertTrue(p.jumpActive)

    def test_ground_gait_uses_intent_and_physics_metrics(self):
        for lib in self.libs:
            p=self.player()
            for x,camera in [(0,False),(34,False),(75,False),(110,False),(156,False),
                             (145,False),(100,False),(50,False),(0,False),(156,True)]:
                self.tick(lib,p,x=x,camera=camera,mesh=floor(x0=-1000,x1=1000))
                self.assertEqual(p.gait.gait,p.locomotion.gait)
                self.assertFalse(p.jumpActive)
                if camera:self.assertEqual(p.metrics.magnitude,0)

    def test_horizontal_jump_camera_orbit_and_collision_landing_handoff(self):
        for lib in self.libs:
            p=self.player();self.tick(lib,p,x=156);self.tick(lib,p,x=156,jump=True)
            self.assertGreater(p.motion.actor.x,0);self.assertTrue(p.jumpActive)
            before=p.motion.actor.x;vy=p.motion.vy
            self.tick(lib,p,x=156,camera=True)
            self.assertGreater(p.motion.actor.x,before);self.assertLess(p.motion.vy,vy)
            # Land while the animation is still in the first takeoff segment.
            p.motion.actor.y=1900;p.motion.vy=-3000
            mixed=bytes(p.jump.pose.bones)
            self.tick(lib,p,dt=.05,mesh=floor())
            self.assertTrue(p.events&2);self.assertFalse(p.jumpActive)
            self.assertEqual(bytes(p.gait.source),mixed);self.assertEqual(p.gait.gait,0)
            self.assertEqual((p.motion.actor.y,p.motion.vy),(1800,0))
            self.tick(lib,p,x=156,mesh=floor())
            self.assertEqual(p.gait.gait,4);self.assertGreater(p.gait.factor,0)
            # A new takeoff freezes the current interrupted landing/gait blend.
            mixed=bytes(p.gait.pose.bones)
            self.tick(lib,p,jump=True,mesh=floor())
            self.assertEqual(bytes(p.jump.source),mixed)

    def test_reconfirm_ground_rejected_flags_and_steep_floor(self):
        steep=arrays([(0,0,0),(0,100,1),(10,0,0)],[(0,1,2,0,0)])
        for lib in self.libs:
            p=self.player();self.tick(lib,p,jump=True,mesh=floor(flags=0x20000))
            self.assertFalse(p.events&1);self.assertFalse(p.motion.grounded)
            for mesh in (floor(0,flags=0x20000),steep):
                p.motion.actor=Actor(1,50,0,0);p.motion.vy=-2000;p.motion.grounded=False
                self.tick(lib,p,dt=.05,mesh=mesh)
                self.assertFalse(p.events&2);self.assertFalse(p.motion.grounded)

    def test_void_recovery_returns_idle_without_teleport_speed(self):
        for lib in self.libs:
            p=self.player();self.tick(lib,p);self.tick(lib,p,jump=True)
            p.motion.actor.y=-1005;p.motion.vy=-100
            mixed=bytes(p.jump.pose.bones)
            self.tick(lib,p,x=156)
            self.assertTrue(p.events&4);self.assertTrue(p.motion.grounded)
            self.assertEqual((p.motion.actor.x,p.motion.actor.y,p.motion.actor.z),(0,1800,0))
            self.assertFalse(p.accepted);self.assertEqual(p.speed,0)
            self.assertFalse(p.jumpActive);self.assertEqual(p.gait.gait,0)
            self.assertEqual(bytes(p.gait.source),mixed)

    def test_only_actor_xyz_and_goldens_through_real_scatter(self):
        for lib in self.libs:
            vertices=(Vertex*TOTAL)()
            for i,v in enumerate(vertices):v.x=i;v.y=-i;v.z=17;v.u=23;v.v=45;v.rgba[:]=(17,33,65,129)
            original=bytes(vertices);stride=C.sizeof(Vertex);p=self.player()
            self.tick(lib,p,jump=True,upload=vertices)
            for row in self.golden['poses']:
                p.jump.phase=row['phase'];p.jump.segment=2;p.jump.factor=1
                # Sample only: no physics/clock advancement, full ONCE inclusive range.
                self.assertTrue(lib.playerRuntimeAnimate(C.byref(p),self.packet,len(self.packet),0))
                self.assertTrue(lib.playerRuntimeWriteVertices(C.byref(p),self.packet,vertices,TOTAL,FIRST,COUNT,stride))
                self.assertEqual(hashlib.sha256(pack(((v.x,v.y,v.z) for v in vertices[FIRST:FIRST+COUNT]),3)).hexdigest(),row['corners'])
                result=bytes(vertices)
                self.assertEqual(result[:FIRST*stride],original[:FIRST*stride]);self.assertEqual(result[(FIRST+COUNT)*stride:],original[(FIRST+COUNT)*stride:])
                for i in range(FIRST,FIRST+COUNT):self.assertEqual(result[i*stride+12:(i+1)*stride],original[i*stride+12:(i+1)*stride])

    def test_cpu_updates_without_gpu_upload_do_not_lose_jump_event(self):
        for lib in self.libs:
            p=self.player();self.tick(lib,p,jump=True)
            source=bytes(p.jump.source)
            for _ in range(3):self.tick(lib,p)
            self.assertTrue(p.jumpActive);self.assertEqual(bytes(p.jump.source),source)
            self.assertGreater(p.jump.phase,F(.3).value)

    def test_export_map_sort_render_prefix_and_old_v3_unchanged(self):
        kwargs=dict(walk_animation_path=self.anims['0003'],runtime_transitions=True,
                    creep_animation_path=self.anims['0002'],run_animation_path=self.anims['000C'])
        old=export_scene(*self.paths,self.anims['006F'],**kwargs)
        new=export_scene(*self.paths,self.anims['006F'],jump_animation_path=self.anims['0008'],**kwargs)
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),'30bb694ab8cfe7b3d857f9455017bee098105603c441fe8414ab070b721e7a89')
        self.assertEqual(old.split('/* B3P3 v3')[0],new.split('/* B3P3 v4')[0])
        suffix=new.split('/* B3P3 v4')[1]
        self.assertEqual(bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',suffix)),self.packet)
        for name,n in [('VERTEX',12600),('TEXTURE',97),('MATERIAL',469),('DRAW',510),
                       ('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {n}\n',new)
        self.assertEqual(C.sizeof(Player),42644)

    def test_main_uses_press_edge_and_wait_before_vbo_write_then_flush(self):
        source=(ROOT/'platform/3ds/source/main.c').read_text()
        self.assertIn('(down & KEY_A) != 0',source);self.assertNotIn('(held & KEY_A)',source)
        names=['cameraRuntimeMove(&rareCamera, &player','playerRuntimeAnimate(&player','C3D_FrameBegin(C3D_FRAME_SYNCDRAW)',
               'playerRuntimeWriteVertices(&player','GSPGPU_FlushDataCache((Banjo3DSVertex *)vbo_data + BANJO_ACTOR_FIRST_VERTEX']
        positions=[source.index(n) for n in names];self.assertEqual(positions,sorted(positions))
        self.assertIn('movementActorMatrix(&player.motion.actor, rows)',source)
        make=(ROOT/'platform/3ds/Makefile').read_text()
        self.assertIn('assets/anim/0008.anim.bin',make)
        self.assertIn('$(BANJO3DS_RUN_ANIMATION) $(BANJO3DS_JUMP_ANIMATION) --runtime-transitions',make)
