"""Explicit 034D near/reset geometry with the original boneless fallback.

This is not general LOD, selector or animation support. Sources:
modelRender.c:657-705,719-789,1092-1137; code_630D0.c:9-36.
Matrices use column vectors; absolute bone matrices already contain parents.
"""
import hashlib
import struct


CANONICAL_SHA256 = '70c8cd03fbd70df07e0c95051d81c7916c8fba603a2be6f3877c2a13c4c047c7'
IDENTITY = ((1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1))


def matrix_product(left, right):
    return tuple(tuple(sum(left[r][k] * right[k][c] for k in range(4))
                       for c in range(4)) for r in range(4))


def matrix_point(matrix, xyz):
    return tuple(sum(matrix[r][c] * xyz[c] for c in range(3)) + matrix[r][3]
                 for r in range(3))


class CanonicalBanjoPose:
    """Lazy geo/RSP command stream; consumed once by the display-list decoder.

The bake is model-local. A fixed camera (0,0,100) is used only for LOD
selection, never baked into positions. World placement is a separate step.
"""
    def __init__(self, model):
        self.model = model
        if hashlib.sha256(model.data).hexdigest() != CANONICAL_SHA256:
            raise ValueError('Canonical Banjo requires the verified 034D asset')
        self.base = IDENTITY
        self.bones = [IDENTITY] * self.read('>h', self.read('>I', 24) + 4)
        self.cpu = [self.base]
        self.rsp = [IDENTITY]
        self.calls = []
        self.loads = []
        self.pops = 0
        self.invalid_references = 0
        self.current_list = 0

    def read(self, fmt, offset):
        return struct.unpack_from(fmt, self.model.data, offset)[0]

    def pop(self):
        if len(self.rsp) <= 1:
            raise ValueError('Canonical RSP matrix stack underflow')
        self.rsp.pop()

    def display_list(self, index):
        self.current_list = index
        self.calls.append(index)
        end = self.read('>I', self.model.gfx_offset)
        for command in range(index, end):
            offset = self.model.gfx_offset + 8 + command * 8
            w0, w1 = struct.unpack_from('>II', self.model.data, offset)
            opcode = w0 >> 24
            if opcode == 0xBD:
                if w1 != 0:
                    raise ValueError('Only modelview G_POPMTX is supported')
                self.pop()
                self.pops += 1
            elif opcode == 0x06:
                if not (0x03000000 <= w1 <= 0x03000080 and w1 % 16 == 0):
                    raise ValueError('Unexpected canonical display-list call')
            elif opcode not in (4,0xBF,0xB1,0xB8,0xB6,0xB7,0xBB,0xE7,
                                0xFC,0xFD,0xF5,0xF0,0xBA,0xF3,0xF2,0xE6):
                raise ValueError(f'Unsupported canonical opcode {opcode:#x}')
            yield offset, w0, w1
            if opcode == 0xB8:
                return
        raise ValueError('Unterminated canonical display list')

    def visit(self, offset):
        while offset:
            kind = self.read('>I', offset)
            if kind == 8:
                maximum, minimum, *point = struct.unpack_from('>5f', self.model.data, offset+8)
                point = matrix_point(self.cpu[-1], point)
                distance = (point[0]**2 + point[1]**2 + (point[2]-100)**2)**0.5
                branch = self.read('>i', offset+28)
                if branch and minimum < distance <= maximum:
                    yield from self.visit(offset+branch)
            elif kind == 12:
                selector = self.read('>h', offset+10)
                # Canonical reset: [00..11]=0, [12..29]=1 (hex indices).
                if not 0 <= selector <= 0x29:
                    raise ValueError('Unexpected canonical selector')
                if selector >= 0x12:
                    branch = self.read('>i', offset+12)
                    if branch:
                        yield from self.visit(offset+branch)
            elif kind == 2:
                bone = self.read('>b', offset+9)
                absolute = IDENTITY if bone == -1 else self.bones[bone]
                self.cpu.append(matrix_product(self.base, absolute))
                self.rsp.append(self.cpu[-1])  # PUSH | LOAD, not multiply.
                branch = self.read('>B', offset+8)
                if branch:
                    yield from self.visit(offset+branch)
                self.cpu.pop()
                self.pop()
            elif kind == 3:
                yield from self.display_list(self.read('>h', offset+8))
            elif kind == 5:
                yield from self.display_list(self.read('>h', offset+8))
                field = offset+10
                while self.read('>h', field):
                    self.rsp.append(self.cpu[-1])
                    yield from self.display_list(self.read('>h', field))
                    field += 2
            elif kind != 10:
                raise ValueError(f'Unsupported canonical geo node {kind:#x}')
            # REFPOINT has no geometry effect without an output sink.
            following = self.read('>i', offset+4)
            offset = offset+following if following else 0

    def commands(self):
        self.rsp.append(self.base)
        yield from self.visit(self.read('>I', 4))
        self.pop()
        if self.cpu != [self.base] or self.rsp != [IDENTITY]:
            raise ValueError('Unbalanced canonical matrix stacks')

    def transform_load(self, vertex, command, slot, source):
        xyz = matrix_point(self.rsp[-1], (vertex.x, vertex.y, vertex.z))
        self.loads.append((command, slot, source, xyz))
        return xyz


def decode_canonical_banjo(model):
    from tools.banjo3ds.n64_displaylist_decoder import interpret_display_list
    return interpret_display_list(model, pose=CanonicalBanjoPose(model))
