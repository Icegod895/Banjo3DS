"""M4.8C actual runtime hooks + immutable data vs independent B.9 goldens."""
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import floor_bridge_reference as reference
import test_camera as cam
from test_floor_bridge import Bridge
from test_world_segment import Model
from test_jump_runtime import Player
from test_jump import Motion, arrays
from test_movement import Actor, Vertex, Triangle
from floor_state_corpus import canonical
from tools.banjo3ds.export_camera_data import export_camera_data, PACKET_HASHES
from tools.banjo3ds.floor_collision import scene_collision
from tools.banjo3ds.world_query_packet import read_model
from test_renderer_culling import det, debug_rotation, project
from test_camera_contact import Scratch
from test_free_b import PostState
from test_bridge_state import State as BridgeState
from body_corpus import History as BodyHistory
from test_body import Scratch as BodyScratch

class RuntimeModel(Model):
    _fields_=[("bridge_state",C.POINTER(BridgeState))]

ROOT=reference.ROOT
F=C.c_float
from ground_corpus import State as GroundPhase
class GroundRuntime(C.Structure):
    _fields_=[('phase',GroundPhase),('fall_request',C.c_uint32),('jump_flight',C.c_bool)]
class Runtime(C.Structure):
    _fields_=[('math',cam.Math),('camera',cam.State),('bridge',Bridge),('opa',RuntimeModel),('xlu',RuntimeModel),
        ('zoom',C.POINTER(cam.Zoom)),('triggers',C.POINTER(cam.Trigger)),('count',C.c_size_t),
        ('view',(F*4)*4),('pre',F*3),('calls',C.c_uint),('status',C.c_int),('parity',C.c_int),
        ('initialized',C.c_bool),('floor_ready',C.c_bool),('view_ready',C.c_bool),
        ('contact',PostState),('world_bridge',BridgeState),('learned_abilities',C.c_uint32),('player_ground',GroundRuntime),('body',BodyHistory),('scratch',BodyScratch)]


def inputs(name,frame):
    speed={'node_walk':54,'node_exit_jump_landing':156,'free_walk':54,
           'free_jump_landing':-156,'rejected_ground':156,'orbit_ground':156,
           'orbit_air':156,'reinitialize':54,'roundtrip':156}.get(name,0)
    x,y,yaw=(speed,0,0) if name=='free_walk' else (0,speed,0)
    if name.startswith('slope_'):y=156;yaw=-135 if name=='slope_down' else -315
    if name=='roundtrip':y=-156 if frame<120 else 156
    jump=frame==10 and name in ('node_jump_landing','node_exit_jump_landing','free_jump_landing','orbit_air')
    return x,y,yaw,jump


class CameraRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='camera-runtime-');cls.addClassCleanup(cls.tmp.cleanup)
        path=Path(cls.tmp.name)
        cls.header=export_camera_data(ROOT/'assets/model/14CF.model.bin',ROOT/'assets/model/14D0.model.bin',
                                     ROOT/'assets/lvl_setup/071D.lvl_setup.bin')
        (path/'generated_camera.h').write_text(cls.header)
        from tools.banjo3ds.bridge_state.movement_binding import provenance, export_header
        (path/'generated_bridge_movement.h').write_text(export_header(provenance(
            ROOT/'assets/model/14CF.model.bin',ROOT/'assets/model/14D0.model.bin')))
        (path/'wrapper.c').write_text('''#include "camera_runtime.h"
#include "generated_camera.h"
#include "bridge_state/movement_overlay.h"
void movement_read(const FloorVertex *v,unsigned i,const MovementOverlay *o,FloorVertex *out){*out=movementVertex(v,i,o);}
size_t runtime_size(void){return sizeof(CameraRuntime);}
int init(CameraRuntime *s,PlayerRuntime *p){return cameraRuntimeInit(s,p,
 camera_opa_packet,sizeof(camera_opa_packet),camera_xlu_packet,sizeof(camera_xlu_packet),
 &camera_zoom,camera_triggers,CAMERA_TRIGGER_COUNT);}
const void *packet(int n){return n?camera_xlu_packet:camera_opa_packet;}
size_t packet_size(int n){return n?sizeof(camera_xlu_packet):sizeof(camera_opa_packet);}
int runtime_cull(const CameraRuntime *s,unsigned cull){return rendererCullMode(cull,s->parity);}
''')
        sources=['platform/3ds/source/'+s for s in ('camera_runtime.c','player_runtime.c','player_ground.c','movement.c')]
        sources += ['tools/banjo3ds/'+s for s in ('pose/pose.c','gait/gait.c','gait/gait_motion.c',
            'horizontal/horizontal.c','body/body.c','body/frame.c','ground/ground.c','jump/jump.c','jump/jump_animation.c','camera/camera.c',
            'camera_contact/contact.c','camera_contact/free_b.c',
            'world_query/segment.c','world_query/floor_state.c','world_query/floor_bridge.c',
            'bridge_state/bridge.c','bridge_state/query_segment.c','bridge_state/query_contact.c',
            'bridge_state/query_free_b.c','bridge_state/query_floor_state.c','bridge_state/query_floor_bridge.c',
            'bridge_state/render.c','bridge_state/movement_overlay.c')]
        extra_sources=[];extra_flags=[]
        if getattr(cls,'body_observer',False):
            extra_sources=[str(Path(__file__).parent/'body_runtime_observer.c')]
            extra_flags=['-Wl,--wrap='+n for n in ('bp_frame_resolve','bridge_floor_update',
                         'bridge_sphere','bridge_moving','bridge_segment')]
        cls.libs=[]
        includes=['platform/3ds/source','tools/banjo3ds/pose','tools/banjo3ds/gait','tools/banjo3ds/jump',
                  'tools/banjo3ds/camera','tools/banjo3ds/world_query']
        for opt in ('-O0','-O2'):
            out=path/(opt+'.so')
            subprocess.run(['cc',*reference.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *['-I'+str(ROOT/p) for p in includes],'-I'+str(path),'-I'+str(ROOT/'tools/banjo3ds'),
                '-I'+str(Path(os.environ.get('DEVKITPRO','/opt/devkitpro'))/'libctru/include'),
                *[str(ROOT/p) for p in sources],str(path/'wrapper.c'),*extra_sources,*extra_flags,'-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out));cls.libs.append(lib)
            lib.runtime_size.restype=C.c_size_t
            lib.cameraRuntimeSetLearnedAbilities.argtypes=[C.POINTER(Runtime),C.c_uint32]
            lib.cameraRuntimeUpdateView.argtypes=[C.POINTER(Runtime),C.POINTER(cam.Input),C.POINTER(F)]
            lib.banjo_camera_update.argtypes=[C.POINTER(cam.State),C.POINTER(cam.Math),C.POINTER(cam.Zoom),C.POINTER(cam.Trigger),C.c_size_t,C.POINTER(cam.Input)]
            lib.banjo_camera_update.restype=C.c_bool
            lib.init.argtypes=[C.POINTER(Runtime),C.POINTER(Player)]
            lib.cameraRuntimeInit.argtypes=[C.POINTER(Runtime),C.POINTER(Player),C.c_void_p,C.c_size_t,
                C.c_void_p,C.c_size_t,C.POINTER(cam.Zoom),C.POINTER(cam.Trigger),C.c_size_t]
            lib.cameraRuntimeInit.restype=C.c_bool
            lib.packet.argtypes=[C.c_int];lib.packet.restype=C.c_void_p
            lib.packet_size.argtypes=[C.c_int];lib.packet_size.restype=C.c_size_t
            lib.cameraRuntimeMove.argtypes=[C.POINTER(Runtime),C.POINTER(Player),F,F,F,F,C.c_int,
                C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
            lib.bq_bridge_reinit.argtypes=[C.POINTER(Bridge)]
            lib.cameraRareView.argtypes=[C.POINTER(cam.State),C.POINTER(F),C.POINTER(C.c_int)]
            lib.cameraRareView.restype=C.c_bool
            lib.cameraMovementYaw.argtypes=[C.POINTER(cam.State)];lib.cameraMovementYaw.restype=F
            lib.cameraMovementInput.argtypes=[C.POINTER(cam.State),C.c_bool,F,F,F,C.POINTER(F)]
            lib.cameraViFrames.argtypes=[C.c_uint32,C.c_uint32]
            lib.bq_camera_terrain.argtypes=[C.POINTER(Model),C.POINTER(Model),C.POINTER(F),C.POINTER(F)]
            lib.bq_segment.argtypes=[C.POINTER(Model),C.POINTER(Model),C.POINTER(F),C.POINTER(F),C.c_uint32,C.c_void_p]
            lib.runtime_cull.argtypes=[C.POINTER(Runtime),C.c_uint]
            lib.banjo_camera_project.argtypes=[C.POINTER(cam.State),C.POINTER(F),F,F,F,C.POINTER(F)]
            lib.banjo_camera_project.restype=C.c_bool
        cls.vertices,cls.triangles=arrays(*scene_collision([ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0')]))

    def start(self,lib,xyz=(0,1800,0),yaw=0):
        player=Player(motion=Motion(actor=Actor(*xyz,yaw),grounded=True));runtime=Runtime()
        self.assertEqual(lib.runtime_size(),C.sizeof(Runtime))
        self.assertEqual(lib.init(C.byref(runtime),C.byref(player)),1)
        return runtime,player

    def move(self,lib,s,p,x=0,y=0,yaw=0,dt=1/60,vi=1,jump=False,orbit=False):
        return lib.cameraRuntimeMove(C.byref(s),C.byref(p),x,y,yaw,dt,vi,jump,orbit,
                                    self.vertices,self.triangles,len(self.triangles))

    def test_embedded_packet_hashes_alignment_and_borrowed_storage(self):
        for lib in self.libs:
            s,p=self.start(lib)
            for role,model in enumerate((s.opa,s.xlu)):
                address=lib.packet(role);size=lib.packet_size(role)
                self.assertEqual(address%4,0)
                actual=C.string_at(address,size)
                self.assertEqual(hashlib.sha256(actual).hexdigest(),PACKET_HASHES[role])
                expected=read_model(ROOT/f'assets/model/{0x14CF+role:04X}.model.bin',role,0x14CF+role).serialize()
                self.assertEqual(actual,expected)
                self.assertEqual(model.vertices,address+64)
                self.assertEqual(model.collision,address+64+struct.unpack_from('>I',actual,24)[0])

    def test_historical_B9_candidate_goldens_remain_unchanged_O0_O2(self):
        # E.1B intentionally replaces the old player's fail-closed trajectories.
        # Preserve B.9 as its original independent input/reference contract;
        # test_ground_runtime.py checks the new live candidate/provider chain.
        frozen=json.loads((Path(__file__).parent/'fixtures/floor_bridge_golden.json').read_text())
        for opt in ('-O0','-O2'):
            for name,rows in reference.trajectories(opt).items():
                floors=reference.states(rows,opt)
                stream=b''.join(canonical(s) for s in floors)
                self.assertEqual(hashlib.sha256(stream).hexdigest(),frozen['floor'][name]['sha256'])

    def test_startup_empty_frame_and_real_zone_selection(self):
        for lib in self.libs:
            s,p=self.start(lib)
            self.assertEqual((s.bridge.frame,s.bridge.floor.height,s.camera.node),(0,-9000,-1))
            self.assertEqual(self.move(lib,s,p,dt=0),0)
            self.assertEqual((s.bridge.frame,s.calls,s.view_ready),(1,0,False))
            self.assertEqual(self.move(lib,s,p),1)
            self.assertEqual((s.camera.state,s.camera.node,s.calls),(0x11,32,1))
            self.assertEqual(s.bridge.floor.height,1800.0001220703125) # Original query on gravity candidate
            self.assertEqual([lib.runtime_cull(C.byref(s),c) for c in range(4)],[0,1,2,-1])
            # The retained debug boundary supplies NORMAL, never a camera-name switch in draws.
            s.parity=0
            self.assertEqual([lib.runtime_cull(C.byref(s),c) for c in range(4)],[0,2,1,-1])

    def test_view_cardinals_eye_origin_handedness_and_movement_direction(self):
        for lib in self.libs:
            for yaw in (0,90,180,270):
                for pitch in (0,20,340):
                    s=cam.State();s.position[:]=(10,200,30);s.rotation[:]=(pitch,yaw,0)
                    out=(F*16)();parity=C.c_int(-1)
                    self.assertTrue(lib.cameraRareView(C.byref(s),out,C.byref(parity)))
                    rows=[list(out[i*4:i*4+4]) for i in range(4)]
                    self.assertEqual(parity.value,1)
                    self.assertAlmostEqual(det([r[:3] for r in rows[:3]]),-1,places=6)
                    for i in range(3):self.assertAlmostEqual(sum(rows[i][j]*s.position[j] for j in range(3))+rows[i][3],0,places=4)
                    y=math.radians(yaw);p=math.radians(pitch)
                    forward=(-math.cos(p)*math.sin(y),math.sin(p),-math.cos(p)*math.cos(y))
                    self.assertAlmostEqual(sum(rows[2][i]*forward[i] for i in range(3)),1,places=6)
                    direction_yaw=math.radians(lib.cameraMovementYaw(C.byref(s)))
                    self.assertAlmostEqual(-math.sin(direction_yaw),-math.sin(y),places=6)
                    self.assertAlmostEqual(math.cos(direction_yaw),-math.cos(y),places=6)
            s.focus[0]=float('nan');before=bytes(out)
            self.assertFalse(lib.cameraRareView(C.byref(s),out,C.byref(parity)))
            self.assertEqual(bytes(out),before)

    def test_cardinal_input_through_physics_and_projected_screen_O0_O2(self):
        # Freeze the view during the displacement measurement: camera tracking must
        # not hide a wrong input basis. Use real plateau collision and actual runtime.
        for lib in self.libs:
            for debug in (False,True):
                for yaw in (0,90,180,270):
                    for x,y in ((0,156),(0,-156),(-156,0),(156,0)):
                        with self.subTest(debug=debug,yaw=yaw,pad=(x,y)):
                            camera=cam.State();camera.rotation[:]=(340,yaw,0)
                            adapted=(F*3)()
                            lib.cameraMovementInput(C.byref(camera),debug,yaw,x,y,adapted)
                            if debug:self.assertEqual(list(adapted),[x,y,yaw])
                            out=(F*16)();parity=C.c_int()
                            self.assertTrue(lib.cameraRareView(C.byref(camera),out,C.byref(parity)))
                            rows=debug_rotation(-20,yaw) if debug else [list(out[i*4:i*4+3]) for i in range(3)]
                            # Independent world direction from the view's right and
                            # horizontal forward, NOT the adapter's yaw formula.
                            direction=[x*rows[0][j]+y*rows[2][j]/math.cos(math.radians(20)) for j in (0,2)]
                            heading=math.degrees(math.atan2(direction[0],direction[1]))
                            runtime,player=self.start(lib,yaw=heading)
                            for _ in range(8):self.move(lib,runtime,player,*adapted)
                            delta=(player.motion.actor.x,player.motion.actor.y-1800,player.motion.actor.z)
                            q=[sum(rows[i][j]*delta[j] for j in range(3)) for i in range(3)]
                            # Citro3D tilt then physical landscape orientation.
                            before=project((0,0,1000),not debug)
                            after=project((q[0],q[1],1000+q[2]),not debug)
                            screen=(-after[1]+before[1],after[0]-before[0])
                            if x:self.assertGreater(screen[0]*x,0)
                            else:
                                self.assertGreater(screen[1]*y,0)
                                self.assertGreater(q[2]*y,0)
                            self.assertGreater(delta[0]*direction[0]+delta[2]*direction[1],0)
                            # Takeoff uses exactly the same adapted basis; vertical
                            # motion must not mask a lateral steering regression.
                            runtime,player=self.start(lib,yaw=heading)
                            self.move(lib,runtime,player,*adapted,jump=True)
                            delta=(player.motion.actor.x,player.motion.actor.z)
                            self.assertGreater(sum(a*b for a,b in zip(delta,direction)),0)
                            self.assertAlmostEqual(math.hypot(*delta)*60,500,delta=.01)
                            # Suppressed intent ignores either basis, including in air.
                            a,b=self.start(lib,yaw=heading),self.start(lib,yaw=heading)
                            self.move(lib,*a,*adapted,orbit=True)
                            self.move(lib,*b,0,0,adapted[2],orbit=True)
                            self.assertEqual(bytes(a[1]),bytes(b[1]))

    def test_view_perspective_matches_original_XY_with_only_Citro3D_tilt(self):
        for lib in self.libs:
            for pitch,yaw in ((0,0),(0,90),(340,180),(20,145),(70,270)):
                s=cam.State();s.position[:]=(10,200,30);s.rotation[:]=(pitch,yaw,0)
                out=(F*16)();parity=C.c_int()
                self.assertTrue(lib.cameraRareView(C.byref(s),out,C.byref(parity)))
                rows=[list(out[i*4:i*4+4]) for i in range(4)]
                for aspect in (1.35185182,400/240):
                    aspect=F(aspect).value
                    for dx,dy in ((0,0),(100,50),(-80,120)):
                        world=(F*3)(*[s.position[j]+700*rows[2][j]+dx*rows[0][j]+dy*rows[1][j] for j in range(3)])
                        want=(F*3)()
                        self.assertTrue(lib.banjo_camera_project(C.byref(s),world,aspect,10,20000,want))
                        q=[sum(rows[i][j]*world[j] for j in range(3))+rows[i][3] for i in range(3)]
                        cot=1/math.tan(math.radians(40)/2)
                        tilted=(cot*q[1]/q[2],-cot*q[0]/(aspect*q[2]))
                        self.assertAlmostEqual(tilted[0],want[1],delta=2e-6*max(1,abs(want[1])))
                        self.assertAlmostEqual(tilted[1],-want[0],delta=2e-6*max(1,abs(want[0])))

    def test_vi_clock_is_separate_wraps_and_caps(self):
        for lib in self.libs:
            for a,b,n in ((0,0,1),(1,0,1),(2,0,2),(10,0,10),(20,0,15),(1,0xffffffff,2)):
                self.assertEqual(lib.cameraViFrames(a,b),n)

    def test_explicit_query_failure_and_no_hit_not_debug_fallback(self):
        from test_world_segment import Hit
        for lib in self.libs:
            s,p=self.start(lib);self.assertEqual(self.move(lib,s,p),1)
            # Entire grid exceeds the original 100-cell bound: explicit failure.
            start=(F*3)(-5000,-1000,-5000);end=(F*3)(5000,5000,5000);out=Hit()
            self.assertEqual(lib.bq_segment(C.byref(s.opa),C.byref(s.xlu),start,end,0,C.byref(out)),-1)
            # Ordinary miss is data, not an error or a debug-camera selection.
            xyz=(F*3)(15000,3000,15000);height=F()
            self.assertEqual(lib.bq_camera_terrain(C.byref(s.opa),C.byref(s.xlu),xyz,C.byref(height)),0)
            self.assertEqual(height.value,2400)
            old=bytes(s.camera);s.camera.position[0]=float('nan');invalid=bytes(s.camera)
            self.assertEqual(self.move(lib,s,p),-1)
            self.assertEqual(bytes(s.camera),invalid);self.assertEqual(s.parity,1)
            self.assertNotEqual(old,invalid)

    def test_unsupported_real_trigger_holds_last_published_camera_and_view(self):
        from tools.banjo3ds.camera.setup import read_spiral_camera
        data=read_spiral_camera(ROOT/'assets/lvl_setup/071D.lvl_setup.bin')
        trigger=next(t for t in data['triggers'] if t['node']==12 and t['mask']&1)
        for lib in self.libs:
            s,p=self.start(lib);self.assertEqual(self.move(lib,s,p),1)
            # Supply an unsupported retained query position, without inventing a mode.
            # Airborne stable=false preserves this probe, as in the proven API.
            s.camera.stable_position[:]=trigger['position'];p.motion.grounded=False
            before=bytes(s.camera);view=bytes(s.view);frame=s.bridge.frame
            self.assertEqual(self.move(lib,s,p,dt=0),-2)
            self.assertEqual(bytes(s.camera),before);self.assertEqual(bytes(s.view),view)
            self.assertEqual((s.calls,s.bridge.frame,s.parity),(0,frame+1,1))

    def test_packet_validation_precedes_runtime_queries(self):
        for lib in self.libs:
            s,p=self.start(lib)
            bad=C.create_string_buffer(C.string_at(lib.packet(0),lib.packet_size(0)))
            bad[0]=b'X'
            failed=Runtime()
            self.assertFalse(lib.cameraRuntimeInit(C.byref(failed),C.byref(p),bad,lib.packet_size(0),
                lib.packet(1),lib.packet_size(1),s.zoom,s.triggers,s.count))
            self.assertFalse(failed.initialized)
            self.assertEqual(self.move(lib,failed,p),-3)
            self.assertEqual(failed.bridge.frame,0)
