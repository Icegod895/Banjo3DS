"""Host-only camera data reader for the canonical NTSC SM 071D setup.

No model exporter/viewer integration. Read tagged cube records to reach section
3 (never search for a byte pattern); retain all camera triggers so unsupported
zones can be reported by the bounded two-state C module.
Sources: file.c, gccube.c:905, code_A5BC0.c:909/1403, cameranodelist.c:149,
code_33310.c:130, include/prop.h:379. Unknown input is rejected.
"""
import hashlib
from pathlib import Path
import struct

SETUP_SHA256 = 'a0531b7207fad05bc8f22569b9c6148b469f9d37df10f71bf68871619180bba2'


def read_spiral_camera(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != SETUP_SHA256:
        raise ValueError('camera reader supports only canonical NTSC 071D')
    cursor = 0

    def read(fmt):
        nonlocal cursor
        values = struct.unpack_from('>' + fmt, data, cursor)
        cursor += struct.calcsize('>' + fmt)
        return values[0] if len(values) == 1 else values

    def expect(tag):
        if read('B') != tag:
            raise ValueError(f'invalid setup tag at {cursor-1:#x}')

    def optional(tag):
        nonlocal cursor
        if data[cursor] != tag:
            return False
        cursor += 1
        return True

    expect(1)
    expect(1)
    minimum, maximum = read('3i'), read('3i')
    triggers = []
    for _x in range(minimum[0], maximum[0]+1):
        for _y in range(minimum[1], maximum[1]+1):
            for _z in range(minimum[2], maximum[2]+1):
                while not optional(1):
                    tag = read('B')
                    if tag == 0:
                        read('6i')
                    elif tag == 2:
                        read('3i')
                    elif tag == 3:
                        if optional(10):
                            count = read('B')
                            if optional(11):
                                for _ in range(count):
                                    offset = cursor
                                    x, y, z, flags, node, _marker, _pad, _scale, extra = read('3h2H2B2I')
                                    if (flags >> 1) & 63 == 9:
                                        triggers.append(dict(offset=offset, position=(x,y,z), radius=flags >> 7,
                                                             node=node, mask=(7,1,2,4)[extra & 3]))
                        elif optional(6):
                            raise ValueError('OtherNode records outside canonical camera reader')
                        if optional(8):
                            count = read('B')
                            if optional(9):
                                cursor += count*12
                    else:
                        raise ValueError(f'unknown cube tag {tag}')
    expect(0)
    section = cursor
    expect(3)
    nodes = {}
    while not optional(0):
        offset = cursor
        expect(1)
        index = read('h')
        expect(2)
        kind = read('B')
        fields = {}
        while not optional(0):
            tag = read('B')
            if kind == 4:
                if tag != 1:
                    raise ValueError('unknown profile field')
                fmt = 'i'
            elif kind == 2:
                if tag not in (1,2):
                    raise ValueError('unknown static field')
                fmt = '3f'
            else:
                fmt = {1:'3f',2:'2f',3:'2f',4:'3f',5:'I',6:'2f'}[tag]
            fields[tag] = read(fmt)
        nodes[index] = dict(offset=offset, type=kind, fields=fields)
    if data[cursor:] != b'\x04\x00\x00':
        raise ValueError('unexpected lighting/end section')
    node = nodes[32]
    fields = node['fields']
    if node['type'] != 3 or fields[5] & 1:
        raise ValueError('node32 must be zoom without collision')
    zoom = (*fields[1], *fields[4], *fields[2], *fields[3], *fields[6], fields[5])
    return dict(section=section, nodes=nodes, triggers=triggers, zoom=zoom)
