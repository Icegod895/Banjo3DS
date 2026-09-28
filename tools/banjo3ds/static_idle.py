"""Host-only canonical 006F idle target, no controller or transition state.

Independent Python implementation of animationfile.c:85, code_BE2C0.c:20,161,
mlmtx.c:259 and code_630D0.c:84. Arithmetic follows the original float/double
expression boundaries; libultra's sin/cos polynomial avoids host-libm drift.
Only the SHA-verified 006F animation is accepted, and baking uses time zero.
"""
from bisect import bisect_right
import hashlib
import math
from pathlib import Path
import struct

from tools.banjo3ds.canonical_banjo import CanonicalBanjoPose, IDENTITY

ANIMATION_SHA256 = 'f9df06acf7e20bfb284b24aaca388c97db416a0b0884628e1f13ed5ea5d7d32b'
DEFAULT_CHANNELS = (0., 0., 0., 1., 1., 1., 0., 0., 0.)
DEGREES_TO_RADIANS = 3.141592654 / 180.0


def f32(value):
    return struct.unpack('>f', struct.pack('>f', value))[0]


def add(a, b):
    return f32(a + b)


def mul(a, b):
    return f32(a * b)


def catmull_rom(t, knots):
    # code_B9770.c:241: coefficients use double literals, Horner terms float.
    t = f32(min(1., max(0., t)))
    a, b, c, d = knots
    cubic = f32(-0.5*a + 1.5*b - 1.5*c + 0.5*d)
    square = f32(a - 2.5*b + 2.*c - 0.5*d)
    linear = f32(-0.5*a + 0.*b + 0.5*c + 0.*d)
    return f32(mul(add(mul(add(mul(cubic, t), square), t), linear), t) + b)


class IdleChannels:
    def __init__(self, path):
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != ANIMATION_SHA256:
            raise ValueError('Static idle requires the verified 006F animation')
        self.first, self.last, count, pad = struct.unpack_from('>hhhH', data)
        self.channels = {}
        offset = 8
        for _ in range(count):
            packed, n = struct.unpack_from('>Hh', data, offset)
            keys = [struct.unpack_from('>Hh', data, offset+4+4*i) for i in range(n)]
            self.channels[packed >> 4, packed & 15] = keys
            offset += 4 + 4*n
        if offset != len(data) or (self.first, self.last, pad) != (0, 110, 0):
            raise ValueError('Unexpected 006F layout')

    def channel_value(self, bone, channel, frame):
        """Original key evaluation; exposed for source/reference regression tests."""
        frame = f32(frame)
        if not self.first <= frame <= self.last:
            raise ValueError('Static channel evaluation requires an in-range frame')
        keys = self.channels[bone, channel]
        frames = [word & 0x3fff for word, value in keys]
        values = [value / 64. for word, value in keys]
        if int(frame) < frames[0]:
            t = f32(f32(frame-self.first) / (frames[0]-self.first))
            right = values[1] if keys[0][0] & 0x8000 and len(keys) > 1 else values[0]
            return catmull_rom(t, (DEFAULT_CHANNELS[channel], DEFAULT_CHANNELS[channel], values[0], right))
        if int(frame) >= frames[-1]:
            left = values[-2] if keys[-1][0] & 0x4000 and len(keys) > 1 else values[-1]
            return catmull_rom(f32(frame-frames[-1]), (left, values[-1], values[-1], values[-1]))
        i = bisect_right(frames, int(frame)) - 1
        t = f32(f32(frame-frames[i]) / (frames[i+1]-frames[i]))
        a, b = values[i:i+2]
        if not (keys[i][0] & 0x4000 or keys[i+1][0] & 0x8000):
            return add(a, mul(f32(b-a), t))
        previous = values[i-1] if keys[i][0] & 0x4000 and i > 0 else a
        following = values[i+2] if keys[i+1][0] & 0x8000 and i+2 < len(keys) else b
        return catmull_rom(t, (previous, a, b, following))

    def transforms_at_start(self):
        channels = [list(DEFAULT_CHANNELS) for _ in range(109)]
        for bone, channel in self.channels:
            channels[bone][channel] = self.channel_value(bone, channel, self.first)
        return [euler_quaternion(c[:3]) + tuple(c[3:]) for c in channels]


def libultra_trig(angle, cosine=False):
    """Finite angle subset of lib/ultralib/src/gu/{sin,cos}f.c, binary64 polynomial."""
    angle = f32(angle)
    exponent = (struct.unpack('>I', struct.pack('>f', angle))[0] >> 22) & 0x1ff
    if exponent >= 0x136:
        raise ValueError('Angle outside static idle trig range')
    if not cosine and exponent < 0xe6:
        return angle
    p = [struct.unpack('>d', struct.pack('>Q', bits))[0] for bits in
         (0xbfc55554bc83656d, 0x3f8110ed3804c2a0, 0xbf29f6ffeea56814, 0x3ec5dbdf0e314bfe)]
    rpi, pihi, pilo = [struct.unpack('>d', struct.pack('>Q', bits))[0] for bits in
                       (0x3fd45f306dc9c883, 0x400921fb50000000, 0x3e6110b4611a6263)]
    x, n = angle, 0
    if cosine or exponent >= 0xff:
        x = abs(angle) if cosine else angle
        dn = x*rpi + (0.5 if cosine else 0.)
        n = int(dn + (0.5 if dn >= 0 else -0.5))
        dn = n - (0.5 if cosine else 0.)
        x = (x - dn*pihi) - dn*pilo
    square = x*x
    polynomial = ((p[3]*square+p[2])*square+p[1])*square+p[0]
    result = f32(x + (x*square)*polynomial)
    return -result if n & 1 else result


