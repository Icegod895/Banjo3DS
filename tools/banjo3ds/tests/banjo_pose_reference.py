"""Independent, test-only 034D fallback-pose reference; no production imports.

Sources: src/core2/modelRender.c:657-705,719-789,858,1093-1137;
src/core2/code_630D0.c:9-36,59-104; src/core1/mlmtx.c:195,521;
lib/ultralib/include/PR/gbi.h (F3DEX gSPVertex/gSPPopMatrix).
Column-vector matrices here are the transpose of Rare's stored row matrices.
This is an exact affine reference for identity bones and integer translations,
not an RSP clipping/rasterization emulator or general animation evaluator.

Run as a module to print a JSON report including every load, triangle, stack
transition and final cache. The fixture camera is (0,0,100), object at origin,
scale 1: actual LOD distance is 100. Model-space output removes that camera
translation after transforming at load time.

General original bone composition, in column notation:
 A[j] = A[parent] T(pivot + animation_scale * translation)
        R(quaternion) S(scale) T(-pivot).
BONE loads base * A[j], NOT current CPU matrix * A[j]. This reference
deliberately evaluates only setBoneless (all A[j] = identity); integer
overrides exercise stack/cache semantics without claiming animated accuracy.
SKINNING's first list may pop only the RSP stack. Its subsequent list loads
the still-current CPU matrix with PUSH|LOAD. Cached vertices are snapshots.
REFPOINT is evaluated as if its optional output sink were present.
"""
import hashlib
import json
from pathlib import Path
import struct

ASSET_SHA = '70c8cd03fbd70df07e0c95051d81c7916c8fba603a2be6f3877c2a13c4c047c7'
CALLS = [0,39,48,54,72,81,87,119,137,161,200,209,215,233,242,
         248,280,298,322,379,404,413,419,439,448,454,466,475,
         482,507,516,522,542,551,557,569,578,585,594,602,620,
         657,666,674,972,1295,1349,1358,1368]
IDENTITY = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))


def translation(x, y, z):
    return ((1,0,0,x),(0,1,0,y),(0,0,1,z),(0,0,0,1))


def multiply(a, b):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(4))
                       for j in range(4)) for i in range(4))


def transform(matrix, xyz):
    return tuple(sum(matrix[i][j]*(*xyz, 1)[j] for j in range(4)) for i in range(3))


