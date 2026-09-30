"""Independent deterministic inputs and output packing for query goldens."""
import ctypes as C
import hashlib
import random
import struct
from segment_reference import ROOT, original
F=C.c_float

def corpus():
    cases=[]
    def add(name,a,b,mask=0x800000):cases.append((name,tuple(map(lambda x:F(x).value,a)),tuple(map(lambda x:F(x).value,b)),mask))
    for x,z in ((0,0),(-2094,-383.666656),(501.5,-6064),(-6259,-2719),(-1600,-3200),(1600,3200),(0,-1),(20000,20000)):
        for top,bottom in ((1810,1200),(7000,-800),(1800,1799),(1801,1800)):
            add('vertical', (x,top,z),(x,bottom,z))
    add('cell102',(501.5,3472,-6064),(501.5,2872,-6064),0)
    for x,z in ((-1599,-3199),(-1601,-3201)):
        for mask in (0,0x800000,0x400000,0xf800ff0f):
            add('negative-exact-padded-bound',(x,3000,z),(x,-500,z),mask)
    for role,asset in enumerate((0x14cf,0x14d0)):
        r=original(asset,role);unique=list(dict.fromkeys(r['records']))
        for i,t in enumerate(unique):
            if i%7 and not t[4]&0x10000:continue
            tri=[r['xyz'][j] for j in t[:3]]
            center=tuple(sum(v[j] for v in tri)/3 for j in range(3))
            for mask in (0,0x800000,0x400000,0xf800ff0f):
                add(f'centroid-{role}-{i}',(center[0],center[1]+75,center[2]),(center[0],center[1]-75,center[2]),mask)
            # Upward approach tests normal flip independently of floor eligibility.
            add('upward',(center[0],center[1]-50,center[2]),(center[0],center[1]+50,center[2]),0)
            if i%21==0:
                for point in (tri[0],tuple((tri[0][j]+tri[1][j])/2 for j in range(3))):
                    add('vertex-or-edge',(point[0],point[1]+10,point[2]),(point[0],point[1]-10,point[2]),0)
                    add('start-on-surface',point,(point[0],point[1]-10,point[2]),0)
                    add('end-on-surface',(point[0],point[1]+10,point[2]),point,0)
    rng=random.Random(1487)
    for i in range(400):
        a=(rng.uniform(-9000,9000),rng.uniform(-500,7000),rng.uniform(-8000,8000))
        b=tuple(a[j]+rng.uniform(-2400,2400) for j in range(3))
        add('multi-cell',a,b,(0,0x800000,0x5e0000,0xf800ff0f)[i%4])
    return cases

def cameras():
    return [(0,y,0) for y in (1790,1800,1801,2399,2400,2401,2500)]+[
        (a[0],a[1]+100,a[2]) for _,a,_,_ in corpus()[::17]]

def query(lib,a,b,mask):
    start=(F*3)(*a);end=(F*3)(*b);normal=(F*3)(101,102,103);info=(C.c_int32*8)(*([-1]*8))
    hit=lib.ref_query(start,end,mask,normal,info)
    return hit,list(end),list(normal),list(info)

def packed(result):
    h,e,n,ids=result
    return struct.pack('>i6f8i',h,*e,*n,*ids)

def input_hash(cases):
    return hashlib.sha256(b''.join(struct.pack('>6fI',*a,*b,m) for _,a,b,m in cases)).hexdigest()

def golden(lib):
    cases=corpus();results=[query(lib,a,b,m) for _,a,b,m in cases]
    camera=[]
    for p in cameras():
        hit=C.c_int32();y=lib.ref_terrain((F*3)(*p),C.byref(hit));camera.append((hit.value,y))
    return dict(count=len(cases),input_sha256=input_hash(cases),
        output_sha256=hashlib.sha256(b''.join(packed(r) for r in results)).hexdigest(),
        hits=sum(r[0] for r in results),opa_hits=sum(r[0] and r[3][0]==0 for r in results),
        xlu_hits=sum(r[0] and r[3][0]==1 for r in results),
        camera_count=len(camera),camera_hits=sum(h for h,_ in camera),
        camera_sha256=hashlib.sha256(b''.join(struct.pack('>if',*r) for r in camera)).hexdigest(),
        cell102=list(results[32]))


