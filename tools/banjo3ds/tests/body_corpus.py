"""Static E.2 diagnostic candidates, independent source-asset identities."""
import ctypes as C
import math
from world_query_reference import original
F=C.c_float
class History(C.Structure):_fields_=[('normal',F*3),('stuck',C.c_uint32)]
class Iteration(C.Structure):
    _fields_=[(n,F*3) for n in ('initial','after_line','after_floor','start_center','end_center','normal','final')]+[('role',C.c_int32),('record',C.c_int32),('line_hit',C.c_uint32),('grounded',C.c_uint32),('paths',C.c_uint32),('floor',C.c_uint8*120)]
class Trace(C.Structure):
    _fields_=[(n,F*3) for n in ('pushed_previous','fallback','final','normal')]+[(n,C.c_uint32) for n in ('iterations','hits','exhausted','forced')]+[('iteration',Iteration*5)]

def triangle(role,unique):
    model=original(0x14d0 if role else 0x14cf,role);records=list(dict.fromkeys(model['records']));r=records[unique]
    xyz=[model['xyz'][i] for i in r[:3]]
    a=[xyz[1][i]-xyz[0][i] for i in range(3)];b=[xyz[2][i]-xyz[0][i] for i in range(3)]
    n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    length=math.sqrt(sum(x*x for x in n));n=[x/length for x in n]
    center=[sum(v[i] for v in xyz)/3 for i in range(3)]
    return r,xyz,n,center,[i for i,x in enumerate(model['records']) if x==r]

def cases():
    # name, previous feet, candidate feet, post-physics vy, grounded, abilities
    out=[('wall-258',(-37.666668,1784,-3751),(-37.666668,1783.233276,-3776),-46,1,0x9db1),
         ('steep-91',(-3833.333252,2024.666626,-3166.666748),(-3833.333252,1987.916626,-3166.666748),-735,0,0x9db1),
         ('plateau-flat',(0,1800,0),(0,1799.233276,8.333334),-46,1,0x9db1),
         ('plateau-zero',(0,1800,0),(0,1800,0),0,1,0x9db1),
         ('plateau-ledge',(0,1800,391.666779),(0,1799.233276,400.000122),-46,1,0x9db1),
         ('slope-down',(-2094,133.333344,-383.666656),(-2076.322266,126.53334,-401.34433),-136,1,0x9db1),
         ('slope-up',(-2076.322266,99.449371,-401.34433),(-2094,92.64937,-383.666656),-136,1,0x9db1),
         ('air-wall',(-37.666668,1820,-3751),(-37.666668,1815,-3776),-100,0,0x9db1),
         ('landing-wall',(-37.666668,1790,-3745),(-37.666668,1780,-3776),-200,0,0x9db1)]
    for unique in (93,108):
        _,_,_,c,_=triangle(0,unique)
        out.append((f'steep-{unique}',(c[0],c[1]+10,c[2]),(c[0],c[1]-26.75,c[2]),-735,0,0x9db1))
    for bits in (0,0x9db1):
        out.append((f'bridge-{bits:x}',(0,1576,-1800),(0,1569.2,-1825),-136,1,bits))
    for d in (65.999755859375,66,66.000244140625,80):
        out.append((f'long-{d}',(-37.666668,1784,-3690),(-37.666668,1784,-3690-d),0,1,0x9db1))
    # Source-derived centers/normals: forward endpoint inside the radius,
    # start outside it. Includes two-sided and nonhorizontal surfaces.
    for role,indices in ((0,(91,93,108,237,258,500,1000,1500)),(1,(0,10,50,96,97,98,109,110,111))):
        for unique in indices:
            r,xyz,n,c,occ=triangle(role,unique)
            a=[c[i]+n[i]*45 for i in range(3)];b=[c[i]+n[i]*20 for i in range(3)]
            a[1]-=80;b[1]-=80
            out.append((f'seed-{role}-{unique}',a,b,-10,0,0x9db1))
    for role,unique,gap,distance in ((0, 0, 0, 25), (0, 28, 0, 25), (0, 189, 0, 25), (0, 231, -20, 60), (0, 259, 0, 25), (0, 259, 15, 45), (0, 273, 0, 25), (0, 273, 15, 45), (0, 329, 0, 25), (0, 364, 0, 25), (0, 364, 15, 45), (0, 378, 0, 25), (0, 378, 15, 45), (0, 931, 0, 25), (0, 966, 0, 25), (0, 1008, 0, 25), (0, 1008, 15, 45), (0, 1050, 0, 25), (0, 1092, -20, 60), (0, 1141, 15, 45), (0, 2751, 0, 25), (0, 2807, 15, 45), (1, 168, 0, 25), (1, 171, 0, 25), (1, 174, 0, 25), (1, 174, 15, 45), (1, 189, 0, 25), (1, 192, 0, 25), (1, 198, 0, 25), (1, 198, 15, 45)):
        _,_,n,c,_=triangle(role,unique)
        a=[c[i]+n[i]*gap for i in range(3)];b=[c[i]-n[i]*distance for i in range(3)]
        a[1]-=80;b[1]-=80
        out.append((f'corner-{role}-{unique}-{gap}-{distance}',a,b,-500,0,0x9db1))
    # Reproducible source-derived A/B/A corner search result. Re-evaluate the
    # seven fixed PRNG samples from asset centroids, not a /tmp fixture.
    import random
    rng=random.Random(0xe2)
    for j in range(7):
        role=0 if j%2 else 1
        ids=(237,258,259,273,364,378,1092,1141) if role==0 else (96,97,98,109,110,111,174,192,198)
        _,_,_,c,_=triangle(role,ids[j%len(ids)])
        a=[c[i]+rng.uniform(-80,80) for i in range(3)];a[1]-=80
        delta=[rng.uniform(-70,70) for i in range(3)];b=[a[i]+delta[i] for i in range(3)]
    out.append(('alternating-XLU-A-B-A',a,b,-500,0,0x9db1))
    return out
