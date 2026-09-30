"""Candidate schedules, NOT a replacement for Rare's volume-collision loop.
Real map cases use original asset geometry; synthetic pairs isolate state paths.
Each row is (candidate, frame parity, reinitialize). Multiple calls can share parity.
"""
import ctypes as C
import hashlib
import struct
from segment_corpus import synthetic
from segment_reference import load_real
from world_query_reference import original
import floor_state_reference as ref

def cases():
    out={}
    def add(name,points,scene=None,reinit=()):
        out[name]=(scene,[(tuple(C.c_float(x).value for x in p),i&1,i in reinit) for i,p in enumerate(points)])
    add('plateau_init_stationary',[(0,1800,0)]*16)
    add('walk_150',[(i*2.5,1800,0) for i in range(90)])
    add('full_speed_500',[(i*500/60,1800,0) for i in range(120)])
    add('camera_thresholds',[(0,1800+y,0) for y in (0,0,0,0,0,50,129,130,131,200,600,1299,1300,1500,100,0)])
    for name,speed in [('jump_rest',0),('jump_full',500)]:
        points=[(0,1800,0)]*6;y=C.c_float(1800);vy=C.c_float(710);x=C.c_float(0);dt=C.c_float(1/60).value
        for i in range(65):
            vy.value=vy.value+C.c_float(-1350*dt).value
            y.value=y.value+C.c_float(vy.value*dt).value;x.value=x.value+C.c_float(speed*dt).value
            points.append((x.value,max(1800,y.value),0))
        add(name,points)
    add('slope_both_directions',[(-2094-i*.5,133.333344-i*.5*1.35536,-383.666656+i*.5) for i in [*range(40),*range(39,-1,-1)]])
    add('edge_void_return',[(0,1800,0)]*6+[(9000,1800,9000)]*6+[(0,1800,0)]*6)
    add('reinitialize_history',[(0,1800,0)]*8+[(0,2000,0)]*8,reinit=(8,10))
    # A finite ordinary floor at 0 and a special XLU plane: exact original queries.
    ordinary=(0,0x100,False,1000)
    add('state3_stacked',[(0,50,0)]*14, (ordinary,(80,0x20000,False,1000)))
    add('state4_parity_grace',[(0,200,0)]*14+[(200,200,0)]*8, (ordinary,(300,0x20000,False,1000)))
    add('state4_low_both_queries',[(0,200,0)]*8+[(0,100,0)]*8,(ordinary,(300,0x20000,False,1000)))
    add('rejected_ordinary',[(0,50,0)]*10,((0,0x400000,False,1000),(-200,0x100,False,1000)))
    add('negative_normal_fallback',[(0,50,0)]*10,((0,0x100,True,1000),(-200,0x100,False,1000)))
    add('two_sided',[(0,50,0)]*10,((0,0x10100,True,1000),(-200,0x100,False,1000)))
    add('split_far_floor',[(0,800,0)]*10,(ordinary,(-200,0x100,False,1000)))
    add('retained_state3_height',[(0,50,0)]*8+[(200,50,0)]*6,(ordinary,(80,0x20000,False,1000)))
    # Three solver candidate callbacks in one frame: parity intentionally identical.
    out['same_frame_candidates']=(None,[((0,1800+i,0),0,False) for i in range(8)])
    # Real XLU surfaces, including actual special-surface flags.
    r=original(0x14d0,1);points=[]
    for t in dict.fromkeys(r['records']):
        if t[4]&0x1e0000:
            v=[r['xyz'][j] for j in t[:3]]
            p=[sum(a[j] for a in v)/3 for j in range(3)];p[1]-=20
            points.extend([p]*7)
    add('real_xlu_special_surfaces',points)
    return out

def load(lib,scene):
    if scene is None:load_real(lib)
    else:
        for role,spec in enumerate(scene):lib.ref_load(role,C.create_string_buffer(synthetic(role,*spec)[0]))

def run(lib,scene,rows):
    load(lib,scene);lib.floor_ref_init();states=[];queries=[]
    for p,parity,reinit in rows:
        if reinit:lib.floor_ref_reinit()
        lib.floor_ref_step((C.c_float*3)(*p),56,0x400000,parity)
        states.append(ref.snapshot(lib));queries.append(ref.calls(lib))
    return states,queries

def canonical(blob):
    # Original logical 0x60 + 2 provenance triples, explicit endian packing.
    return struct.pack('>I',*struct.unpack_from('=I',blob))+b''.join(
        struct.pack('>4hI',*struct.unpack_from('=4hI',blob,o)) for o in (4,16))+struct.pack(
        '>12fIh2xI8B6i',*struct.unpack_from('=12f',blob,28),
        struct.unpack_from('=I',blob,76)[0],struct.unpack_from('=h',blob,80)[0],
        struct.unpack_from('=I',blob,84)[0],*blob[88:96],*struct.unpack_from('=6i',blob,96))

def golden(lib):
    result={}
    for name,(scene,rows) in cases().items():
        states,queries=run(lib,scene,rows)
        result[name]={'calls':len(rows),'modes':sorted(set(s[94] for s in states)),
            'sha256':hashlib.sha256(b''.join(map(canonical,states))).hexdigest(),
            'states':[canonical(s).hex() for s in states],
            'query_count':sum(map(len,queries)),
            'query_sha256':hashlib.sha256(b''.join(struct.pack('>6fI',*q) for qs in queries for q in qs)).hexdigest()}
    return {'source_sha256':{p:hashlib.sha256((ref.segment.ROOT/p).read_bytes()).hexdigest() for p in ('src/core2/code_94A20.c','include/structs.h','src/core2/code_C4B0.c','src/core2/code_999A0.c')},'packing':'big endian logical 0x60 (normalized model/padding) + 6 signed provenance words', 'cases':result}
