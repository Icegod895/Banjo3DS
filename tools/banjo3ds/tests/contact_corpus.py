"""Deterministic independent inputs and canonical output packing."""
import ctypes as C
import hashlib
import math
import struct
import contact_reference as ref
from world_query_reference import original

F=C.c_float
class State(C.Structure):
    _fields_=[('counter',C.c_uint32),('position_step',F*3),('angular_step',F*3)]
class Trace(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('sphere_calls','line_calls','moving_calls','gated_calls','obstruction_calls','recovery_attempts','changed','recovered')]+[(n,F*3) for n in ('pushed_previous','extended_end','subtracted_end')]

def synthetic(role,vertices,records,cells=None,grid=None):
    """Native asset + independent B3Q1 single-cell fixture; no production imports."""
    lo=[min(v[i] for v in vertices) for i in range(3)];hi=[max(v[i] for v in vertices) for i in range(3)]
    vb=struct.pack('>12h',*lo,*hi,0,0,0,30000,len(vertices),30000)
    vb+=b''.join(struct.pack('>3h10x',*v) for v in vertices)
    cells=cells or [(0,len(records))]
    grid=grid or (0,0,0,0,0,0,1,1,1,0)
    cb=struct.pack('>11h2x',*grid,len(records))+b''.join(struct.pack('>2h',*c) for c in cells)
    cb+=b''.join(struct.pack('>4hI',*r) for r in records)
    vo=64;co=vo+len(vb);raw=bytearray(64);struct.pack_into('>I',raw,16,vo);struct.pack_into('>I',raw,28,co);raw+=vb+cb
    packet=struct.pack('>4sHHIfIIII32s',b'B3Q1',1,role,0x14cf+role,1.,vo,co,len(vb),len(cb),hashlib.sha256(raw).digest())+vb+cb
    return bytes(raw),packet

def wall(x=0,flags=0):
    # +X normal. Big enough for the state-B ±100 target probes.
    return [(x,-1000,-1000),(x,1000,-1000),(x,0,1000)],[(0,1,2,7,flags)]

def worlds():
    return {
        'opa':(wall(),wall(-1000)),
        'xlu':(wall(-1000),wall()),
        'shared':(wall(),wall(10)),
        'shared-xlu-only':(wall(-1000),wall(10)),
        'reverse':(wall(0,0x10000),wall(-1000)),
        'filtered':(wall(0,0x800000),wall(-1000)),
        'order':(wall()[0],[(0,1,2,7,0),(0,2,1,8,0)]),
    }

def world(name):
    if name=='real':
        return [((ref.ROOT/f'assets/model/{a:04X}.model.bin').read_bytes(),original(a,r)['packet']) for r,a in enumerate((0x14cf,0x14d0))]
    if name=='duplicates':
        vertices=wall()[0]+[(-1000,-1000,0),(1000,-1000,0),(0,1000,0)]
        records=[(0,1,2,7,0),(3,4,5,8,0),(0,1,2,7,0)]
        return [synthetic(0,vertices,records,[(0,2),(2,1)],(-1,0,0,0,0,0,2,2,2,1000)),synthetic(1,*wall(-1000))]
    if name=='order':spec=(worlds()['order'],wall(-1000))
    else:spec=worlds()[name]
    return [synthetic(r,*s) for r,s in enumerate(spec)]

def cases():
    # name, world, primitive (0 sphere/1 moving/2 gate/3 line), start,end,r,steps,mask
    cases=[]
    def add(name,w,k,a,b,r=35,steps=3,mask=0x9e0000):
        cases.append((name,w,k,tuple(F(v).value for v in a),tuple(F(v).value for v in b),r,steps,mask))
    for w in ('opa','xlu','shared','reverse','filtered','order'):
        for k in range(4):
            add(f'{w}-{k}',w,k,(50,0,0),(20,0,0) if k<3 else (-20,0,0))
    for d in (34.499996,34.5,34.500004,35,100):
        add('tangent-'+str(d),'opa',0,(d,0,0),(d,0,0))
    for p in ((1,-1000,-1000),(1,0,-1000),(1,-1020,-1000),(1,-1040,-1000)):
        add('vertex-edge','opa',0,p,p)
    for d in (34.999996,35,35.000004):
        add('gate-'+str(d),'opa',2,(50,0,0),(50-d,0,0))
    add('endpoint-no-overlap','opa',1,(50,0,0),(-50,0,0))
    add('bisect','opa',1,(50,0,0),(20,0,0))
    add('bisect-four','opa',1,(55,0,0),(20,0,0),r=40,steps=4)
    add('bisect-zero','opa',1,(50,0,0),(20,0,0),steps=0)
    add('moving-stationary-overlap','opa',1,(20,0,0),(20,0,0))
    add('shared-mutated-endpoint','shared',1,(50,0,0),(15,0,0))
    add('xlu-original-endpoint','shared-xlu-only',1,(50,0,0),(15,0,0))
    add('special-line','shared',3,(50,0,0),(-20,0,0),mask=0xf800ff0f)
    add('special-sphere-no-skip','opa',0,(20,0,0),(20,0,0),mask=0xf800ff0f)
    add('special-moving-no-skip','opa',1,(50,0,0),(20,0,0),mask=0xf800ff0f)
    add('backface-reject','opa',1,(-50,0,0),(-20,0,0))
    add('two-sided-flip','reverse',1,(-50,0,0),(-20,0,0))
    add('sphere-no-two-sided-flip','reverse',0,(-20,0,0),(-20,0,0))
    add('duplicate-cell-normal','duplicates',0,(5,0,5),(5,0,5))
    add('duplicate-cell-moving','duplicates',1,(45,0,45),(20,0,20))
    for role,asset in enumerate((0x14cf,0x14d0)):
        r=original(asset,role);unique=list(dict.fromkeys(r['records']))
        for i,t in enumerate(unique):
            if i%13 and not t[4]&0x10000:continue
            tri=[r['xyz'][j] for j in t[:3]]
            ab=[tri[1][j]-tri[0][j] for j in range(3)];ac=[tri[2][j]-tri[0][j] for j in range(3)]
            n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
            length=math.sqrt(sum(v*v for v in n))
            if not length:continue
            n=[v/length for v in n];p=[sum(v[j] for v in tri)/3 for j in range(3)]
            for k in (0,1,2,3):
                a=[p[j]+(10 if k==0 else 45)*n[j] for j in range(3)]
                b=[p[j]+(20 if k<3 else -10)*n[j] for j in range(3)]
                add(f'real-{role}-{i}-{k}','real',k,a,b)
            if i%39==0:
                for p in (tri[0],[(tri[0][j]+tri[1][j])/2 for j in range(3)]):
                    a=[p[j]+2*n[j] for j in range(3)]
                    add(f'real-edge-{role}-{i}','real',0,a,a,mask=0)
    for p in ((-1600,100,-3200),(-1600,1800,0),(0,1800,0),(1600,1500,3200),(20000,0,20000)):
        for k in (0,1):add('grid-boundary','real',k,p,(p[0],p[1]-25,p[2]))
    return cases

