"""Standalone canonical 034D/0003 pose packet, not part of the viewer export.

Big endian B3P3 v1: 32-byte header (magic, version, matrix/load/corner counts,
animation length, two reserved u32); f32 translation scale; 60 records >3fhh;
load entries >3hH (raw XYZ, matrix record or 0xffff for model base);
2085 >H corner indices; verbatim 0003 animation. No implicit struct padding.

Symbolically executes BONE/SKINNING/G_POPMTX at G_VTX time. Source of truth:
modelRender.c:657-705 and canonical_banjo's fixed near/selector contract.
"""
from pathlib import Path
import hashlib
import struct
from tools.banjo3ds.canonical_banjo import CANONICAL_SHA256

WALK_SHA = '97424fab14fc0328557a4d6eeb07548a47d8a59d21376d4b008f5f602de50b1a'
BASE = 0xffff


def binding(model_path):
    data = Path(model_path).read_bytes()
    if hashlib.sha256(data).hexdigest() != CANONICAL_SHA256:
        raise ValueError('Expected canonical 034D')
    def read(fmt, offset):
        return struct.unpack_from(fmt, data, offset)[0]
    gfx, vertices = read('>I', 12)+8, read('>I', 16)+24
    cpu, rsp, cache = [BASE], [BASE, BASE], [None]*32
    loads, corners, calls = [], [], []
    def pop():
        if len(rsp) <= 1:
            raise ValueError('RSP underflow')
        rsp.pop()
    def display(index):
        calls.append(index)
        while True:
            w0, w1 = struct.unpack_from('>II', data, gfx+8*index)
            op = w0 >> 24
            if op == 0xb8:
                return
            if op == 0xbd:
                if w1 != 0:
                    raise ValueError('Unsupported matrix pop')
                pop()
            elif op == 4:
                slot, count = ((w0 >> 16) & 255)//2, (w0 >> 10) & 63
                if w1 >> 24 != 1 or slot+count > 32:
                    raise ValueError('Invalid vertex load')
                for i in range(count):
                    raw = struct.unpack_from('>3h', data, vertices+(w1 & 0xffffff)+16*i)
                    cache[slot+i] = len(loads)
                    loads.append((*raw, rsp[-1]))
            elif op in (0xbf, 0xb1):
                for word in ((w0,w1) if op == 0xb1 else (w1,)):
                    for shift in (16,8,0):
                        slot = ((word >> shift) & 255)//2
                        if slot >= 32 or cache[slot] is None:
                            raise ValueError('Invalid cache reference')
                        corners.append(cache[slot])
            elif op == 6:
                if not (0x03000000 <= w1 <= 0x03000080 and w1 % 16 == 0):
                    raise ValueError('Unexpected DL call')
            elif op not in (0xb6,0xb7,0xbb,0xe7,0xfc,0xfd,0xf5,0xf0,0xba,0xf3,0xf2,0xe6):
                raise ValueError(f'Unsupported opcode {op:#x}')
            index += 1
    def visit(offset):
        while offset:
            kind = read('>I',offset)
            if kind == 8:
                maximum, minimum, x,y,z = struct.unpack_from('>5f',data,offset+8)
                # Canonical near geometry only; no pose-dependent LOD evaluation.
                if cpu[-1] != BASE:
                    raise ValueError('Pose-dependent LOD outside contract')
                branch = read('>i',offset+28)
                if branch and minimum < (x*x+y*y+(z-100)**2)**.5 <= maximum:
                    visit(offset+branch)
            elif kind == 12:
                selector = read('>h',offset+10)
                if not 0 <= selector <= 0x29:
                    raise ValueError('Unsupported selector')
                branch = read('>i',offset+12)
                if selector >= 0x12 and branch:
                    visit(offset+branch)
            elif kind == 2:
                record = read('>b',offset+9)
                if not -1 <= record < 60:
                    raise ValueError('Invalid matrix record')
                cpu.append(BASE if record == -1 else record)
                rsp.append(cpu[-1])
                branch = read('>B',offset+8)
                if branch:
                    visit(offset+branch)
                cpu.pop(); pop()
            elif kind == 3:
                display(read('>h',offset+8))
            elif kind == 5:
                display(read('>h',offset+8))
                field = offset+10
                while read('>h',field):
                    rsp.append(cpu[-1])
                    display(read('>h',field)); field += 2
            elif kind != 10:
                raise ValueError('Unsupported geometry')
            following = read('>i',offset+4)
            offset = offset+following if following else 0
    visit(read('>I',4)); pop()
    if cpu != [BASE] or rsp != [BASE] or (len(calls),len(loads),len(corners)) != (49,723,2085):
        raise ValueError('Canonical traversal mismatch')
    if set(corners) != set(range(723)):
        raise ValueError('Unused canonical load')
    return loads,corners,calls


