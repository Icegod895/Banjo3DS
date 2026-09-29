"""Independent 0008 ONCE/subrange reference; NO production imports.

Original-C animation/quaternion/blend/matrix oracles and independent geo/RSP
traversal. The small controller is the explicit M4.6B Banjo3DS policy, with
bs/jump.c:57-63,108-112 and anctrl.c:86 strict subrange endpoints. Landing
returns immediately to gait/idle (not Rare's complete landing state).
"""
import hashlib
import json
import struct
from pathlib import Path
from idle_animation_reference import ROOT, F, original_library
from walk_pose_reference import WalkAnimation
from gait_reference import ClipReference
from transition_reference import blend_pose, pose_summary, digest

SHA='b4984d8cfe4aed530a7fb1d62221619b1babac4f79c1697aa85d71ea4847f7e8'
PHASES=(0.,.3,.3+2**-20,.4,.5042,.6,.6667,.75,1-2**-20,1-2**-24,1.)
def f(x):return F(x).value

class JumpReference(WalkAnimation):
    def __init__(self):
        data=(ROOT/'assets/anim/0008.anim.bin').read_bytes()
        assert len(data)==1788 and hashlib.sha256(data).hexdigest()==SHA
        self.first,self.last,n,pad=struct.unpack_from('>hhhH',data)
        assert (self.first,self.last,n,pad)==(0,45,35,0)
        self.channels=[];offset=8
        for _ in range(n):
            descriptor,count=struct.unpack_from('>Hh',data,offset)
            keys=[struct.unpack_from('>Hh',data,offset+4+4*i) for i in range(count)]
            self.channels.append((descriptor>>4,descriptor&15,keys));offset+=4+4*count
        assert offset==len(data) and sum(len(k) for _,_,k in self.channels)==410
        self.library=original_library()

def animation(clip):return JumpReference() if clip=='0008' else ClipReference(clip)

class JumpTransition:
    def __init__(self,source,clip,duration=1.9,optimization='-O0'):
        self.source=tuple(tuple(f(x) for x in b) for b in source)
        self.clip=clip;self.animation=animation(clip);self.optimization=optimization
        self.phase=f(.3) if clip=='0008' else 0.;self.factor=0.;self.segment=0
        self.duration=f(1.9 if clip=='0008' else duration)
        self.transition=f(.134 if clip=='0008' else .2)

    def advance(self,dt):
        dt=min(f(dt),f(.05));assert dt>=0
        self.factor=min(1.,f(self.factor+f(dt/self.transition)))
        if self.clip=='0008':
            if self.segment<2:
                self.phase=f(self.phase+f(dt/self.duration))
                end=f(.5042 if self.segment==0 else .6667)
                if self.phase>end:
                    self.phase=end
                    if self.segment==0:self.duration=f(4.)
                    self.segment+=1
        else:
            self.phase=f(self.phase+f(dt/self.duration));self.phase=f(self.phase-int(self.phase))

    def sample(self):
        target=self.animation.transforms(self.phase)[0]
        mixed,_=blend_pose(self.source,target,self.factor,self.optimization)
        return mixed,dict(phase=self.phase,factor=self.factor,segment=self.segment,
            duration=self.duration,source_hash=digest(self.source,10),
            destination_hash=digest(target,10),**pose_summary(mixed))

    def step(self,dt):self.advance(dt);return self.sample()

CASES=(('006F','0008',.37,1.9),('0003','0008',.625,1.9),
       ('0008','006F',.61,5.5),('0008','0003',.6667,.6))

def golden(optimization='-O0'):
    result={'asset':{'sha256':SHA,'bytes':1788,'frames':[0,45],'channels':35,'keys':410},
        'packing':{'bones':'109 * >10f XYZW, scale XYZ, translation XYZ',
                   'matrices':'60 * >16f original row-major before RSP quantization',
                   'loads':'723 * >3f G_VTX order','corners':'2085 * >3f triangle order'},
        'counts':{'calls':49,'triangles':695,'loads':723,'corners':2085},
        'poses':[dict(phase=f(p),**pose_summary(JumpReference().transforms(p)[0])) for p in PHASES],
        'transitions':{}}
    for old,new,phase,duration in CASES:
        source=animation(old).transforms(phase)[0]
        t=JumpTransition(source,new,duration,optimization)
        result['transitions'][old+'_'+new]=dict(source=old,destination=new,source_phase=f(phase),
            duration=f(duration),rows=[t.sample()[1]]+[t.step(.025)[1] for _ in range(8)])
    t=JumpTransition(animation('006F').transforms(.37)[0],'0008',optimization=optimization)
    for _ in range(3):mixed,at=t.step(.025)
    second=JumpTransition(mixed,'0003',.6,optimization)
    result['interruption']={'at':at,'rows':[second.sample()[1]]+[second.step(.025)[1] for _ in range(8)]}
    return result

if __name__=='__main__':
    import sys
    Path(sys.argv[1]).write_text(json.dumps(golden(),indent=2)+'\n')