def query(lib,case):
    _,_,k,a,b,r,steps,mask=case
    aa=(F*3)(*a);bb=(F*3)(*b);n=(F*3)(101,102,103);info=(C.c_int32*8)(*([-1]*8))
    hit=lib.ref_contact_query(k,aa,bb,r,steps,mask,n,info)
    return [hit,list(bb),list(n),list(info)]

def pack_query(result):
    h,e,n,ids=result
    return struct.pack('>i6f8i',h,*e,*n,*ids)

def update(lib,previous,camera,target,state,obstruction=True):
    a=(F*3)(*previous);b=(F*3)(*camera);t=Trace()
    result=lib.ref_contact_update(obstruction,a,b,(F*3)(*target),C.byref(state),C.byref(t))
    return [result,list(a),list(b),[state.counter,*state.position_step,*state.angular_step],trace_values(t)]

def trace_values(t):
    return [getattr(t,n) for n,_ in Trace._fields_[:8]]+list(t.pushed_previous)+list(t.extended_end)+list(t.subtracted_end)

def pack_update(result):
    h,a,b,s,t=result
    return struct.pack('>i6fI6f8I9f',h,*a,*b,*s,*t)

def schedules():
    # Qualifying sequence supplies the documented pre-contact previous/desired;
    # it is NOT a simulated free-B smoothing trajectory or a collision renderer.
    return [
        ('previous-pushout','opa',True,[( (20,0,0),(60,0,0),(200,0,0))]),
        ('unchanged-preserves-counter','opa',True,[((100,0,0),(120,0,0),(-200,0,0))]),
        ('line-extension','opa',False,[((100,0,0),(20,0,0),(-200,0,0))]),
        ('miss-resets','opa',True,[((100,0,0),(20,0,0),(200,0,0))]),
        ('five-qualifying','opa',True,[((100,0,0),(20,0,0),(-400,0,0))]*5),
        ('five-recovery-fails','opa',True,[((100,0,0),(20,0,0),(-20,0,0))]*5),
        ('xlu','xlu',True,[((100,0,0),(20,0,0),(-400,0,0))]*5),
        ('shared','shared',True,[((100,0,0),(20,0,0),(-400,0,0))]*5),
        ('real-opa-wall','real',True,[((1725.329674305655,123.33333333333333,-3052.284905538222),
            (1682.3992681944644,123.33333333333333,-3119.7903144409775),
            (1564.34065138869,123.33333333333333,-3305.4301889235558))]),
        ('real-xlu-wall','real',True,[((0,1900,-2360),(0,1900,-2390),(0,1900,-2600))]),
        ('real-plateau','real',True,[((0,1820,0),(0,1810,0),(0,1880,0))]),
    ]

def load(lib,name):
    data=world(name)
    for role,(raw,_) in enumerate(data):lib.ref_load(role,C.create_string_buffer(raw))
    return data

def golden(lib):
    results=[];last=None;inputs=[];explicit=[]
    for case in cases():
        if case[1]!=last:load(lib,case[1]);last=case[1]
        r=query(lib,case)
        if r[0]<0:raise AssertionError(('original fixed buffer overflow',case))
        results.append(r)
        if case[1]!='real':explicit.append([case[0],r])
        inputs.append(struct.pack('>i6ffiI',case[2],*case[3],*case[4],case[5],case[6],case[7]))
    sequences={}
    for name,w,obs,steps in schedules():
        load(lib,w);state=State(2 if 'counter' in name or name=='miss-resets' else 0,(F*3)(1,2,3),(F*3)(4,5,6))
        seq=[update(lib,*step,state,obs) for step in steps]
        assert all(s[0]>=0 for s in seq),name
        sequences[name]=seq
    return {'count':len(results),'input_sha256':hashlib.sha256(b''.join(inputs)).hexdigest(),
        'output_sha256':hashlib.sha256(b''.join(map(pack_query,results))).hexdigest(),
        'hits':sum(r[0] for r in results),'opa_hits':sum(r[0] and r[3][0]==0 for r in results),
        'xlu_hits':sum(r[0] and r[3][0]==1 for r in results),
        'sequence_sha256':hashlib.sha256(b''.join(pack_update(r) for seq in sequences.values() for r in seq)).hexdigest(),
        'explicit_primitives':explicit,'sequences':sequences}
