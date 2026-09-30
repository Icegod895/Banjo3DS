"""B3Q1: lossless static-map query data, deliberately separate from movement.

No ray/floor evaluation and no viewer integration. Original vertex/collision
blocks remain byte-for-byte intact, including padding and repeated records.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import struct

HEADER = struct.Struct('>4sHHIfIIII32s')

@dataclass(frozen=True)
class QueryModel:
    role: int  # 0=OPA, 1=XLU
    asset: int
    scale: float
    vertex_offset: int
    collision_offset: int
    source_sha: bytes
    vertex_block: bytes
    collision_block: bytes

    @property
    def vertex_header(self):
        return struct.unpack_from('>12h', self.vertex_block)

    @property
    def grid(self):
        return struct.unpack_from('>11h', self.collision_block)

    @property
    def vertices(self):
        return tuple(struct.unpack_from('>3h', self.vertex_block, 24+16*i)
                     for i in range(self.vertex_header[10]))

    @property
    def cells(self):
        return tuple(struct.unpack_from('>2h', self.collision_block, 24+4*i)
                     for i in range(self.grid[8]))

    @property
    def records(self):
        start = 24+4*self.grid[8]
        return tuple(struct.unpack_from('>4hI', self.collision_block, start+12*i)
                     for i in range(self.grid[10]))

    def validate(self):
        if (self.role, self.asset) not in ((0, 0x14CF), (1, 0x14D0)) or self.scale != 1:
            raise ValueError('only untransformed Spiral Mountain OPA/XLU supported')
        if len(self.vertex_block) < 24 or len(self.collision_block) < 24:
            raise ValueError('truncated source block')
        nv = self.vertex_header[10]
        g = self.grid
        if nv <= 0 or g[8] <= 0 or g[9] < 0 or g[10] < 0:
            raise ValueError('invalid counts/scale')
        if len(self.vertex_block) != 24+16*nv or len(self.collision_block) != 24+4*g[8]+12*g[10]:
            raise ValueError('invalid block length')
        dims = tuple(g[i+3]-g[i]+1 for i in range(3))
        if min(dims) <= 0 or (g[9] and (g[6], g[7], g[8]) != (dims[0], dims[0]*dims[1], dims[0]*dims[1]*dims[2])):
            raise ValueError('invalid grid strides/dimensions')
        for first, count in self.cells:
            if first < 0 or count < 0 or first+count > g[10]:
                raise ValueError('invalid cell range')
        if any(not 0 <= index < nv for r in self.records for index in r[:3]):
            raise ValueError('invalid vertex reference')
        return self

    def serialize(self):
        self.validate()
        return HEADER.pack(b'B3Q1', 1, self.role, self.asset, self.scale,
                           self.vertex_offset, self.collision_offset,
                           len(self.vertex_block), len(self.collision_block), self.source_sha) + self.vertex_block + self.collision_block


def read_model(path, role, asset):
    data = Path(path).read_bytes()
    vo, co = struct.unpack_from('>I', data, 0x10)[0], struct.unpack_from('>I', data, 0x1c)[0]
    if not vo or not co:
        raise ValueError('missing vertex/collision block')
    nv = struct.unpack_from('>h', data, vo+20)[0]
    g = struct.unpack_from('>11h', data, co)
    return QueryModel(role, asset, 1., vo, co, hashlib.sha256(data).digest(),
                      data[vo:vo+24+16*nv], data[co:co+24+4*g[8]+12*g[10]]).validate()


def decode(packet):
    if len(packet) < HEADER.size:
        raise ValueError('truncated packet')
    magic, version, role, asset, scale, vo, co, vl, cl, sha = HEADER.unpack_from(packet)
    if magic != b'B3Q1' or version != 1 or len(packet) != HEADER.size+vl+cl:
        raise ValueError('invalid packet header/length')
    return QueryModel(role, asset, scale, vo, co, sha,
                      packet[64:64+vl], packet[64+vl:]).validate()


def selected_cells(model, minimum, maximum):
    """Original getIntersecting_s32; caller supplies integer padded bounds.

    No global_norm rejection or evolving ray endpoint is performed here.
    Negative exact multiples intentionally differ from mathematical floor().
    """
    g = model.grid
    if g[9] == 0:
        return (0,)
    def axis(v, i):
        q = abs(v)//g[9]
        q = q if v >= 0 else -q-1
        return min(g[i+3], max(g[i], q))-g[i]
    lo = [axis(v, i) for i, v in enumerate(minimum)]
    hi = [axis(v, i) for i, v in enumerate(maximum)]
    return tuple(x+y*g[6]+z*g[7] for z in range(lo[2], hi[2]+1)
                 for y in range(lo[1], hi[1]+1) for x in range(lo[0], hi[0]+1))


def candidates(model, cells, mask):
    """Per-model occurrence stream, not a raycast. OPA wrapper skip preserved.

    The eventual ray caller must visit XLU with the endpoint shortened by OPA;
    this helper intentionally does not pretend to calculate that endpoint.
    """
    if model.role == 0 and mask & 0x80001F00 == 0x80001F00:
        return ()  # supported dataset always has its XLU partner
    ranges, records = model.cells, model.records
    return tuple((model.role, cell, occurrence, records[occurrence])
                 for cell in cells for occurrence in range(ranges[cell][0], sum(ranges[cell]))
                 if not records[occurrence][4] & mask)


def semantic_stream(model):
    """BE header fields + XYZ in original index order + each cell occurrence.

    Cell prefix >I2h: cell index/start/count. Record >I4hI: raw occurrence
    index, original vertex indices, surface, flags. No deduplication.
    """
    out = bytearray(struct.pack('>HIf', model.role, model.asset, model.scale))
    out += struct.pack('>12h11h', *model.vertex_header, *model.grid)
    for v in model.vertices:
        out += struct.pack('>3h', *v)
    records = model.records
    for cell, (first, count) in enumerate(model.cells):
        out += struct.pack('>I2h', cell, first, count)
        for occurrence in range(first, first+count):
            out += struct.pack('>I4hI', occurrence, *records[occurrence])
    return bytes(out)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('asset_directory', type=Path)
    p.add_argument('output_directory', type=Path)
    args = p.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for role, asset in enumerate((0x14CF, 0x14D0)):
        model = read_model(args.asset_directory/f'{asset:04X}.model.bin', role, asset)
        (args.output_directory/f'{asset:04X}.b3q').write_bytes(model.serialize())
