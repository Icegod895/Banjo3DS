"""M4.7B.5: preserve one-query semantics; ordered, atomic long floor updates."""
import ctypes as C
import math
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

import floor_step_reference as ref
from test_movement import Vertex, Triangle, Actor

F=C.c_float

def arrays(v,t):
    return (Vertex*len(v))(*(Vertex(*x) for x in v)),(Triangle*len(t))(*(Triangle(*x) for x in t))

def ramp(slope=0,low=-100,high=100,z0=-100,z1=100,offset=0,flags=0):
    return [(low,round(offset+low*slope),z0),(low,round(offset+low*slope),z1),
            (high,round(offset+high*slope),z0),(high,round(offset+high*slope),z1)],[(0,1,2,0,flags),(2,1,3,0,flags)]

def combine(*meshes):
    v,t=[],[]
    for vv,tt in meshes:
        base=len(v);v.extend(vv);t.extend((a+base,b+base,c+base,s,f) for a,b,c,s,f in tt)
    return v,t

class FloorSteppingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-floor-stepping-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc','-std=c99',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                str(ref.ROOT/'platform/3ds/source/movement.c'),'-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out))
            lib.movementFloor.argtypes=[C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t,F,F,F,C.POINTER(F)]
            lib.movementFloor.restype=C.c_bool
            # This symbol is intentionally required only by the fix tests,
            # allowing the original regression to be run before implementation.
            if hasattr(lib,'movementFollowFloor'):
                lib.movementFollowFloor.argtypes=[C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t,F,F,F,F,F,C.POINTER(F)]
                lib.movementFollowFloor.restype=C.c_bool
            lib.movementUpdate.argtypes=[C.POINTER(Actor),F,F,F,F,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
            lib.movementUpdate.restype=C.c_bool
            cls.libs.append(lib)
        cls.real=ref.read_14cf()
        cls.real_arrays=arrays(*cls.real)

    def query(self,lib,mesh,x,z,y):
        v,t=mesh;out=F(-12345)
        ok=lib.movementFloor(v,t,len(t),x,z,y,C.byref(out))
        return ok,out.value

    def follow(self,lib,mesh,start,end):
        v,t=mesh;out=F(-12345)
        ok=lib.movementFollowFloor(v,t,len(t),*start,*end,C.byref(out))
        return ok,out.value

    def test_record_1196_original_failure_independent_fixture(self):
        vertices,records=self.real
        self.assertEqual(records[1196],ref.RECORD_1196)
        self.assertEqual(tuple(vertices[i] for i in records[1196][:3]),ref.VERTICES_1196)
        p=ref.plane(vertices,records[1196]);self.assertAlmostEqual(p[4],.5936838823791017)
        for lib in self.libs:
            x,y,z=ref.START_1196
            self.assertTrue(self.query(lib,self.real_arrays,x,z,y)[0])
            for speed,dt,expected in ((150,.05,True),(500,1/60,True),(500,.05,False)):
                d=F(F(speed*F(dt).value).value/math.sqrt(2)).value
                end=F(x+d).value,F(z-d).value
                self.assertEqual(self.query(lib,self.real_arrays,*end,y)[0],expected)
                exact=ref.height_inside(p,*end)
                if not expected:self.assertAlmostEqual(exact,ref.EXPECTED_END_Y,delta=.001)
                self.assertEqual(ref.floor(vertices,records,*end,y) is not None,expected)

    def test_record_1196_fix_all_rates_and_same_trajectory(self):
        for lib in self.libs:
            x,y,z=ref.START_1196
            for speed in (0,150,500):
                for dt in (0,1/60,.025,.05):
                    d=F(F(speed*F(dt).value).value/math.sqrt(2)).value
                    end=F(x+d).value,F(z-d).value
                    ok,height=self.follow(lib,self.real_arrays,(x,y,z),end)
                    expected,_=ref.follow(*self.real,(x,y,z),end)
                    self.assertTrue(ok);self.assertAlmostEqual(height,expected,delta=.001)
            d=F(25/math.sqrt(2)).value;end=F(x+d).value,F(z-d).value
            ok,height=self.follow(lib,self.real_arrays,(x,y,z),end)
            self.assertTrue(ok);self.assertAlmostEqual(height,ref.EXPECTED_END_Y,delta=.001)
            for count in (2,3,5,10):
                current=(x,y,z)
                for i in range(1,count+1):
                    target=end if i==count else (F(x+(end[0]-x)*i/count).value,F(z+(end[1]-z)*i/count).value)
                    valid,h=self.follow(lib,self.real_arrays,current,target)
                    self.assertTrue(valid);current=(target[0],h,target[1])
                self.assertEqual(current[1],height)

    def test_derived_geometric_bound_and_near_limit_up_downhill(self):
        slope=math.sqrt(1-ref.MIN_NORMAL**2)/ref.MIN_NORMAL
        self.assertEqual(ref.SEGMENT_LIMIT,14)
        self.assertLess(14*slope,30);self.assertGreater(15*slope,30)
        self.assertGreaterEqual(14,150*.05)
        for s in (2.08,-2.08):
            v,t=ramp(s);mesh=arrays(v,t)
            self.assertGreater(ref.plane(v,t[0])[4],ref.MIN_NORMAL)
            for lib in self.libs:
                for direction in (-1,1):
                    end=(direction*25.,0.)
                    self.assertFalse(self.query(lib,mesh,*end,0)[0])
                    ok,y=self.follow(lib,mesh,(0,0,0),end)
                    expected,_=ref.follow(v,t,(0,0,0),end)
                    self.assertTrue(ok);self.assertAlmostEqual(y,expected,delta=.001)
        # Just outside the normal contract stays rejected, regardless of steps.
        mesh=arrays(*ramp(2.10))
        for lib in self.libs:self.assertEqual(self.follow(lib,mesh,(0,0,0),(25,0)),(False,-12345))

    def test_flat_and_continuous_triangle_edge_crossings(self):
        for slope in (0,.5,2):
            v,t=combine(ramp(slope,low=-100,high=10),ramp(slope,low=10,high=100))
            for lib in self.libs:
                ok,y=self.follow(lib,arrays(v,t),(0,0,0),(25,0))
                self.assertTrue(ok);self.assertAlmostEqual(y,25*slope)
                # End exactly on shared triangle/patch edge.
                self.assertEqual(self.follow(lib,arrays(v,t),(-15,-15*slope,0),(10,0)),(True,10*slope))

    def test_failure_is_atomic_not_partial_or_endpoint_only(self):
        # Endpoint is valid, but the first segment (x=12.5) has no floor.
        v,t=combine(ramp(low=-10,high=5),ramp(low=20,high=40));mesh=arrays(v,t)
        for lib in self.libs:
            self.assertTrue(self.query(lib,mesh,25,0,0)[0])
            self.assertEqual(self.follow(lib,mesh,(0,0,0),(25,0)),(False,-12345))
            # First segment succeeds; second fails. Output still not committed.
            self.assertEqual(self.follow(lib,arrays(*ramp(low=-10,high=15)),(0,0,0),(25,0)),(False,-12345))
            self.assertEqual(self.follow(lib,arrays([],[]),(0,0,0),(25,0)),(False,-12345))

    def test_overlapping_layers_highest_per_segment_order_and_window(self):
        # At 12.5 choose 10; at 25 choose 35 (inside 10 +/-30, outside 0 +/-30).
        # This explicitly retains the original per-query, history-dependent rule.
        v,t=combine(ramp(offset=0),ramp(offset=10),ramp(low=20,high=40,offset=35),ramp(offset=100))
        expected,samples=ref.follow(v,t,(0,0,0),(25,0))
        self.assertEqual([p[1] for p in samples],[10,35])
        for lib in self.libs:
            for records in (t,list(reversed(t))):
                self.assertEqual(self.follow(lib,arrays(v,records),(0,0,0),(25,0)),(True,expected))

    def test_filters_two_sided_and_exact_vertical_window_preserved(self):
        for lib in self.libs:
            for flag in (0x20000,0x40000,0x80000,0x100000,0x400000):
                self.assertEqual(self.follow(lib,arrays(*ramp(flags=flag)),(0,0,0),(25,0)),(False,-12345))
            v,t=ramp(2.08);t=[(b,a,c,s,flag) for a,b,c,s,flag in t]
            self.assertFalse(self.follow(lib,arrays(v,t),(0,0,0),(25,0))[0])
            t=[(a,b,c,s,flag|0x10000) for a,b,c,s,flag in t]
            self.assertTrue(self.follow(lib,arrays(v,t),(0,0,0),(25,0))[0])
            for height in (-31,-30,30,31):
                self.assertEqual(self.follow(lib,arrays(*ramp(offset=height)),(0,0,0),(7.5,0))[0],abs(height)<=30)

    def test_asset_worst_case_reaches_data_derived_plane_bound(self):
        result=ref.worst_case()
        self.assertEqual(result['valid_triangles'],1474)
        self.assertEqual(result['maximum']['record'],2890)
        self.assertEqual(result['witness']['record'],2890)
        w=result['witness']
        self.assertAlmostEqual(w['max_height_change_25'],50.722050798507134)
        self.assertAlmostEqual(math.hypot(w['end'][0]-w['start'][0],w['end'][2]-w['start'][2]),25)
        self.assertAlmostEqual(w['end'][1]-w['start'][1],w['max_height_change_25'])
        p=ref.plane(self.real[0],self.real[1][w['record']])
        for point in (w['start'],w['end']):
            self.assertAlmostEqual(ref.height_inside(p,point[0],point[2]),point[1])

    def test_nonfinite_candidates_fail_without_output(self):
        mesh=arrays(*ramp())
        for lib in self.libs:
            for end in ((float('nan'),0),(0,float('inf')),(1e30,0)):
                self.assertEqual(self.follow(lib,mesh,(0,0,0),end),(False,-12345))

    def test_existing_150_update_bit_identical_to_single_query(self):
        rng=random.Random(475)
        v,t=combine(ramp(.5),ramp(.5,offset=5));mesh=arrays(v,t)
        for lib in self.libs:
            for _ in range(80):
                dt=F(rng.choice((0,.001,1/60,.025,.05,.2))).value
                start=Actor(0,0,0,37);before=bytes(start)
                # Cardinal right input: original C candidate evaluation order.
                x=F(F(150*F(min(dt,.05)).value).value).value
                valid,y=self.query(lib,mesh,x,0,0)
                ok=lib.movementUpdate(C.byref(start),156,0,0,dt,False,*mesh,len(mesh[1]))
                if dt==0:self.assertFalse(ok);self.assertEqual(bytes(start),before)
                else:
                    self.assertEqual(ok,valid);self.assertEqual((start.x,start.y,start.z,start.yaw),(x,y,0,90))
            # Original full actor preservation on rejection (including yaw).
            actor=Actor(0,0,0,37);before=bytes(actor);empty=arrays([],[])
            self.assertFalse(lib.movementUpdate(C.byref(actor),156,0,0,.05,False,*empty,0))
            self.assertEqual(bytes(actor),before)

    def test_real_asset_short_candidates_match_original_query(self):
        vertices,records=self.real
        for lib in self.libs:
            checked=0
            for r in records[::7]:
                p=ref.plane(vertices,r)
                if p is None:continue
                start=tuple(F(sum(vertices[i][j] for i in r[:3])/3).value for j in range(3))
                for dx,dz in ((7.5,0),(0,-7.5),(5,5)):
                    end=F(start[0]+dx).value,F(start[2]+dz).value
                    old=self.query(lib,self.real_arrays,*end,start[1])
                    new=self.follow(lib,self.real_arrays,start,end)
                    self.assertEqual(new,old);checked+=1
            self.assertGreater(checked,100)

if __name__=='__main__':unittest.main()
