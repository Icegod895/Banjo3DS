"""3DS input translation policy: independent tables, SDK keys, no camera math."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
# Verified against the installed libctru hid.h; production uses KEY_* directly.
A,B,SELECT,START,RIGHT,LEFT,UP,DOWN,R,L,X,Y=[1<<n for n in range(12)]
NR,CL,CR,CD,CU,NZ,NA,NB,NS=[1<<n for n in range(9)]
class State(C.Structure):
    _fields_=[('held',C.c_uint32),('consumed',C.c_uint32),('x',C.c_int8),('y',C.c_int8)]
class Frame(C.Structure):
    _fields_=[('held',C.c_uint32),('pressed',C.c_uint32),('released',C.c_uint32),
              ('manual',C.c_uint32),('jump',C.c_bool),('suppress',C.c_bool)]
def bind(lib):
    lib.playerInputUpdate.argtypes=[C.POINTER(State),C.c_uint32,C.c_int16,C.c_int16]
    lib.playerInputUpdate.restype=Frame

def read(lib,s,keys=0,x=0,y=0):return lib.playerInputUpdate(C.byref(s),keys,x,y)

class PlayerInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='player-input-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                '-I/opt/devkitpro/libctru/include',str(ROOT/'platform/3ds/source/player_input.c'),'-o',str(out)],check=True)
            lib=C.CDLL(str(out));bind(lib);cls.libs.append(lib)

    def test_every_mapping_press_hold_release_each_source(self):
        cases=[(X,0,0,NR),(L,0,0,NZ),(A,0,0,NA),(B,0,0,NB),(START,0,0,NS),
               (UP,0,0,CU),(DOWN,0,0,CD),(LEFT,0,0,CL),(RIGHT,0,0,CR),
               (0,0,40,CU),(0,0,-40,CD),(0,-40,0,CL),(0,40,0,CR),
               (R|X,0,0,CU),(R|B,0,0,CD),(R|Y,0,0,CL),(R|A,0,0,CR)]
        for lib in self.libs:
            for keys,x,y,want in cases:
                s=State();a=read(lib,s,keys,x,y)
                self.assertEqual((a.held,a.pressed,a.released,a.manual),(want,want,0,want&15))
                self.assertEqual(a.jump,want==NA);self.assertFalse(a.suppress)
                for _ in range(90):
                    b=read(lib,s,keys,x,y);self.assertEqual((b.held,b.pressed,b.released),(want,0,0));self.assertFalse(b.jump)
                b=read(lib,s);self.assertEqual((b.held,b.pressed,b.released),(0,0,want))

    def test_all_simultaneous_physical_combinations_modifier_priority(self):
        # Independent truth table for all ten relevant discrete keys.
        keys=(A,B,X,Y,R,L,UP,DOWN,LEFT,RIGHT)
        for lib in self.libs:
            for mask in range(1<<len(keys)):
                held=sum(k for i,k in enumerate(keys) if mask&(1<<i));want=0
                for physical,logical in ((L,NZ),(UP,CU),(DOWN,CD),(LEFT,CL),(RIGHT,CR)):
                    if held&physical:want|=logical
                mapping=((X,CU),(Y,CL),(A,CR),(B,CD)) if held&R else ((X,NR),(A,NA),(B,NB))
                for physical,logical in mapping:
                    if held&physical:want|=logical
                f=read(lib,State(),held)
                self.assertEqual((f.held,f.pressed,f.manual),(want,want,want&15),held)
                self.assertEqual(f.suppress,bool(held&Y and not held&R))
                self.assertEqual(f.jump,bool(held&A and not held&R))

    def test_schmitt_boundaries_reversal_diagonal_and_noise(self):
        for lib in self.libs:
            for sign,button in ((1,CR),(-1,CL)):
                s=State()
                for val,want,edge in ((0,0,0),(25,0,0),(26,0,0),(39,0,0),(40,button,button),
                        (39,button,0),(26,button,0),(25,0,0),(39,0,0),(40,button,button)):
                    f=read(lib,s,0,sign*val,0);self.assertEqual((f.held,f.pressed),(want,edge))
                f=read(lib,s,0,-sign*40,0)
                self.assertEqual((f.held,f.pressed,f.released),(CL if sign==1 else CR,CL if sign==1 else CR,button))
            for x,y,want in ((40,40,CR|CU),(-40,40,CL|CU),(-40,-40,CL|CD),(40,-40,CR|CD),
                             (32767,-32768,CR|CD)):
                s=State();self.assertEqual(read(lib,s,0,x,y).held,want)
                self.assertEqual(read(lib,s,0,x,y).pressed,0)
            s=State()
            for i in range(500):self.assertEqual(read(lib,s,0,i%51-25,25-i%51).held,0)
            # Axes are independent, square activation policy: 30/30 is not a press.
            self.assertEqual(read(lib,State(),0,30,30).held,0)

    def test_merge_source_handover_does_not_repeat_edges(self):
        for lib in self.libs:
            s=State()
            sequence=[(LEFT,0),(LEFT,-60),(0,-60),(R|Y,-60),(R|Y,0),(R|Y|LEFT,0),(LEFT|Y,0),(LEFT,0)]
            for i,(held,x) in enumerate(sequence):
                f=read(lib,s,held,x,0)
                self.assertEqual((f.held,f.pressed,f.released),(CL,CL if i==0 else 0,0))
                self.assertFalse(f.suppress)
            self.assertEqual(read(lib,s).released,CL)
            self.assertEqual(read(lib,s,LEFT).pressed,CL)
            # Independent opposing sources stay distinct: Rare decides priority.
            f=read(lib,State(),LEFT|UP,50,-50)
            self.assertEqual((f.held,f.manual),(CL|CR|CU|CD,CL|CR|CD))

    def test_modifier_chords_require_face_release_before_gameplay(self):
        for lib in self.libs:
            for face,normal,chord in ((A,NA,CR),(B,NB,CD),(X,NR,CU),(Y,0,CL)):
                s=State();f=read(lib,s,face)
                self.assertEqual(f.held,normal)
                f=read(lib,s,R|face);self.assertEqual(f.held,chord);self.assertFalse(f.jump);self.assertFalse(f.suppress)
                # Shoulder release is a C release, not an ordinary face press.
                for _ in range(5):
                    f=read(lib,s,face);self.assertEqual((f.held,f.pressed),(0,0));self.assertFalse(f.suppress)
                read(lib,s);f=read(lib,s,face);self.assertEqual(f.pressed,normal)
                self.assertEqual(f.suppress,face==Y)
                # Shoulder first, then face; holding face cannot retrigger A.
                s=State();self.assertEqual(read(lib,s,R).held,0)
                self.assertEqual(read(lib,s,R|face).pressed,chord)
                self.assertEqual(read(lib,s,R|face).pressed,0)
                self.assertEqual(read(lib,s,R).released,chord)
                self.assertEqual(read(lib,s,R|face).pressed,chord)
            s=State();self.assertTrue(read(lib,s,Y).suppress)
            self.assertFalse(read(lib,s,R|Y).suppress)
            self.assertFalse(read(lib,s,Y).suppress)
            read(lib,s);self.assertTrue(read(lib,s,Y).suppress)

    def test_reserved_inputs_ignore_hid_virtual_directions_and_unmapped_keys(self):
        for lib in self.libs:
            for keys in (R,SELECT,1<<14,1<<15,0xff000000):
                f=read(lib,State(),keys);self.assertEqual((f.held,f.manual,f.jump,f.suppress),(0,0,False,False))
            for keys in (UP,R|X,L,B):
                f=read(lib,State(),keys);self.assertNotEqual(f.held,0);self.assertEqual(f.manual,0);self.assertFalse(f.jump)
            self.assertEqual(C.sizeof(State),12);self.assertEqual(C.sizeof(Frame),20)

    def test_full_int16_axis_domain_and_O0_O2_parity(self):
        # Hold from each polarity and neutral; verify exactly the Schmitt sets,
        # including signed extremes. No float or assumed hardware maximum.
        for previous in (-1,0,1):
            for value in range(-32768,32768):
                expected=1 if value>=40 or (previous==1 and value>25) else -1 if value<=-40 or (previous==-1 and value<-25) else 0
                states=[State(x=previous) for _ in self.libs]
                frames=[read(lib,s,0,value,0) for lib,s in zip(self.libs,states)]
                self.assertEqual(states[0].x,expected);self.assertEqual(states[1].x,expected)
                self.assertEqual(tuple(getattr(frames[0],n) for n,_ in Frame._fields_),
                                 tuple(getattr(frames[1],n) for n,_ in Frame._fields_))
