"""Independent 0003 target poses. Original-C oracle, no production imports.

Reuses M3.5's extracted original evaluator/quaternion/matrix functions, not
IdleAnimation.transforms(): that helper's frame() wrapper is fixed to 006F.
The existing original geo/RSP reference remains the geometry oracle.
"""
import ctypes as C
import hashlib
import struct
from idle_animation_reference import IdleAnimation, original_library, QuantizedPoseReference, F, ROOT
from banjo_pose_reference import PoseReference, translation

WALK_SHA = '97424fab14fc0328557a4d6eeb07548a47d8a59d21376d4b008f5f602de50b1a'
PHASES = (0., 2**-20, .25, .5, .75, 1-2**-20, 1-2**-24, 1.)

class WalkAnimation(IdleAnimation):
    def __init__(self):
        data=(ROOT/'assets/anim/0003.anim.bin').read_bytes()
        assert hashlib.sha256(data).hexdigest()==WALK_SHA
        self.first,self.last,count,pad=struct.unpack_from('>hhhH',data)
        assert (self.first,self.last,count,pad)==(0,120,47,0)
        self.channels=[]; offset=8
        for _ in range(count):
            packed,n=struct.unpack_from('>Hh',data,offset)
            keys=[struct.unpack_from('>Hh',data,offset+4+4*i) for i in range(n)]
            self.channels.append((packed>>4,packed&15,keys)); offset+=4+4*n
        assert offset==len(data)
        self.library=original_library()

    def transforms(self,time=0.):
        frame=F(self.first+F(F(time).value*(self.last-self.first)).value).value
        channels=[[0.,0.,0.,1.,1.,1.,0.,0.,0.] for _ in range(109)]
        for bone,channel,_ in self.channels:
            channels[bone][channel]=self.channel_value(bone,channel,frame)
        bones=[]
        for values in channels:
            q=(F*4)(); self.library.quaternion((F*3)(*values[:3]),q)
            bones.append(tuple(q)+tuple(values[3:]))
        return bones,channels


def reference(phase):
    animation=WalkAnimation()
    bones,_=animation.transforms(phase)
    pose=QuantizedPoseReference((ROOT/'assets/model/034D.model.bin').read_bytes(),
                                bone_overrides=animation.matrices(bones)).run()
    return animation,bones,pose


def reference_binding():
    # Unique symbolic matrix tags, NOT inferred from equal animated matrices.
    # Translation tags preserve the canonical near branch; exact CALLS checked
    # by the independent traversal. base has x=0, record j has x=j+1.
    pose=PoseReference((ROOT/'assets/model/034D.model.bin').read_bytes(),
                      bone_overrides={j:translation(j+1,0,0) for j in range(60)}).run()
    loads=[(*entry['raw'],int(entry['matrix'][0][3])-1) for entry in pose.loads]
    return [(x,y,z,65535 if record==-1 else record) for x,y,z,record in loads], \
           [i for triangle in pose.triangles for i in triangle], pose.calls


def golden(phase):
    _,bones,pose=reference(phase)
    summary=pose.summary()
    return dict(phase=phase,bone_sha256=hashlib.sha256(b''.join(struct.pack('>10f',*b) for b in bones)).hexdigest(),
                geometry_sha256=summary['triangle_xyz_be_f32_sha256'],bounds=summary['bounds'],
                samples={str(i):pose.loads[i]['xyz'] for i in (0,120,240,360,600,722)})
