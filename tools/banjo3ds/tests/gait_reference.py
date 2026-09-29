"""Independent M4.5 original-C pose/blend oracle. No production imports.

Phase rules: bs/walk.c:117,190,262,339. Duration band mapping and .2s
transitions are explicit Banjo3DS policy, not Rare's physics. Every fixture
records source/destination gait as well as clip (WALK and FAST share 000C).
"""
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path
from idle_animation_reference import ROOT, F, original_library
from walk_pose_reference import WalkAnimation, PHASES
from transition_reference import Transition, pose_summary

ASSETS = {
    '0002': ('45695bf12a3f82d0a2a9aaeac7808d4635f4347fedb11d580ae1e332f49c2082',80,44,176),
    '000C': ('cf37a93b986be2efe08b86aadf7bf7709331d14237bf8aaad724f7d870d21f23',120,44,191),
    '0003': ('97424fab14fc0328557a4d6eeb07548a47d8a59d21376d4b008f5f602de50b1a',120,47,234),
    '006F': ('f9df06acf7e20bfb284b24aaca388c97db416a0b0884628e1f13ed5ea5d7d32b',110,81,2996),
}
CLIPS = {'IDLE':'006F','CREEP':'0002','SLOW':'0003','WALK':'000C','FAST':'000C'}
# Interior speeds cross both directions of hysteresis, unlike band endpoints.
SPEEDS = {'IDLE':0.,'CREEP':15.,'SLOW':60.,'WALK':90.,'FAST':150.}

def policy_duration(gait, speed):
    """Independent float32 arithmetic specification of M4.5A band policy."""
    if gait == 'IDLE':return F(5.5).value
    lo,hi,first,last = {
        'CREEP':(0,.2,1.8,1.2), 'SLOW':(.2,.5,1.3,.6),
        'WALK':(.5,.75,.92,.58), 'FAST':(.75,1,.54,.44)}[gait]
    lo,hi,first,last=map(lambda x:F(x).value,(lo,hi,first,last))
    s=min(1.,max(0.,F(F(speed).value/150.).value))
    u=min(1.,max(0.,F(F(s-lo).value/F(hi-lo).value).value))
    value=F(first+F(F(last-first).value*u).value).value
    return min(F(1.5).value,max(F(.3).value,value))

DURATIONS = {g:policy_duration(g,s) for g,s in SPEEDS.items()}
# Explicit original entry-handler facts, not a copy of production logic.
PRESERVE = {('SLOW','CREEP'),('WALK','SLOW'),('SLOW','WALK'),
            ('FAST','WALK'),('WALK','FAST')}
CASES = [('IDLE','CREEP'),('CREEP','IDLE'),('CREEP','SLOW'),('SLOW','CREEP'),
         ('SLOW','WALK'),('WALK','SLOW'),('CREEP','WALK'),('CREEP','FAST'),
         ('SLOW','FAST'),('FAST','SLOW'),('IDLE','WALK'),('WALK','IDLE'),
         ('IDLE','FAST'),('FAST','IDLE')]

class ClipReference(WalkAnimation):
    """Uses original-C channel/quaternion/matrix math and generalized frame range."""
    def __init__(self, asset):
        data=(ROOT/f'assets/anim/{asset}.anim.bin').read_bytes()
        sha,last,count,keys=ASSETS[asset]
        assert hashlib.sha256(data).hexdigest()==sha
        self.first,self.last,n,pad=struct.unpack_from('>hhhH',data)
        assert (self.first,self.last,n,pad)==(0,last,count,0)
        self.channels=[];offset=8
        for _ in range(n):
            packed,length=struct.unpack_from('>Hh',data,offset)
            entries=[struct.unpack_from('>Hh',data,offset+4+4*i) for i in range(length)]
            self.channels.append((packed>>4,packed&15,entries));offset+=4+4*length
        assert offset==len(data) and sum(len(k) for b,c,k in self.channels)==keys
        self.library=original_library()

class GaitTransition(Transition):
    def __init__(self, source, old_gait, new_gait, old_phase, optimization='-O0'):
        self.source=tuple(tuple(F(v).value for v in b) for b in source)
        self.animation=ClipReference(CLIPS[new_gait])
        self.duration=DURATIONS[new_gait]
        self.phase=F(old_phase).value if (old_gait,new_gait) in PRESERVE else 0.
        self.factor=0.;self.optimization=optimization

def golden(optimization='-O0'):
    result={'packing':{'bones':'109 * >10f: XYZW, scale XYZ, translation XYZ',
        'matrices':'60 * >16f: original row-major, before RSP quantization',
        'loads':'723 * >3f: G_VTX load order', 'corners':'2085 * >3f: triangle order'},
        'counts':{'calls':49,'triangles':695,'loads':723,'corners':2085},
        'assets':{},'poses':{},'transitions':{}}
    for clip in ('0002','000C'):
        animation=ClipReference(clip)
        result['assets'][clip]={'sha256':ASSETS[clip][0],
            'bytes':(ROOT/f'assets/anim/{clip}.anim.bin').stat().st_size,
            'first':0,'last':ASSETS[clip][1],'channels':ASSETS[clip][2],'keys':ASSETS[clip][3]}
        result['poses'][clip]=[dict(phase=p,**pose_summary(animation.transforms(p)[0])) for p in PHASES]
    for old,new in CASES:
        source=ClipReference(CLIPS[old]).transforms(.37)[0]
        t=GaitTransition(source,old,new,.37,optimization)
        result['transitions'][old+'_'+new]=dict(source_gait=old,destination_gait=new,
            source_phase=F(.37).value,speed=SPEEDS[new],duration=F(t.duration).value,
            rows=[t.sample()[1]]+[t.step(.025)[1] for _ in range(8)])
    source=ClipReference('0002').transforms(.37)[0]
    t=GaitTransition(source,'CREEP','SLOW',.37,optimization)
    for _ in range(3):mixed,at=t.step(.025)
    # During CREEP->SLOW the current logical gait is SLOW; SLOW->WALK
    # inherits its advancing phase, but freezes the MIXED pose values.
    second=GaitTransition(mixed,'SLOW','WALK',t.phase,optimization)
    result['interruption']={'at':at,'rows':[second.sample()[1]]+[second.step(.025)[1] for _ in range(8)]}
    return result

if __name__=='__main__':
    import sys
    Path(sys.argv[1]).write_text(json.dumps(golden(),indent=2)+'\n')