def synthetic(role, height, flags=0, reverse=False, radius=1000):
    """Independent minimal native asset + B3Q1, one grid cell/one triangle."""
    vertices=[(-100,height,-100),(0,height,100),(100,height,-100)]
    vh=struct.pack('>12h',-100,height,-100,100,height,100,0,height,0,300,3,radius)
    vb=vh+b''.join(struct.pack('>3h10x',*v) for v in vertices)
    cb=struct.pack('>11h2x',0,0,0,0,0,0,1,1,1,0,1)+struct.pack('>2h',0,1)
    cb+=struct.pack('>4hI',*( (2,1,0) if reverse else (0,1,2)),7+role,flags)
    vo=64;co=vo+len(vb);raw=bytearray(64);struct.pack_into('>I',raw,16,vo);struct.pack_into('>I',raw,28,co);raw+=vb+cb
    packet=struct.pack('>4sHHIfIIII32s',b'B3Q1',1,role,0x14cf+role,1.,vo,co,len(vb),len(cb),hashlib.sha256(raw).digest())+vb+cb
    return bytes(raw),packet


def wrapper_cases():
    # label, opa (height,flags,reverse,radius), xlu, start, end, mask, expected role
    return [
        ('opa-nearest',(100,0,False,1000),(0,0,False,1000),(0,200,0),(0,-100,0),0,0),
        ('xlu-replaces-shortened-opa',(0,0,False,1000),(100,0,False,1000),(0,200,0),(0,-100,0),0,1),
        ('equal-xlu-endpoint-excluded',(0,0,False,1000),(0,0,False,1000),(0,200,0),(0,-100,0),0,0),
        ('special-opa-skip',(100,0,False,1000),(0,0,False,1000),(0,200,0),(0,-100,0),0xf800ff0f,1),
        ('filtered-opa-then-xlu',(100,0x800000,False,1000),(0,0,False,1000),(0,200,0),(0,-100,0),0x800000,1),
        ('no-hit',(100,0,False,1000),(0,0,False,1000),(500,200,500),(500,-100,500),0,-1),
        ('start-contact-excluded',(0,0,False,1000),(-200,0,False,1000),(0,0,0),(0,-100,0),0,-1),
        ('end-contact-excluded',(0,0,False,1000),(-200,0,False,1000),(0,100,0),(0,0,0),0,-1),
        ('backface-keeps-down-normal',(0,0,True,1000),(-200,0,False,1000),(0,100,0),(0,-100,0),0,0),
        ('two-sided-flips-normal',(0,0x10000,True,1000),(-200,0,False,1000),(0,100,0),(0,-100,0),0,0),
        ('global-norm-early-reject',(0,0,False,10),(-200,0,False,1000),(20,100,0),(20,-100,0),0,-1),
        ('all-flags-filtered',(0,0x100,False,1000),(-20,0x200,False,1000),(0,100,0),(0,-100,0),0xffffffff,-1),
        ('vertex-included',(0,0,False,1000),(-200,0,False,1000),(-100,10,-100),(-100,-10,-100),0,0),
        ('edge-included',(0,0,False,1000),(-200,0,False,1000),(0,10,-100),(0,-10,-100),0,0),
        ('near-surface',(0,0,False,1000),(-200,0,False,1000),(0,2**-20,0),(0,-2**-20,0),0,0),
        ('zero-length',(0,0,False,1000),(-200,0,False,1000),(0,0,0),(0,0,0),0,-1),
    ]


def cell102_variant():
    r=original(0x14cf,0);raw=bytearray((ROOT/'assets/model/14CF.model.bin').read_bytes())
    co=struct.unpack_from('>I',raw,28)[0];base=co+24+4*r['grid'][8];first,n=r['cells'][102]
    ids={t:i for i,t in enumerate(dict.fromkeys(r['records']))}
    rows=sorted(r['records'][first:first+n],key=lambda t:ids[t])
    raw[base+12*first:base+12*(first+n)]=b''.join(struct.pack('>4hI',*t) for t in rows)
    return bytes(raw)


def extended_golden(lib):
    from segment_reference import load_real
    g=golden(lib)
    wrapper={}
    for label,o,x,a,b,mask,expected in wrapper_cases():
        for role,spec in enumerate((o,x)):
            raw,_=synthetic(role,*spec);lib.ref_load(role,C.create_string_buffer(raw))
        result=query(lib,a,b,mask)
        assert (result[3][0] if result[0] else -1)==expected
        wrapper[label]=list(result)
    g['wrapper_cases']=wrapper
    load_real(lib)
    a=(772.25,2868.,-5206.);b=(772.25,2568.,-5206.)
    g['cell102_witness_original']=list(query(lib,a,b,0))
    lib.ref_load(0,C.create_string_buffer(cell102_variant()))
    g['cell102_witness_reordered']=list(query(lib,a,b,0))
    load_real(lib)
    g['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
        'src/core2/code_5FD90.c','src/core2/mapModel.c','src/core1/code_72B0.c',
        'src/core2/nc/dynamicCamera.c','src/core1/ml.c','include/math.h','include/core2/model.h')}
    return g
