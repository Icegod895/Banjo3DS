"""Independent crouch-clip poses. Original-C channel oracle, no production imports.

Uses the extracted animationfile / quaternion path from the idle reference.
Frame mapping matches WalkAnimation: normalized phase times the clip's own
last frame, with first frame 0. It does not wrap phase 1 back to 0.
"""
import hashlib
import struct

from idle_animation_reference import F, IdleAnimation, QuantizedPoseReference, ROOT, original_library

MODEL = ROOT / 'assets/model/034D.model.bin'
CLIPS = {
    '0001': ('e87528e23c123f01ff6c22a4001c557667129831caebbfdf677e7e426c252416', 28, 58),
    '010C': ('0ade73c41f67baabffc3e529e7f2100659867146355f091752c6f8cea248943a', 48, 53),
    '0116': ('efeda4d5cd1cc63d4796c3b7d6b50c63fbf3baede351e924d374e358d44b7832', 95, 57),
}


class CrouchAnimation(IdleAnimation):
    def __init__(self, name):
        sha, last, channels = CLIPS[name]
        data = (ROOT / f'assets/anim/{name}.anim.bin').read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('Unexpected crouch animation ' + name)
        self.name = name
        self.first, self.last, count, pad = struct.unpack_from('>hhhH', data)
        if (self.first, self.last, count, pad) != (0, last, channels, 0):
            raise ValueError('Unexpected crouch header ' + name)
        self.channels = []
        offset = 8
        for _ in range(count):
            packed, n = struct.unpack_from('>Hh', data, offset)
            keys = [struct.unpack_from('>Hh', data, offset + 4 + 4 * i) for i in range(n)]
            self.channels.append((packed >> 4, packed & 15, keys))
            offset += 4 + 4 * n
        if offset != len(data):
            raise ValueError('Crouch animation did not consume its bytes')
        self.library = original_library()

    def transforms(self, time=0.):
        frame = F(self.first + F(F(time).value * (self.last - self.first)).value).value
        channels = [[0., 0., 0., 1., 1., 1., 0., 0., 0.] for _ in range(109)]
        for bone, channel, _ in self.channels:
            channels[bone][channel] = self.channel_value(bone, channel, frame)
        bones = []
        for values in channels:
            quaternion = (F * 4)()
            self.library.quaternion((F * 3)(*values[:3]), quaternion)
            bones.append(tuple(quaternion) + tuple(values[3:]))
        return bones, channels


def reference(name, phase):
    animation = CrouchAnimation(name)
    bones, _ = animation.transforms(phase)
    pose = QuantizedPoseReference(MODEL.read_bytes(), bone_overrides=animation.matrices(bones)).run()
    return animation, bones, pose
