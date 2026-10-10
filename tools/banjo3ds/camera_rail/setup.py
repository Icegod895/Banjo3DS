"""Category-4 rail volumes and the spline chains they name, from canonical 071D.

NodeProp layout is the file order consumed by code7AF80 and gccube.c. Spline
knots follow func_803411B0: unreferenced bit0-clear heads, then position knots
in next-pointer order. No authored camera positions.
"""
import hashlib
import struct
from pathlib import Path

SETUP_SHA256 = 'a0531b7207fad05bc8f22569b9c6148b469f9d37df10f71bf68871619180bba2'


def _read_nodes(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != SETUP_SHA256:
        raise ValueError('rail reader supports only canonical NTSC 071D')
    minimum = struct.unpack_from('>3i', data, 2)
    maximum = struct.unpack_from('>3i', data, 14)
    cursor = 26
    nodes = []
    for x in range(minimum[0], maximum[0] + 1):
        for y in range(minimum[1], maximum[1] + 1):
            for z in range(minimum[2], maximum[2] + 1):
                prop = 0
                while data[cursor] != 1:
                    tag = data[cursor]
                    cursor += 1
                    if tag == 0:
                        cursor += 24
                    elif tag == 2:
                        cursor += 12
                    elif tag == 3:
                        if data[cursor] == 10:
                            count = data[cursor + 1]
                            cursor += 2
                            if data[cursor] == 11:
                                cursor += 1
                                for _ in range(count):
                                    px, py, pz, flags, actor, marker, _pad, w0, w1 = struct.unpack_from(
                                        '>3h2H2B2I', data, cursor)
                                    nodes.append(dict(
                                        cube=(x, y, z), prop=prop,
                                        position=(px, py, pz),
                                        radius=flags >> 7,
                                        category=(flags >> 1) & 63,
                                        bit0=flags & 1,
                                        actor=actor, marker=marker,
                                        scale=w0 & 0x7FFFFF,
                                        spline_id=w1 >> 20,
                                        next=(w1 >> 8) & 0xFFF))
                                    cursor += 20
                                    prop += 1
                        if data[cursor] == 8:
                            count = data[cursor + 1]
                            cursor += 2
                            if data[cursor] == 9:
                                cursor += 1 + count * 12
                    else:
                        raise ValueError(f'unknown cube tag {tag}')
                cursor += 1
    return minimum, maximum, nodes


def _splines(nodes):
    """func_803411B0 position chains, in the order func_80341BC8 records them."""
    by_id = {}
    for node in nodes:
        by_id[node['spline_id']] = node
    if not by_id:
        return []
    referenced = set()
    for node in by_id.values():
        nxt = node['next']
        if nxt > 0 and nxt in by_id:
            referenced.add(nxt)
    heads = []
    for index in range(1, max(by_id) + 1):
        node = by_id.get(index)
        if node and node['next'] > 0 and index not in referenced and node['bit0'] == 0:
            heads.append(index)
    splines = []
    for head in heads:
        knots = []
        seen = set()
        index = head
        while index and index not in seen and index in by_id:
            seen.add(index)
            node = by_id[index]
            if node['bit0'] == 0:
                knots.append(tuple(float(v) for v in node['position']))
            index = node['next']
        if len(knots) >= 2:
            splines.append(dict(head=head, actor=by_id[head]['actor'],
                                 scale=by_id[head]['scale'], knots=knots))
    return splines


def read_rail(path):
    """Category-4 actor 0x16 starts and actor 0x2A clears, plus named splines.

    Marker id 0 maps through sMarkerToBitfield to bit 0. Other marker ids are
    not the player marker and are not eligible for this dry Banjo.
    """
    minimum, maximum, nodes = _read_nodes(path)
    splines = _splines(nodes)
    volumes = []
    for node in nodes:
        # bit0-set nodes are packed out of the func_80307CA0 front group.
        if (node['category'] != 4 or node['actor'] not in (0x16, 0x2A)
                or node['marker'] != 0 or node['bit0'] != 0):
            continue
        # func_80334524(actor-0x16) is the spline node. Clears do not name one.
        lookup = node['actor'] + 0xB6 if node['actor'] == 0x16 else 0
        volumes.append(dict(
            center=node['position'], radius=node['radius'], actor=node['actor'],
            marker_bit=0, spline_actor=lookup, cube=node['cube'], prop=node['prop']))
    for spline in splines:
        spline['origin'] = spline['knots'][0]
    width = tuple(maximum[i] - minimum[i] + 1 for i in range(3))
    return dict(minimum=minimum, maximum=maximum, width=width,
                stride=(width[0], width[0] * width[1]),
                volumes=volumes, splines=splines)
