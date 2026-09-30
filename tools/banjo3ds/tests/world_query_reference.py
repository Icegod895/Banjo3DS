"""Independent asset oracle: no production imports. NTSC struct layouts from
include/core2/model.h:225,298,310 and mapModel.c:28,450.
"""
from pathlib import Path
import hashlib
import struct

ROOT = Path(__file__).resolve().parents[3]


def original(asset, role):
    raw = (ROOT/f'assets/model/{asset:04X}.model.bin').read_bytes()
    def number(at, width=2, signed=True):
        return int.from_bytes(raw[at:at+width], 'big', signed=signed)
    vo, co = number(16,4,False), number(28,4,False)
    vh = [number(vo+2*i) for i in range(12)]
    grid = [number(co+2*i) for i in range(11)]
    cells = [(number(co+24+4*i),number(co+26+4*i)) for i in range(grid[8])]
    start = co+24+4*grid[8]
    records = [tuple([number(start+12*i+2*j) for j in range(4)]+[number(start+12*i+8,4,False)]) for i in range(grid[10])]
    xyz = [tuple(number(vo+24+16*i+2*j) for j in range(3)) for i in range(vh[10])]
    vb, cb = raw[vo:vo+24+16*vh[10]], raw[co:start+12*grid[10]]
    # Independent packet construction, not the production struct/serializer.
    prefix = b'B3Q1'+b'\0\1'+role.to_bytes(2,'big')+asset.to_bytes(4,'big')+b'\x3f\x80\0\0'
    for n in (vo,co,len(vb),len(cb)):
        prefix += n.to_bytes(4,'big')
    packet = prefix+hashlib.sha256(raw).digest()+vb+cb
    semantic = struct.pack('>HIf',role,asset,1.)+struct.pack('>23h',*(vh+grid))
    semantic += b''.join(struct.pack('>3h',*v) for v in xyz)
    for i,(first,count) in enumerate(cells):
        semantic += struct.pack('>I2h',i,first,count)
        for j in range(first,first+count):
            semantic += struct.pack('>I4hI',j,*records[j])
    return dict(vh=vh,grid=grid,cells=cells,records=records,xyz=xyz,vb=vb,cb=cb,
                packet=packet,semantic=semantic,source_sha=hashlib.sha256(raw).hexdigest())


def select(ref, lower, upper):
    # Source getIntersecting_s32: C signed truncation then negative correction,
    # independent exhaustive z/y/x enumeration of the original grid bounds.
    g=ref['grid']
    if not g[9]:return [0]
    low=[];high=[]
    for i in range(3):
        for values,out in ((lower,low),(upper,high)):
            cell=int(values[i]/g[9])-(values[i]<0)
            out.append(max(g[i],min(g[i+3],cell)))
    result=[]
    for z in range(g[2],g[5]+1):
        for y in range(g[1],g[4]+1):
            for x in range(g[0],g[3]+1):
                if all(low[i]<=v<=high[i] for i,v in enumerate((x,y,z))):
                    result.append(x-g[0]+(y-g[1])*g[6]+(z-g[2])*g[7])
    return result


def metrics(ref):
    return dict(source_sha256=ref['source_sha'],packet_bytes=len(ref['packet']),
        packet_sha256=hashlib.sha256(ref['packet']).hexdigest(),
        semantic_sha256=hashlib.sha256(ref['semantic']).hexdigest(),
        vertex_block_sha256=hashlib.sha256(ref['vb']).hexdigest(),
        collision_block_sha256=hashlib.sha256(ref['cb']).hexdigest(),
        vertices=len(ref['xyz']),cells=len(ref['cells']),raw_records=len(ref['records']),
        cell_occurrences=sum(n for _,n in ref['cells']),unique_records=len(set(ref['records'])))