def euler_quaternion(angles):
    # Rare's row-matrix storage: Roll, then Yaw, then Pitch.
    matrix = [list(row) for row in IDENTITY]
    for axis, angle in ((2, angles[2]), (1, angles[1]), (0, angles[0])):
        if angle == 0:
            continue
        radians = f32(angle * (DEGREES_TO_RADIANS if axis == 1 else f32(DEGREES_TO_RADIANS)))
        sine, cosine = libultra_trig(radians), libultra_trig(radians, True)
        i, j = ((1, 2), (0, 2), (0, 1))[axis]
        sign = -1 if axis == 1 else 1
        for column in range(3):
            a, b = matrix[i][column], matrix[j][column]
            matrix[i][column] = add(mul(a, cosine), mul(b, sign*sine))
            matrix[j][column] = add(mul(a, -sign*sine), mul(b, cosine))
    trace = add(add(matrix[0][0], matrix[1][1]), matrix[2][2])
    q = [0.] * 4
    if trace > 0:
        root = f32(math.sqrt(f32(trace + 1.)))
        q[3] = f32(root * 0.5)
        factor = f32(0.5 / root)
        for i, j, k in ((0,1,2), (1,2,0), (2,0,1)):
            q[i] = mul(f32(matrix[j][k]-matrix[k][j]), factor)
    else:
        i = max(range(3), key=lambda a: matrix[a][a])
        j, k = (i+1) % 3, (i+2) % 3
        root = f32(math.sqrt(f32(f32(matrix[i][i]-add(matrix[j][j], matrix[k][k])) + 1.)))
        q[i] = f32(root * 0.5)
        factor = f32(0.5 / root)
        q[3] = mul(f32(matrix[j][k]-matrix[k][j]), factor)
        q[j] = mul(add(matrix[i][j], matrix[j][i]), factor)
        q[k] = mul(add(matrix[i][k], matrix[k][i]), factor)
    return tuple(q)


def quaternion_matrix(q):
    norm = add(add(add(mul(q[0], q[0]), mul(q[1], q[1])), mul(q[2], q[2])), mul(q[3], q[3]))
    factor = f32(2. / norm) if norm else 2.
    x, y, z = [mul(v, factor) for v in q[:3]]
    xw, yw, zw = [mul(v, q[3]) for v in (x, y, z)]
    xx, xy, xz = [mul(v, q[0]) for v in (x, y, z)]
    yy, yz, zz = mul(y, q[1]), mul(z, q[1]), mul(z, q[2])
    return ((f32(1.-add(yy,zz)), add(xy,zw), f32(xz-yw)),
            (f32(xy-zw), f32(1.-add(xx,zz)), add(yz,xw)),
            (add(xz,yw), f32(yz-xw), f32(1.-add(xx,yy))))


def bone_matrices(model, transforms):
    """Float32 absolute matrices, applying each record's parent exactly once."""
    offset = struct.unpack_from('>I', model.data, 24)[0]
    factor, count = struct.unpack_from('>fh', model.data, offset)
    rows = []

    def translate(matrix, xyz):
        for c in range(3):
            delta = add(add(mul(matrix[0][c], xyz[0]), mul(matrix[1][c], xyz[1])),
                        mul(matrix[2][c], xyz[2]))
            matrix[3][c] = add(matrix[3][c], delta)

    for i in range(count):
        *pivot, bone, parent = struct.unpack_from('>3fhh', model.data, offset+8+16*i)
        if not -1 <= parent < i or not 0 <= bone < len(transforms):
            raise ValueError('Invalid canonical bone matrix record')
        matrix = [list(row) for row in (IDENTITY if parent == -1 else rows[parent])]
        q, scale, translation = transforms[bone][:4], transforms[bone][4:7], transforms[bone][7:]
        translate(matrix, [add(p, mul(factor, t)) for p, t in zip(pivot, translation)])
        if q != (0., 0., 0., 1.):
            rotation = quaternion_matrix(q)
            rotated = [[0.]*3 for _ in range(3)]
            for r in range(3):
                for c in range(3):
                    for k in range(3):
                        rotated[r][c] = add(rotated[r][c], mul(rotation[r][k], matrix[k][c]))
            for r in range(3):
                matrix[r][:3] = rotated[r]
        for r in range(3):
            matrix[r][:3] = [mul(v, scale[r]) for v in matrix[r][:3]]
        translate(matrix, [-p for p in pivot])
        rows.append(matrix)
    return [tuple(tuple(matrix[c][r] for c in range(4)) for r in range(4)) for matrix in rows]


class StaticIdlePose(CanonicalBanjoPose):
    def __init__(self, model, animation_path):
        super().__init__(model)
        self.transforms = IdleChannels(animation_path).transforms_at_start()
        self.bones = bone_matrices(model, self.transforms)

    def push(self, matrix):
        # M3.5's fixed diagnostic camera (0,0,100) precedes signed 16.16
        # truncation. Undo that translation afterwards for model-local baking.
        view = [list(row) for row in matrix]
        view[2][3] = f32(view[2][3] - 100.)
        fixed = [[int(mul(f32(v), 65536.))/65536. for v in row] for row in view]
        fixed[2][3] += 100.
        self.rsp.append(tuple(tuple(row) for row in fixed))


def decode_static_idle(model, animation_path):
    from tools.banjo3ds.n64_displaylist_decoder import interpret_display_list
    return interpret_display_list(model, pose=StaticIdlePose(model, animation_path))
