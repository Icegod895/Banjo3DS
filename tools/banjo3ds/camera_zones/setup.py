"""Canonical 071D host export: original group order, never file-order priority.

code_A5BC0.c:865 reverses camera props within each cube. gccube.c:1557 visits
x-fastest cubes; 1685 appends to first overlapping same-ID group, then 1492
merges connected groups. Existing tagged parser supplies node payloads.
No viewer/build dependency; no generated project artifact.
"""
import struct
from tools.banjo3ds.camera.setup import read_spiral_camera

def read_zones(path):
    data=read_spiral_camera(path)
    raw=path.read_bytes();lo=struct.unpack_from('>3i',raw,2);hi=struct.unpack_from('>3i',raw,14)
    by_offset={t['offset']:t for t in data['triggers']};cubes=[];p=26;enemy_count=0
    for x in range(lo[0],hi[0]+1):
        for y in range(lo[1],hi[1]+1):
            for z in range(lo[2],hi[2]+1):
                records=[]
                while raw[p]!=1:
                    tag=raw[p];p+=1
                    if tag==0:p+=24
                    elif tag==2:p+=12
                    elif tag==3:
                        if raw[p]==10:
                            count=raw[p+1];p+=2
                            if raw[p]==11:
                                p+=1
                                for _ in range(count):
                                    enemy_count+=((int.from_bytes(raw[p+6:p+8],'big')>>1)&63)==7
                                    if p in by_offset:records.append(by_offset[p])
                                    p+=20
                        if raw[p]==8:
                            count=raw[p+1];p+=2
                            if raw[p]==9:p+=1+count*12
                    else:raise ValueError('noncanonical cube')
                p+=1;cubes.append(((z,y,x),records[::-1]))
    def overlaps(a,b):
        return sum((a['position'][i]-b['position'][i])**2 for i in (0,2))<(a['radius']+b['radius'])**2
    groups=[]
    for _,records in sorted(cubes):
        for record in records:
            group=next((g for g in groups if g[0]['node']==record['node'] and any(overlaps(t,record) for t in g)),None)
            if group is None:groups.append([record])
            else:group.append(record)
    # Original merge guard depends on nonempty enemy-boundary groups.
    if enemy_count:
        for i,a in enumerate(groups):
            j=i+1
            while j<len(groups):
                b=groups[j]
                if a and b and a[0]['node']==b[0]['node'] and any(overlaps(t,u) for t in a for u in b):
                    a.extend(b);groups[j]=[];j=i+1
                else:j+=1
        groups=[g for g in groups if g]
    return dict(nodes=data['nodes'],groups=groups,enemy_count=enemy_count)
