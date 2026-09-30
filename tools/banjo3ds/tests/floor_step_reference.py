"""Independent mathematical floor-following oracle; no production imports.

Binary64 geometry, compared to host float32 with explicit tolerances. The asset
reader follows the original BKModelBin/BKCollisionList layout directly. The
1196 fixture is self-contained; /tmp probes are not inputs to these tests.
"""
import hashlib
import math
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[3]
MIN_NORMAL=.432
WINDOW=30.
SEGMENT_LIMIT=math.floor(WINDOW*MIN_NORMAL/math.sqrt(1-MIN_NORMAL**2))
ASSET_SHA='469f471eb0845c988ba83c7ee759b4572993d669a35ebb1caf9aeab690e7f851'
RECORD_1196=(412,415,413,0,0x100)
VERTICES_1196=((-1937,200,-153),(-1860,-50,-338),(-2485,250,-660))
START_1196=(-2094.,133.33334350585938,-383.6666564941406)
EXPECTED_END_Y=99.44937133789062


def read_14cf():
    data=(ROOT/'assets/model/14CF.model.bin').read_bytes()
    assert hashlib.sha256(data).hexdigest()==ASSET_SHA
    vertex_offset=struct.unpack_from('>I',data,0x10)[0]
    count=struct.unpack_from('>H',data,vertex_offset+20)[0]
    vertices=[struct.unpack_from('>hhh',data,vertex_offset+24+16*i) for i in range(count)]
    collision=struct.unpack_from('>I',data,0x1c)[0]
    cells,_,count=struct.unpack_from('>hhh',data,collision+16)
    first=collision+24+4*cells
    records=list(dict.fromkeys(struct.unpack_from('>hhhhI',data,first+12*i) for i in range(count)))
    return vertices,records


def plane(vertices,record):
    a,b,c=(vertices[i] for i in record[:3])
    u=[b[j]-a[j] for j in range(3)];v=[c[j]-a[j] for j in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    length=math.sqrt(sum(x*x for x in n))
    ny=abs(n[1]) if record[4]&0x10000 else n[1]
    if record[4]&0x005e0000 or not length or ny<MIN_NORMAL*length:return None
    return a,u,v,n,ny/length


def height_inside(p,x,z):
    a,u,v,_,_=p
    det=u[0]*v[2]-u[2]*v[0]
    px,pz=x-a[0],z-a[2]
    s=(px*v[2]-pz*v[0])/det;t=(u[0]*pz-u[2]*px)/det
    if s<0 or t<0 or s+t>1:return None
    return a[1]+s*u[1]+t*v[1]


def floor(vertices,records,x,z,previous_y):
    heights=[]
    for r in records:
        p=plane(vertices,r)
        if p is None:continue
        y=height_inside(p,x,z)
        if y is not None and previous_y-WINDOW<=y<=previous_y+WINDOW:heights.append(y)
    return max(heights) if heights else None


def follow(vertices,records,start,end):
    dx,dz=end[0]-start[0],end[1]-start[2]
    count=max(1,math.ceil(math.hypot(dx,dz)/SEGMENT_LIMIT))
    y=start[1];samples=[]
    for i in range(1,count+1):
        x,z=end if i==count else (start[0]+dx*i/count,start[2]+dz*i/count)
        y=floor(vertices,records,x,z,y)
        if y is None:return None,samples
        samples.append((x,y,z))
    return y,samples


def worst_case():
    """Data-derived maximum plane slope and a real in-triangle 25-unit witness.

    This is a geometric scan, not an assertion about reachability from spawn or
    which layer a gameplay route would select in overlapping geometry.
    """
    vertices,records=read_14cf();maximum=None;witness=None;valid=0
    for i,r in enumerate(records):
        p=plane(vertices,r)
        if p is None:continue
        valid+=1
        a,u,v,n,ny=p
        gx,gz=-n[0]/n[1],-n[2]/n[1];slope=math.hypot(gx,gz)
        row={'record':i,'normal_y':ny,'slope':slope,'max_height_change_25':25*slope,'flags':hex(r[4])}
        if maximum is None or slope>maximum['slope']:maximum=row
        if not slope:continue
        start=tuple(sum(vertices[j][k] for j in r[:3])/3 for k in range(3))
        # A centered segment also catches triangles whose centroid has less
        # than 25 units of clearance in either direction but spans 25 in total.
        for shift in (-25.,-12.5,0.):
            x0,z0=start[0]+shift*gx/slope,start[2]+shift*gz/slope
            x1,z1=x0+25*gx/slope,z0+25*gz/slope
            y0=height_inside(p,x0,z0);y1=height_inside(p,x1,z1)
            if y0 is not None and y1 is not None and (witness is None or slope>witness['slope']):
                witness=dict(row,start=(x0,y0,z0),end=(x1,y1,z1))
    return {'valid_triangles':valid,'maximum':maximum,'witness':witness}

if __name__=='__main__':
    import json
    print(json.dumps(worst_case(),indent=2))
