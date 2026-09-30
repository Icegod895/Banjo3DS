"""M4.8B: production C vs independently compiled original camera functions."""
import ctypes as C
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from camera_reference import (ROOT, ASSET, F, FLAGS, FIELDS, CASES, setup,
                              library, initial, commands, snapshot, pack, golden, projection_points)

spec=importlib.util.spec_from_file_location('camera_setup',ROOT/'tools/banjo3ds/camera/setup.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)

class State(C.Structure):
    _fields_=[(name,F*3) for name in ('position','rotation','focus','lead','position_step','angular_step','stable_position')]+[
        ('orbit_yaw',F),('mode',C.c_int),('state',C.c_int),('node',C.c_int),('preset',C.c_int)]
class Math(C.Structure):_fields_=[('table',C.c_uint16*10001)]
class Zoom(C.Structure):
    _fields_=[('anchor',F*3),('offset',F*3),('pg',F*2),('ag',F*2),('close',F),('far',F),('flags',C.c_uint32)]
class Trigger(C.Structure):
    _fields_=[('position',C.c_int*3),('radius',C.c_int),('node',C.c_int),('mask',C.c_int)]
class Input(C.Structure):
    _fields_=[('player',F*3),('floor',F),('yaw',F),('under',F),('dt',F),('vi',C.c_int),('stable',C.c_bool)]

def values(s):return list(struct.unpack('=22f4i',bytes(s)))
def make_input(c):return Input((F*3)(*c['player']),c['floor'],c['yaw'],c['under'],c['dt'],c['vi'],c['stable'])

class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-camera-test-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                str(ROOT/'tools/banjo3ds/camera/camera.c'),'-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out));fp=C.POINTER(F)
            for name,args,result in (
                ('math_init',[C.POINTER(Math)],None),
                ('init',[C.POINTER(State),C.POINTER(Math),C.POINTER(Input),fp,fp],None),
                ('update',[C.POINTER(State),C.POINTER(Math),C.POINTER(Zoom),C.POINTER(Trigger),C.c_size_t,C.POINTER(Input)],C.c_bool),
                ('project',[C.POINTER(State),fp,F,F,F,fp],C.c_bool)):
                fn=getattr(lib,'banjo_camera_'+name);fn.argtypes=args;fn.restype=result
            cls.libs.append(lib)
        cls.data=reader.read_spiral_camera(ASSET)
        z=cls.data['zoom'];cls.zoom=Zoom((F*3)(*z[:3]),(F*3)(*z[3:6]),(F*2)(*z[6:8]),(F*2)(*z[8:10]),*z[10:])
        cls.triggers=(Trigger*len(cls.data['triggers']))(*[
            Trigger((C.c_int*3)(*t['position']),t['radius'],t['node'],t['mask']) for t in cls.data['triggers']])

    def init(self,lib,ref,case='free_stationary'):
        m=Math();lib.banjo_camera_math_init(C.byref(m))
        p,eye,rot=initial(case);s=State();cmd=dict(player=p,floor=1800,yaw=0,under=1800,dt=1/60,vi=1,stable=True)
        lib.banjo_camera_init(C.byref(s),C.byref(m),C.byref(make_input(cmd)),(F*3)(*eye),(F*3)(*rot))
        records,z=setup();raw=[v for r in records for v in r[1:]]
        ref.ref_setup((C.c_int*len(raw))(*raw),len(records),(F*12)(*z[:12]))
        ref.ref_init((F*3)(*p),1800,(F*3)(*eye),(F*3)(*rot))
        self.assertEqual(bytes(m),bytes((C.c_uint16*10001).in_dll(ref,'lookup')))
        self.same(s,ref)
        return s,m

    def same(self,s,ref,label=''):
        expected,ids=snapshot(ref);actual=values(s)
        self.assertEqual(pack(actual[:22],actual[22:]),pack(expected,ids),
                         (label,[(k,a,b) for k,a,b in zip(FIELDS+['mode','state','node','preset'],actual,expected+ids) if a!=b]))

    def step(self,lib,ref,s,m,cmd,label=''):
        s.preset=cmd.get('preset',2)
        self.assertTrue(lib.banjo_camera_update(C.byref(s),C.byref(m),C.byref(self.zoom),self.triggers,len(self.triggers),C.byref(make_input(cmd))),label)
        ref.ref_step((F*3)(*cmd['player']),cmd['floor'],cmd['yaw'],cmd['under'],cmd['dt'],cmd['vi'],cmd['stable'],s.preset)
        self.same(s,ref,label)

    def test_asset_parser_independent_records_and_exact_node32(self):
        records,z=setup()
        self.assertEqual(self.data['zoom'],z)
        self.assertEqual([(r['offset'],*r['position'],r['radius'],r['node'],r['mask']) for r in self.data['triggers']],records)
        self.assertEqual(len(records),150)
        self.assertEqual(self.data['section'],0x1df0)
        self.assertEqual(self.data['nodes'][32]['offset'],0x2491)
        self.assertEqual(z[10:12],(1251.,1251.));self.assertEqual(z[12]&1,0)
        self.assertIn((0x11ba,25,1925,-18,443,32,1),records)

    def test_original_goldens_and_O0_O2(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/camera_golden.json').read_text())
        for opt in ('-O0','-O2'):self.assertEqual(golden(opt),fixture)

    def test_all_production_traces_bit_exact_O0_O2(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/camera_golden.json').read_text())
        for lib,opt in zip(self.libs,('-O0','-O2')):
            ref=library(opt)
            for case in CASES:
                s,m=self.init(lib,ref,case);stream=[]
                for frame,cmd in enumerate(commands(case),1):
                    self.step(lib,ref,s,m,cmd,(case,frame,opt))
                    v=values(s);stream.append(pack(v[:22],v[22:]))
                    checkpoint=fixture['cases'][case]['checkpoints'].get(str(frame))
                    if checkpoint:
                        index=0
                        for aspect in (F(1.35185182).value,F(400/240).value):
                            for point in projection_points(cmd['player']):
                                out=(F*3)()
                                valid=lib.banjo_camera_project(C.byref(s),(F*3)(*point),aspect,10,20000,out)
                                expected=checkpoint['projected'][index];index+=1
                                self.assertEqual(valid,bool(expected[0]))
                                if valid:
                                    for a,b in zip(out,expected[1:]):self.assertAlmostEqual(a,b,delta=2e-6*max(1,abs(b)))
                self.assertEqual(hashlib.sha256(b''.join(stream)).hexdigest(),fixture['cases'][case]['sha256'])

    def test_zone_exit_delay_return_and_jump_probe(self):
        for lib in self.libs:
            ref=library();s,m=self.init(lib,ref,'node_stationary')
            cmd=next(commands('node_stationary'))
            self.step(lib,ref,s,m,cmd);self.assertEqual((s.mode,s.state,s.node),(9,17,32))
            probe=list(s.stable_position)
            cmd.update(player=[0,2200,800],stable=False)
            self.step(lib,ref,s,m,cmd);self.assertEqual(s.node,32);self.assertEqual(list(s.stable_position),probe)
            cmd.update(player=[0,1800,800],stable=True)
            self.step(lib,ref,s,m,cmd);self.assertEqual((s.mode,s.state,s.node),(2,17,-1))
            self.step(lib,ref,s,m,cmd);self.assertEqual(s.state,11)
            cmd['player']=[0,1800,0]
            self.step(lib,ref,s,m,cmd);self.assertEqual((s.mode,s.state,s.node),(9,17,32))

    def test_vertical_threshold_visible_yaw_and_preserved_orbit(self):
        for lib in self.libs:
            ref=library();s,m=self.init(lib,ref);orbit=s.orbit_yaw
            cmd=next(commands('free_stationary'));cmd.update(stable=False,yaw=90)
            boundary_bits=struct.unpack('>I',struct.pack('>f',1930.))[0]
            for y in (1800.,1930.,struct.unpack('>f',struct.pack('>I',boundary_bits+1))[0],1931.,1980.,1800.):
                cmd['player']=[0,y,600];self.step(lib,ref,s,m,cmd)
                self.assertEqual(s.focus[1],1880+max(y-1930,0))
                self.assertEqual(s.orbit_yaw,orbit)
            self.assertGreater(s.lead[0],0)

    def test_profiles_timing_and_overshoot_accumulators(self):
        for lib in self.libs:
            ref=library();s,m=self.init(lib,ref)
            cmd=next(commands('free_stationary'))
            for preset in (1,2,3):
                for dt,vi in ((0,1),(1/60,1),(1/30,2),(.05,3),(.05,15)):
                    cmd.update(preset=preset,dt=dt,vi=vi,yaw=180,under=2400)
                    self.step(lib,ref,s,m,cmd,(preset,dt,vi))
            for i in range(3):s.position_step[i]=10000;s.angular_step[i]=100
            ref.ref_seed(s.position_step,s.angular_step)
            cmd.update(under=1800,dt=.05,vi=1)
            self.step(lib,ref,s,m,cmd,'overshoot')

    def test_trigger_integer_truncation_edges_and_unsupported_zones(self):
        lib=self.libs[0];ref=library();s,m=self.init(lib,ref,'node_stationary')
        # Isolate the actual 0x11BA trigger, to probe strict radial/vertical edges.
        t=Trigger((C.c_int*3)(25,1925,-18),443,32,1)
        for p,want in (([25,1775,-18],32),([25,2074.99,-18],32),([25,2075,-18],-1),
                       ([467.99,1925,-18],32),([468,1925,-18],-1)):
            cmd=dict(player=p,floor=1800,yaw=0,under=1800,dt=1/60,vi=1,stable=True)
            self.assertTrue(lib.banjo_camera_update(C.byref(s),C.byref(m),C.byref(self.zoom),C.byref(t),1,C.byref(make_input(cmd))))
            self.assertEqual(s.node,want)
        before=bytes(s);t.node=9;t.position[:]=[0,1800,0]
        cmd['player']=[0,1800,0]
        self.assertFalse(lib.banjo_camera_update(C.byref(s),C.byref(m),C.byref(self.zoom),C.byref(t),1,C.byref(make_input(cmd))))
        self.assertEqual(bytes(s),before)

    def test_projection_known_points_aspects_and_handedness(self):
        for lib in self.libs:
            ref=library();s=State();out=(F*3)();oracle=(F*3)()
            for aspect in (F(1.35185182).value,F(400/240).value):
                self.assertTrue(lib.banjo_camera_project(C.byref(s),(F*3)(0,0,-100),aspect,10,20000,out))
                self.assertEqual(list(out[:2]),[0,0])
                for rot in ((0,0,0),(340,180,0),(327.7,45,0)):
                    s.rotation[:]=rot;s.position[:]=[20,60,40]
                    for point in ((0,0,-1000),(0,0,1000),(100,80,0)):
                        a=lib.banjo_camera_project(C.byref(s),(F*3)(*point),aspect,10,20000,out)
                        b=ref.ref_project(s.position,s.rotation,(F*3)(*point),aspect,10,20000,oracle)
                        self.assertEqual(a,bool(b))
                        if a:
                            for x,y in zip(out,oracle):self.assertAlmostEqual(x,y,delta=2e-6*max(1,abs(y)))
                # Identity RH sees -Z; LH flips view Z, projection uses w=+Z.
                s=State();p=(F*3)(10,20,-100)
                lib.banjo_camera_project(C.byref(s),p,aspect,10,20000,out)
                cot=1/math.tan(math.radians(20));lh=(10,20,100)
                self.assertAlmostEqual(out[0],cot/aspect*lh[0]/lh[2],places=6)
                self.assertAlmostEqual(out[1],cot*lh[1]/lh[2],places=6)
                for depth,expected_z in ((10.,-1.),(20000.,1.)):
                    lib.banjo_camera_project(C.byref(s),(F*3)(0,0,-depth),aspect,10,20000,out)
                    self.assertAlmostEqual(out[2],expected_z,places=6)
                lib.banjo_camera_project(C.byref(s),(F*3)(0,100*math.tan(math.radians(20)),-100),aspect,10,20000,out)
                self.assertAlmostEqual(out[1],1.,places=6)
            self.assertFalse(lib.banjo_camera_project(C.byref(s),(F*3)(0,0,100),1,10,20000,out))

    def test_invalid_time_preserves_state(self):
        lib=self.libs[0];ref=library();s,m=self.init(lib,ref);cmd=next(commands('free_stationary'))
        before=bytes(s)
        for dt,vi in ((-.01,1),(.051,1),(float('nan'),1),(.01,0),(.01,16)):
            cmd.update(dt=dt,vi=vi)
            self.assertFalse(lib.banjo_camera_update(C.byref(s),C.byref(m),C.byref(self.zoom),self.triggers,len(self.triggers),C.byref(make_input(cmd))))
            self.assertEqual(bytes(s),before)

    def test_zoom_anchor_degeneracy_and_collision_not_silently_enabled(self):
        for lib in self.libs:
            ref=library();s,m=self.init(lib,ref,'node_stationary');cmd=next(commands('node_stationary'))
            self.step(lib,ref,s,m,cmd)
            cmd['stable']=False
            for distance in (149.,150.,0.):
                cmd['player']=[self.zoom.anchor[0]+distance,1800,self.zoom.anchor[2]]
                self.step(lib,ref,s,m,cmd,('anchor distance',distance))
            z=Zoom.from_buffer_copy(self.zoom);z.flags|=1;before=bytes(s)
            self.assertFalse(lib.banjo_camera_update(C.byref(s),C.byref(m),C.byref(z),self.triggers,len(self.triggers),C.byref(make_input(cmd))))
            self.assertEqual(bytes(s),before)

if __name__=='__main__':unittest.main()