def export_pose_packet(model_path, animation_path):
    model = Path(model_path).read_bytes()
    animation = Path(animation_path).read_bytes()
    if hashlib.sha256(animation).hexdigest() != WALK_SHA:
        raise ValueError('Only verified 0003 supported')
    loads,corners,_ = binding(model_path)
    offset = struct.unpack_from('>I',model,24)[0]
    factor,count = struct.unpack_from('>fh',model,offset)
    if (factor,count) != (10.,60):
        raise ValueError('Unexpected skeleton')
    records = model[offset+8:offset+8+60*16]
    return (struct.pack('>4s7I',b'B3P3',1,60,723,2085,len(animation),0,0)
            + struct.pack('>f',factor) + records
            + b''.join(struct.pack('>3hH',*entry) for entry in loads)
            + struct.pack('>2085H',*corners) + animation)


def export_transition_packet(model_path, walk_path, idle_path):
    """B3P3 v2: unchanged binding, raw 0003 then raw 006F.

    Header word 6 holds idle length instead of zero; no channel reindexing.
    v1 remains available for historical M4.3 byte-identity regressions.
    """
    from tools.banjo3ds.static_idle import ANIMATION_SHA256
    idle = Path(idle_path).read_bytes()
    if hashlib.sha256(idle).hexdigest() != ANIMATION_SHA256:
        raise ValueError('Only verified 006F supported')
    packet = bytearray(export_pose_packet(model_path, walk_path))
    struct.pack_into('>I', packet, 4, 2)
    struct.pack_into('>I', packet, 24, len(idle))
    return bytes(packet) + idle


def export_gait_packet(model_path, walk_path, idle_path, creep_path, run_path):
    """B3P3 v3: v2 binding + 0003/006F/0002/000C, exactly 26234 bytes.

    The reserved word at 28 becomes two big-endian u16 clip lengths:
    0002 at 28, 000C at 30. Old v1/v2 exports remain byte-identical.
    """
    packet = bytearray(export_transition_packet(model_path, walk_path, idle_path))
    clips = []
    for path, sha in (
        (creep_path, '45695bf12a3f82d0a2a9aaeac7808d4635f4347fedb11d580ae1e332f49c2082'),
        (run_path, 'cf37a93b986be2efe08b86aadf7bf7709331d14237bf8aaad724f7d870d21f23'),
    ):
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('Expected canonical 0002/000C animation')
        clips.append(data)
    struct.pack_into('>I', packet, 4, 3)
    struct.pack_into('>HH', packet, 28, *(len(clip) for clip in clips))
    return bytes(packet) + b''.join(clips)


def export_jump_packet(model_path, walk_path, idle_path, creep_path, run_path, jump_path):
    """B3P3 v4: unchanged v3 payload plus canonical raw 0008.

    Explicit opt-in for the jump viewer. 28022 bytes; no new binding.
    """
    animation = Path(jump_path).read_bytes()
    if hashlib.sha256(animation).hexdigest() != 'b4984d8cfe4aed530a7fb1d62221619b1babac4f79c1697aa85d71ea4847f7e8':
        raise ValueError('Expected canonical 0008 animation')
    packet = bytearray(export_gait_packet(model_path, walk_path, idle_path, creep_path, run_path))
    struct.pack_into('>I', packet, 4, 4)
    return bytes(packet) + animation


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model'); parser.add_argument('animation'); parser.add_argument('output')
    args = parser.parse_args()
    Path(args.output).write_bytes(export_pose_packet(args.model,args.animation))