class PoseReference:
    def __init__(self, data, bone_overrides=None):
        if hashlib.sha256(data).hexdigest() != ASSET_SHA:
            raise ValueError('Canonical 034D asset hash mismatch')
        self.data = data
        self.gfx = self.read('>I', 12) + 8
        self.vtx = self.read('>I', 16) + 24
        animation = self.read('>I', 24)
        self.records = [struct.unpack_from('>3fhh', data, animation + 8 + 16*i)
                        for i in range(self.read('>h', animation + 4))]
        # animMtxList_setBoneless explicitly fills every record with identity;
        # it does NOT apply pivots or parent translations.
        self.bones = [IDENTITY] * len(self.records)
        for index, matrix in (bone_overrides or {}).items():
            self.bones[index] = matrix  # Only for nondegenerate semantic tests.
        self.base = translation(0, 0, -100)
        self.cpu = [self.base]
        self.rsp = [IDENTITY]
        self.cache = [None] * 32
        self.loads, self.triangles, self.calls, self.events, self.refs = [], [], [], [], []
        self.call_ranges = []
        self.nodes = []
        self.push('model', self.base)

    def read(self, fmt, offset):
        return struct.unpack_from(fmt, self.data, offset)[0]

    def event(self, action, location):
        self.events.append(dict(action=action, location=location,
                                cpu_depth=len(self.cpu), rsp_depth=len(self.rsp),
                                cpu_matrix=self.cpu[-1], rsp_matrix=self.rsp[-1]))

    def push(self, location, matrix):
        self.rsp.append(matrix)
        self.event('rsp_push_load', location)

    def pop(self, location):
        if len(self.rsp) <= 1:
            raise ValueError('RSP matrix stack underflow')
        self.rsp.pop()
        self.event('rsp_pop', location)

    def display_list(self, index):
        self.calls.append(index)
        start_load, start_triangle = len(self.loads), len(self.triangles)
        cursor = index
        while True:
            w0, w1 = struct.unpack_from('>II', self.data, self.gfx + 8*cursor)
            op = w0 >> 24
            if op == 0xB8:
                self.call_ranges.append(dict(gfx=index, loads=(start_load, len(self.loads)),
                                             triangles=(start_triangle, len(self.triangles))))
                return  # Cache and matrices survive a DL return.
            if op == 0xBD:
                if w1 != 0:
                    raise ValueError('Unexpected matrix pop target')
                self.pop(cursor)
            elif op == 4:
                first, count = ((w0 >> 16) & 255)//2, (w0 >> 10) & 63
                if w1 >> 24 != 1 or first + count > 32:
                    raise ValueError('Invalid vertex load')
                source = (w1 & 0xffffff)//16
                for n in range(count):
                    raw = struct.unpack_from('>3h', self.data, self.vtx + 16*(source+n))
                    view = transform(self.rsp[-1], raw)
                    entry = dict(load_id=len(self.loads), command=cursor, slot=first+n,
                                 vertex=source+n, raw=raw, view_xyz=view,
                                 xyz=(view[0], view[1], view[2]+100), matrix=self.rsp[-1])
                    self.loads.append(entry)
                    self.cache[first+n] = entry
            elif op in (0xBF, 0xB1):
                for word in ((w0, w1) if op == 0xB1 else (w1,)):
                    slots = [((word >> bit) & 255)//2 for bit in (16,8,0)]
                    if any(s >= 32 or self.cache[s] is None for s in slots):
                        raise ValueError(f'Invalid triangle cache at gfx[{cursor}]')
                    self.triangles.append(tuple(self.cache[s]['load_id'] for s in slots))
            elif op == 6:
                if not (0x03000000 <= w1 <= 0x03000080 and w1 % 16 == 0):
                    raise ValueError('Unexpected display-list call')
                # Verified render-mode table: no matrix/cache changes.
            elif op not in (0xB6,0xB7,0xBB,0xE7,0xFC,0xFD,0xF5,0xF0,0xBA,0xF3,0xF2,0xE6):
                raise ValueError(f'Unsupported command {op:#x}')
            cursor += 1

    def visit(self, offset):
        while offset:
            kind = self.read('>I', offset)
            self.nodes.append((offset, kind))
            if kind == 8:
                maximum, minimum, *point = struct.unpack_from('>5f', self.data, offset+8)
                dist = sum(x*x for x in transform(self.cpu[-1], point)) ** 0.5
                if minimum < dist <= maximum:
                    self.visit(offset + self.read('>i', offset+28))
            elif kind == 2:
                bone = self.read('>b', offset+9)
                matrix = IDENTITY if bone == -1 else self.bones[bone]
                self.cpu.append(multiply(self.base, matrix))
                self.push(offset, self.cpu[-1])
                self.visit(offset + self.read('>B', offset+8))
                self.cpu.pop()
                self.pop(offset)
            elif kind == 3:
                self.display_list(self.read('>h', offset+8))
            elif kind == 5:
                self.display_list(self.read('>h', offset+8))
                field = offset+10
                while self.read('>h', field):
                    self.push(offset, self.cpu[-1])
                    self.display_list(self.read('>h', field))
                    field += 2
            elif kind == 12:
                selector = self.read('>h', offset+10)
                if 0x12 <= selector <= 0x29:
                    self.visit(offset + self.read('>i', offset+12))
            elif kind == 10:
                index, bone, *point = struct.unpack_from('>hh3f', self.data, offset+8)
                matrix = multiply(self.base, IDENTITY if bone == -1 else self.bones[bone])
                self.cpu.append(matrix)
                self.event('refpoint_cpu_push', offset)
                view = transform(matrix, point)
                self.refs.append((offset, index, bone, (view[0], view[1], view[2]+100)))
                self.cpu.pop()
                self.event('refpoint_cpu_pop', offset)
            else:
                raise ValueError(f'Unsupported geo node {kind:#x}')
            following = self.read('>i', offset+4)
            offset = offset+following if following else 0

    def run(self):
        self.visit(self.read('>I', 4))
        self.pop('model')
        if self.calls != CALLS or len(self.cpu) != 1 or self.rsp != [IDENTITY]:
            raise ValueError('Canonical traversal or final matrix stack mismatch')
        return self

    def summary(self):
        xyz = [self.loads[i]['xyz'] for triangle in self.triangles for i in triangle]
        stream = b''.join(struct.pack('>3f', *p) for p in xyz)
        return dict(calls=self.calls, triangles=len(self.triangles), loads=len(self.loads),
                    used_loads=len({i for t in self.triangles for i in t}),
                    bounds=[(min(p[a] for p in xyz), max(p[a] for p in xyz)) for a in range(3)],
                    triangle_xyz_be_f32_sha256=hashlib.sha256(stream).hexdigest(),
                    max_rsp_depth=max(e['rsp_depth'] for e in self.events),
                    max_cpu_depth=max(e['cpu_depth'] for e in self.events),
                    final_cache=[e['vertex'] if e else None for e in self.cache])


def canonical_reference(**kwargs):
    path = Path(__file__).resolve().parents[3] / 'assets/model/034D.model.bin'
    return PoseReference(path.read_bytes(), **kwargs).run()


if __name__ == '__main__':
    reference = canonical_reference()
    print(json.dumps(dict(summary=reference.summary(), events=reference.events,
                         loads=reference.loads, triangles=reference.triangles,
                         call_ranges=reference.call_ranges,
                         nodes=reference.nodes, refpoints=reference.refs,
                         final_cache=reference.cache), indent=2))
