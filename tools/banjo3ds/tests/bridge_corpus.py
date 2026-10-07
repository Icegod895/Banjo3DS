"""Permanent, asset-derived M4.9D bridge diagnostics; no /tmp inputs."""
import ctypes as C
import hashlib
import math
import struct
import bridge_reference as ref
import contact_corpus as contact
import free_b_corpus as free
from world_query_reference import original

F=C.c_float
MODES={'raw':None,'before_all':0,'all_learned':sum(1<<i for i in (15,4,12,11,0,10,7,8,5))}

def configure(lib,mode):
    raw=(ref.ROOT/'assets/model/14D0.model.bin').read_bytes()
    lib.bridge_ref_reset(C.create_string_buffer(raw))
    if MODES[mode] is not None:
        lib.bridge_ref_actor(MODES[mode]);lib.bridge_ref_mesh(F(1/60))

def geometry(lib):
    out=[]
    for vertex in range(len(original(0x14d0,1)['xyz'])):
        xyz=(C.c_int16*3)();lib.bridge_ref_xyz(1,vertex,xyz);out.append(list(xyz))
    return out

def seeds():
    data=original(0x14d0,1);records=list(dict.fromkeys(data['records']));out=[]
    for idx in (109,110,111):
        tri=[data['xyz'][j] for j in records[idx][:3]]
        a=[tri[1][j]-tri[0][j] for j in range(3)];b=[tri[2][j]-tri[0][j] for j in range(3)]
        n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
        length=math.sqrt(sum(x*x for x in n));n=[x/length for x in n]
        center=[sum(v[j] for v in tri)/3 for j in range(3)]
        h=math.hypot(n[0],n[2]);v=[n[0]/h,0,n[2]/h]
        eye=[center[j]+60*v[j] for j in range(3)]
        p=[center[0]+400*v[0],center[1]-375,center[2]+400*v[2]]
        out.append(dict(name=f'seeded-14D0-{idx}',world='real',zones=False,player=p,eye=eye,
                        rotation=[330,math.degrees(math.atan2(-v[0],-v[2]))%360,0]))
    return out

def cases():
    # Preserve old static real-world corpus and add probes of every unique
    # affected triangle at both original and displaced heights. Cells remain
    # ORIGINAL, as in Rare; relocating the grid would be an incorrect fix.
    cases=[c for c in contact.cases() if c[1]=='real']
    d=original(0x14d0,1);records=list(dict.fromkeys(tuple(x[2:]) for x in ref.geometry_manifest()['occurrences']))
    for i,record in enumerate(records):
        tri=[d['xyz'][j] for j in record[:3]]
        a=[tri[1][j]-tri[0][j] for j in range(3)];b=[tri[2][j]-tri[0][j] for j in range(3)]
        n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
        length=math.sqrt(sum(x*x for x in n));n=[x/length for x in n]
        center=[sum(v[j] for v in tri)/3 for j in range(3)]
        for dy in (0,-5000):
            for mask in (0,0x9e0000,0xf800ff0f):
                for k in range(4):
                    a=[center[j]+(10 if k==0 else 50)*n[j]+(dy if j==1 else 0) for j in range(3)]
                    b=[center[j]+(10 if k<3 else -50)*n[j]+(dy if j==1 else 0) for j in range(3)]
                    cases.append((f'bridge-{i}-{dy}-{mask}-{k}','real',k,tuple(F(x).value for x in a),tuple(F(x).value for x in b),35,3,mask))
    return cases

def run(lib,seed,mode):
    free.initialize(lib,seed);configure(lib,mode);frames=[]
    for _ in range(180):
        eye=list((F*3).in_dll(lib,'cameraPosition'))
        q=contact.query(lib,('terrain','real',3,(eye[0],eye[1]+10,eye[2]),(eye[0],eye[1]-600,eye[2]),0,0,0x800000))
        assert q[0]>=0
        under=q[1][1] if q[0] else F(eye[1]-600).value
        p=seed['player'];cmd=free.command(p,target=[p[0],p[1]+80,p[2]],under=under)
        result=free.step(lib,cmd);frames.append((cmd,result))
    return frames

def sha(b):return hashlib.sha256(b).hexdigest()

def golden(lib):
    result=dict(manifest=ref.geometry_manifest(),setup=ref.actor_setup(),query_count=len(cases()),states={},schedules={})
    queries=cases()
    result['query_inputs_sha256']=sha(b''.join(struct.pack('>i6ffiI',c[2],*c[3],*c[4],c[5],c[6],c[7]) for c in queries))
    for mode in MODES:
        contact.load(lib,'real');configure(lib,mode);xyz=geometry(lib)
        stream=b''.join(struct.pack('>3h',*v) for v in xyz)
        q=[contact.query(lib,c) for c in queries];assert all(v[0]>=0 for v in q)
        result['states'][mode]=dict(xyz_sha256=sha(stream),
            bridge_xyz=[xyz[v] for v in result['manifest']['vertex_ids']],
            queries_sha256=sha(b''.join(contact.pack_query(v) for v in q)),hits=sum(v[0] for v in q))
    for seed in seeds():
        baseline=run(lib,seed,'raw');out={}
        for mode in MODES:
            frames=baseline if mode=='raw' else run(lib,seed,mode)
            packed=[free.packed(*r) for _,r in frames]
            first=next((i+1 for i,((_,a),(_,b)) in enumerate(zip(frames,baseline)) if free.packed(*a)!=free.packed(*b)),None)
            out[mode]=dict(updates=len(frames),sha256=sha(b''.join(packed)),first_difference_from_raw=first,
                maximum_xyz_difference=max(math.dist(a[1][0][:3],b[1][0][:3]) for a,b in zip(frames,baseline)),
                final_xyz=frames[-1][1][0][:3],rollbacks=sum(r[4].rolled_back for _,r in frames),
                recoveries=sum(r[4].contact.recovered for _,r in frames))
        result['schedules'][seed['name']]=out
    return result
