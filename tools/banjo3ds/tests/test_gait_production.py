"""Host C gait/controller and v3 packet against independent frozen goldens."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT
from gait_reference import ClipReference, CLIPS, SPEEDS, policy_duration
from test_walk_pose import Pose
from transition_reference import pack
from tools.banjo3ds.pose_binding import export_gait_packet, export_transition_packet

F=C.c_float
Bones=(F*10)*109
GAITS={'IDLE':0,'CREEP':1,'SLOW':2,'WALK':3,'FAST':4}
CLIP_IDS={'0003':0,'006F':1,'0002':2,'000C':3}
class State(C.Structure):
    _fields_=[('pose',Pose),('source',Bones),('phase',F),('factor',F),('gait',C.c_uint8),('initialized',C.c_bool)]
def digest(values,width):return hashlib.sha256(pack(values,width)).hexdigest()
def adjacent(value,offset):
    bits=struct.unpack('I',struct.pack('f',value))[0]
    return struct.unpack('f',struct.pack('I',bits+offset))[0]

class GaitProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-gait-host-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            path=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc','-std=c99',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                '-I'+str(ROOT/'tools/banjo3ds/pose'),
                str(ROOT/'tools/banjo3ds/pose/pose.c'),str(ROOT/'tools/banjo3ds/gait/gait.c'),'-lm','-o',str(path)],check=True)
            lib=C.CDLL(str(path))
            lib.banjo_pose_sample.argtypes=[C.c_char_p,C.c_size_t,C.c_int,F,C.POINTER(F*10)]
            lib.banjo_pose_sample.restype=C.c_bool
            lib.banjo_pose_apply.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(Pose)]
            lib.banjo_pose_apply.restype=C.c_bool
            lib.banjo_gait_select.argtypes=[C.c_int,C.c_bool,F];lib.banjo_gait_select.restype=C.c_int
            lib.banjo_gait_duration.argtypes=[C.c_int,F];lib.banjo_gait_duration.restype=F
            lib.banjo_gait_start_phase.argtypes=[C.c_int,C.c_int,F];lib.banjo_gait_start_phase.restype=F
            lib.banjo_gait_update.argtypes=[C.POINTER(State),C.c_char_p,C.c_size_t,C.c_bool,F,F]
            lib.banjo_gait_update.restype=C.c_bool
            cls.libs.append(lib)
        cls.paths=[ROOT/'assets/model/034D.model.bin']+[ROOT/f'assets/anim/{c}.anim.bin' for c in ('0003','006F','0002','000C')]
        cls.packet=export_gait_packet(*cls.paths)
        cls.corners=struct.unpack_from('>2085H',cls.packet,36+960+5784)
        cls.golden=json.loads((Path(__file__).parent/'fixtures/gait_golden.json').read_text())

    def seed(self,lib,gait,phase):
        s=State();s.gait=GAITS[gait];s.initialized=True;s.phase=phase;s.factor=1
        self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),CLIP_IDS[CLIPS[gait]],phase,s.pose.bones))
        self.assertTrue(lib.banjo_pose_apply(self.packet,len(self.packet),C.byref(s.pose)))
        return s

    def update(self,lib,s,gait,dt):
        self.assertTrue(lib.banjo_gait_update(C.byref(s),self.packet,len(self.packet),gait!='IDLE',SPEEDS[gait],dt))
        self.assertEqual(s.gait,GAITS[gait])

    def check_pose(self,pose,row):
        self.assertEqual(digest(pose.bones,10),row['bones'])
        self.assertEqual(digest(([v for r in m for v in r] for m in pose.matrices),16),row['matrices'])
        self.assertEqual(digest(pose.xyz,3),row['loads'])
        self.assertEqual(digest((pose.xyz[i] for i in self.corners),3),row['corners'])

    def check_state(self,s,row):
        self.assertEqual(s.phase,row['phase']);self.assertEqual(s.factor,row['factor'])
        self.assertEqual(digest(s.source,10),row['source_hash'])
        self.check_pose(s.pose,row)

    def test_all_new_pose_goldens_O0_O2(self):
        for lib in self.libs:
            for clip,rows in self.golden['poses'].items():
                for row in rows:
                    with self.subTest(clip=clip,phase=row['phase']):
                        pose=Pose()
                        self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),CLIP_IDS[clip],row['phase'],pose.bones))
                        self.assertTrue(lib.banjo_pose_apply(self.packet,len(self.packet),C.byref(pose)))
                        self.check_pose(pose,row)

    def test_all_transition_goldens_with_real_controller_O0_O2(self):
        for lib in self.libs:
            for name,case in self.golden['transitions'].items():
                s=self.seed(lib,case['source_gait'],case['source_phase'])
                for i,row in enumerate(case['rows']):
                    with self.subTest(case=name,step=i):
                        self.update(lib,s,case['destination_gait'],0 if i==0 else .025)
                        self.check_state(s,row)
                frozen=bytes(s.source)
                self.update(lib,s,case['destination_gait'],.025)
                expected=ClipReference(CLIPS[case['destination_gait']]).transforms(s.phase)[0]
                self.assertEqual(bytes(s.source),frozen)
                self.assertEqual(pack(s.pose.bones,10),pack(expected,10))
                self.assertEqual(s.factor,1)

    def test_interrupted_transition_uses_current_mixed_pose_and_phase(self):
        for lib in self.libs:
            s=self.seed(lib,'CREEP',.37)
            for _ in range(3):self.update(lib,s,'SLOW',.025)
            self.check_state(s,self.golden['interruption']['at'])
            mixed=bytes(s.pose.bones)
            for i,row in enumerate(self.golden['interruption']['rows']):
                self.update(lib,s,'WALK',0 if i==0 else .025)
                self.check_state(s,row);self.assertEqual(bytes(s.source),mixed)

    def test_walk_fast_is_rate_only_including_mid_transition(self):
        for lib in self.libs:
            for inflight in (False,True):
                s=self.seed(lib,'WALK',.37)
                if inflight:
                    s=self.seed(lib,'SLOW',.37);self.update(lib,s,'WALK',.025)
                phase,factor,source,pose=s.phase,s.factor,bytes(s.source),bytes(s.pose)
                self.update(lib,s,'FAST',0)
                self.assertEqual((s.phase,s.factor,bytes(s.source),bytes(s.pose)),(phase,factor,source,pose))
                self.update(lib,s,'FAST',.025)
                self.assertEqual(s.phase,F(phase+F(F(.025).value/F(.44).value).value).value)
                self.assertEqual(bytes(s.source),source)
                phase,factor,pose=s.phase,s.factor,bytes(s.pose)
                self.update(lib,s,'WALK',0)
                self.assertEqual((s.phase,s.factor,bytes(s.source),bytes(s.pose)),(phase,factor,source,pose))

    def test_nominal_bands_stop_and_large_jumps(self):
        samples=[(0,0),(1,1),(30,1),(adjacent(30,1),2),(75,2),
                 (adjacent(75,1),3),(112.5,3),(adjacent(112.5,1),4),(150,4),(300,4)]
        for lib in self.libs:
            for speed,expected in samples:self.assertEqual(lib.banjo_gait_select(0,True,speed),expected)
            for current in range(5):
                for accepted,speed in ((False,150),(True,0),(True,-1),(True,float('nan'))):
                    self.assertEqual(lib.banjo_gait_select(current,accepted,speed),0)
            self.assertEqual(lib.banjo_gait_select(1,True,150),4)
            self.assertEqual(lib.banjo_gait_select(4,True,1),1)

    def test_hysteresis_strict_float32_boundaries(self):
        # Banjo3DS policy, not Rare behavior. Search adjacent representable
        # speed inputs: division by 150 can map several to the same strength.
        for lib in self.libs:
            for lower,b in enumerate((.2,.5,.75),1):
                for shift in (-1,1):
                    threshold=F(F(b).value+shift*F(.02).value).value
                    near=F(threshold*150).value
                    samples=[adjacent(near,i) for i in range(-8,9)]
                    relations=set()
                    for speed in samples:
                        strength=F(speed/150).value
                        relations.add((strength>threshold)-(strength<threshold))
                        current=lower if shift==1 else lower+1
                        expected=(lower+1 if strength>threshold else lower) if shift==1 else (lower if strength<threshold else lower+1)
                        self.assertEqual(lib.banjo_gait_select(current,True,speed),expected)
                    self.assertEqual(relations,{-1,0,1})

    def test_duration_endpoints_neighbors_and_hysteresis_bands(self):
        for lib in self.libs:
            for name,lo,hi in [('CREEP',0,30),('SLOW',30,75),('WALK',75,112.5),('FAST',112.5,150)]:
                speeds=[lo,hi,(lo+hi)/2,lo-3,lo+3,hi-3,hi+3]
                speeds += [adjacent(v,offset) for v in (lo,hi) if v>0 for offset in (-1,1)]
                for speed in speeds:
                    self.assertEqual(lib.banjo_gait_duration(GAITS[name],speed),policy_duration(name,speed))
                    self.assertTrue(.3<=lib.banjo_gait_duration(GAITS[name],speed)<=1.5)
            self.assertEqual(lib.banjo_gait_duration(0,150),5.5)

    def test_phase_rule_table_all_gait_pairs(self):
        preserve={(2,1),(3,2),(2,3),(4,3),(3,4)}
        for lib in self.libs:
            for old in range(5):
                for new in range(5):
                    expected=F(.37).value if old==new or (old,new) in preserve else 0
                    self.assertEqual(lib.banjo_gait_start_phase(old,new,.37),expected)

    def test_packet_state_sizes_and_no_binding_or_legacy_packet_change(self):
        old=export_transition_packet(*self.paths[:3])
        self.assertEqual(len(old),24398);self.assertEqual(len(self.packet),26234)
        self.assertEqual(C.sizeof(State),21248)
        self.assertEqual(self.packet[32:len(old)],old[32:])
        self.assertEqual(struct.unpack_from('>HH',self.packet,28),(888,948))
        self.assertEqual(self.packet[len(old):],self.paths[3].read_bytes()+self.paths[4].read_bytes())
        self.assertEqual(len(self.corners),2085);self.assertEqual(set(self.corners),set(range(723)))
        for lib in self.libs:
            for clip in (0,1):
                for phase in (0,.25,.5,.75,1):
                    a,b=Bones(),Bones()
                    self.assertTrue(lib.banjo_pose_sample(old,len(old),clip,phase,a))
                    self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),clip,phase,b))
                    self.assertEqual(bytes(a),bytes(b))

    def test_initial_idle_stop_and_dt_clamp(self):
        for lib in self.libs:
            s=State();self.update(lib,s,'IDLE',0)
            self.assertEqual(pack(s.pose.bones,10),pack(ClipReference('006F').transforms(0)[0],10))
            self.assertEqual((s.phase,s.factor),(0,1))
            a=State.from_buffer_copy(s);b=State.from_buffer_copy(s)
            self.update(lib,a,'FAST',.05);self.update(lib,b,'FAST',1.)
            self.assertEqual(bytes(a),bytes(b))
            frozen=bytes(a.pose.bones)
            # Rejected high-speed input still selects idle; factor zero is exact.
            self.assertTrue(lib.banjo_gait_update(C.byref(a),self.packet,len(self.packet),False,150,0))
            self.assertEqual((a.gait,a.phase,a.factor),(0,0,0))
            self.assertEqual(bytes(a.source),frozen);self.assertEqual(bytes(a.pose.bones),frozen)

    def test_invalid_packets_and_dt_are_rejected(self):
        packets=[self.packet[:-1],self.packet+b'\0']
        for offset in (4,28,30,24398+3):
            bad=bytearray(self.packet);bad[offset]^=1;packets.append(bytes(bad))
        for lib in self.libs:
            for packet in packets:
                self.assertFalse(lib.banjo_pose_sample(packet,len(packet),2,0,Bones()))
            s=State()
            for dt in (-1,float('nan')):
                self.assertFalse(lib.banjo_gait_update(C.byref(s),self.packet,len(self.packet),True,150,dt))
                self.assertEqual(bytes(s),bytes(State()))

if __name__=='__main__':unittest.main()
