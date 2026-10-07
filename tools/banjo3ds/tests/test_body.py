"""E.2 original decomp loop vs isolated production composition."""
import ctypes as C
import functools
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import body_reference as ref
import body_corpus as corpus
import floor_state_reference as floor_ref
import bridge_reference,bridge_corpus,contact_corpus
from ground_corpus import State,Frame
from test_floor_state import State as Floor
from test_bridge_state import State as Bridge,View
from test_world_segment import Hit
from test_camera_contact import Scratch as ContactScratch
from test_camera import Math
from world_query_reference import original
from segment_reference import ROOT,FLAGS
F=C.c_float
class Step(C.Structure):
    _fields_=[(n,F*3) for n in ('position','previous','normal','end','start')]+[('hit',Hit),('contacted',C.c_int)]
class Scratch(C.Structure):_fields_=[('contact',ContactScratch),('steps',Step*5),('trace',corpus.Trace)]

@functools.lru_cache(None)
def production(opt):
    tmp=tempfile.TemporaryDirectory(prefix='body-production-');p=Path(tmp.name)/'body.so';base=ROOT/'tools/banjo3ds'
    names=('body/body.c','ground/ground.c','world_query/segment.c','bridge_state/bridge.c','bridge_state/query_segment.c','bridge_state/query_floor_state.c','bridge_state/query_contact.c','camera/camera.c')
    subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',*[str(base/n) for n in names],'-lm','-o',str(p)],check=True)
    lib=C.CDLL(str(p));lib._tmp=tmp
    lib.bridge_init.argtypes=[C.POINTER(Bridge)];lib.bridge_actor_tick.argtypes=[C.POINTER(Bridge),C.c_uint32];lib.bridge_mesh_tick.argtypes=[C.POINTER(Bridge),F]
    lib.bridge_model_open.argtypes=[C.POINTER(View),C.c_void_p,C.c_size_t,C.POINTER(Bridge)]
    lib.bridge_floor_init.argtypes=[C.POINTER(Floor)]
    lib.bridge_floor_update.argtypes=[C.POINTER(Floor),C.c_void_p,C.c_void_p,C.POINTER(F),F,C.c_uint32,C.c_uint]
    lib.bp_resolve.argtypes=[C.POINTER(corpus.History),C.POINTER(State),C.POINTER(Frame),C.POINTER(Floor),C.POINTER(View),C.POINTER(View),C.POINTER(Math),C.c_uint,C.POINTER(Scratch),C.POINTER(corpus.Trace)]
    return lib

def reference_setup(opt,pos,bits):
    lib=ref.library(opt)
    for role,id in enumerate(('14CF','14D0')):lib.ref_load(role,(ROOT/f'assets/model/{id}.model.bin').read_bytes())
    bridge=bridge_reference.library(opt);contact_corpus.load(bridge,'real');bridge_corpus.configure(bridge,'raw')
    bridge.bridge_ref_actor(bits);bridge.bridge_ref_mesh(F(1/60))
    for ids in bridge_reference.membership().values():
        for v in ids:
            xyz=(C.c_int16*3)();bridge.bridge_ref_xyz(1,v,xyz);lib.body_ref_vertex(1,v,xyz)
    lib.floor_ref_init();lib.body_ref_init(0,0)
    for i in range(6):lib.floor_ref_step((F*3)(*pos),56,0x400000,i&1)
    return lib

def reference_run(opt,case,initial_stuck=0):
    name,pos,end,vy,g,bits=case;lib=reference_setup(opt,pos,bits)
    end=(F*3)(*end);v=F(vy);ground=C.c_uint(g);stuck=C.c_uint(initial_stuck);trace=corpus.Trace()
    r=lib.body_ref_step((F*3)(*pos),end,C.byref(v),0,C.byref(ground),C.byref(stuck),C.byref(trace))
    return r,bytes(end),bytes(v),ground.value,stuck.value,bytes(trace),floor_ref.snapshot(lib)

def production_run(opt,case,initial_stuck=0):
    name,pos,end,vy,g,bits=case;lib=production(opt)
    bridge=Bridge();lib.bridge_init(C.byref(bridge));lib.bridge_actor_tick(C.byref(bridge),bits);lib.bridge_mesh_tick(C.byref(bridge),F(1/60))
    buffers=[C.create_string_buffer(original(a,r)['packet']) for r,a in enumerate((0x14cf,0x14d0))];views=[View(),View()]
    for view,buf in zip(views,buffers):assert lib.bridge_model_open(C.byref(view),buf,len(buf)-1,C.byref(bridge))==1
    floor=Floor();lib.bridge_floor_init(C.byref(floor))
    for i in range(6):assert lib.bridge_floor_update(C.byref(floor),C.byref(views[0].base),C.byref(views[1].base),(F*3)(*pos),56,0x400000,i&1)==1
    state=State((F*3)(*pos),vy,floor.height,g,0);frame=Frame();frame.previous[:]=pos;frame.candidate[:]=end
    frame.requested[:]=[F(frame.candidate[i]-frame.previous[i]).value for i in range(3)];frame.grounded=g
    hist=corpus.History();hist.stuck=initial_stuck;scratch=Scratch();trace=corpus.Trace();math=Math();lib.banjo_camera_math_init(C.byref(math))
    r=lib.bp_resolve(C.byref(hist),C.byref(state),C.byref(frame),C.byref(floor),*[C.byref(v) for v in views],C.byref(math),0,C.byref(scratch),C.byref(trace))
    return r,bytes(state.position),bytes(F(state.vy)),state.grounded,hist.stuck,bytes(trace),bytes(floor)

class BodyTests(unittest.TestCase):
    def test_original_production_all_candidates_O0_O2(self):
        for case in corpus.cases():
            a=reference_run('-O0',case)
            self.assertEqual(a[0],1,case[0])
            self.assertEqual(reference_run('-O2',case),a,('reference optimizations',case[0]))
            for opt in ('-O0','-O2'):
                b=production_run(opt,case)
                if a!=b:
                    for i,(x,y) in enumerate(zip(a,b)):
                        if x!=y:print('FIRST DIFFERENCE',case[0],opt,i,[(j,x[j:j+4].hex(),y[j:j+4].hex()) for j in range(0,len(x),4) if x[j:j+4]!=y[j:j+4]][:10] if isinstance(x,bytes) else (x,y))
                self.assertEqual(b,a,(opt,case[0]))

class ProductionWorld:
    def __init__(self,opt,pos,grounded,bits):
        self.lib=production(opt);lib=self.lib
        self.bridge=Bridge();lib.bridge_init(C.byref(self.bridge));lib.bridge_actor_tick(C.byref(self.bridge),bits);lib.bridge_mesh_tick(C.byref(self.bridge),F(1/60))
        self.buffers=[C.create_string_buffer(original(a,r)['packet']) for r,a in enumerate((0x14cf,0x14d0))];self.views=[View(),View()]
        for view,buf in zip(self.views,self.buffers):assert lib.bridge_model_open(C.byref(view),buf,len(buf)-1,C.byref(self.bridge))==1
        self.floor=Floor();lib.bridge_floor_init(C.byref(self.floor))
        for i in range(6):assert lib.bridge_floor_update(C.byref(self.floor),*[C.byref(v.base) for v in self.views],(F*3)(*pos),56,0x400000,i&1)==1
        self.state=State((F*3)(*pos),0,self.floor.height,grounded,0);self.hist=corpus.History();self.scratch=Scratch();self.math=Math();lib.banjo_camera_math_init(C.byref(self.math))
    def step(self,end,vy,parity):
        s=self.state;s.vy=vy;f=Frame();f.previous[:]=s.position;f.candidate[:]=end
        f.requested[:]=[F(f.candidate[i]-f.previous[i]).value for i in range(3)];f.grounded=s.grounded;t=corpus.Trace()
        r=self.lib.bp_resolve(C.byref(self.hist),C.byref(s),C.byref(f),C.byref(self.floor),*[C.byref(v) for v in self.views],C.byref(self.math),parity,C.byref(self.scratch),C.byref(t))
        return r,bytes(s.position),bytes(F(s.vy)),s.grounded,self.hist.stuck,bytes(t),bytes(self.floor)


def schedule(opt,name,production_side=False):
    # External candidate/physics inputs. Body and persistent floor results feed
    # the next update; no forced replay of an accepted/final floor candidate.
    selected={
        'sustained-wall':((-37.666668,1784,-3751),(0,-.766724,-25),-46,1,8,0x9db1),
        'falling-ledge':((0,1800,391.666779),(0,0,8.333334),-1,1,60,0x9db1),
        'steep-descent':((-3833.333252,2024.666626,-3166.666748),(0,-36.75,0),-735,0,12,0x9db1),
        'corner-history':((-84.333333,1726,-3791),(0,0,-25),-500,0,8,0x9db1),
        'bridge-tutorial':((0,1576,-1770),(0,-.766724,-8.333334),-46,1,20,0),
        'bridge-full':((0,1576,-1770),(0,-.766724,-8.333334),-46,1,20,0x9db1),
    }
    pos,delta,vy,g,count,bits=selected[name];pos=list((F*3)(*pos));v=F(vy);ground=C.c_uint(g);stuck=C.c_uint(0);out=[]
    if production_side:world=ProductionWorld(opt,pos,g,bits)
    else:lib=reference_setup(opt,pos,bits)
    for i in range(count):
        if name=='falling-ledge':
            v=F(v.value+F(F(1/60).value*-2700).value)
            delta=(0,F(v.value*F(1/60).value).value,8.333334)
        end=[F(pos[k]+F(delta[k]).value).value for k in range(3)]
        if production_side:row=world.step(end,v.value,i&1)
        else:
            t=corpus.Trace();end=(F*3)(*end)
            result=lib.body_ref_step((F*3)(*pos),end,C.byref(v),i&1,C.byref(ground),C.byref(stuck),C.byref(t))
            row=result,bytes(end),bytes(v),ground.value,stuck.value,bytes(t),floor_ref.snapshot(lib)
        out.append(row);pos=list((F*3).from_buffer_copy(row[1]));v=F.from_buffer_copy(row[2])
    return out


def packed(row):
    import struct
    # Canonical little-endian float32/uint32 memory snapshots. No pointers;
    # structs have only 4-byte fields/arrays. Trace unused slots are zeroed.
    return struct.pack('<i',row[0])+row[1]+row[2]+struct.pack('<II',row[3],row[4])+row[5]+row[6]


def snapshot_summary(row):
    import struct
    t=corpus.Trace.from_buffer_copy(row[5])
    iterations=[]
    for x in t.iteration[:t.iterations]:
        f=Floor.from_buffer_copy(bytes(x.floor))
        iterations.append(dict(initial=list(x.initial),after_line=list(x.after_line),after_floor=list(x.after_floor),
          start_center=list(x.start_center),end_center=list(x.end_center),normal=list(x.normal),final=list(x.final),
          role=x.role,record=x.record,line_hit=x.line_hit,grounded=x.grounded,paths=x.paths,
          floor_height=f.height,floor_normal=list(f.normal),floor_sha256=hashlib.sha256(bytes(x.floor)).hexdigest()))
    return dict(sha256=hashlib.sha256(packed(row)).hexdigest(),position=list(struct.unpack('=3f',row[1])),
      vy=F.from_buffer_copy(row[2]).value,grounded=row[3],stuck=row[4],pushed_previous=list(t.pushed_previous),
      fallback=list(t.fallback),hits=t.hits,exhausted=t.exhausted,forced=t.forced,iterations=iterations)


def goldens(opt):
    snapshots={case[0]:snapshot_summary(reference_run(opt,case)) for case in corpus.cases()}
    schedules={}
    for name in ('sustained-wall','falling-ledge','steep-descent','corner-history','bridge-tutorial','bridge-full'):
        rows=schedule(opt,name);schedules[name]=dict(count=len(rows),sha256=hashlib.sha256(b''.join(map(packed,rows))).hexdigest(),
            checkpoints={str(i):snapshot_summary(rows[i]) for i in sorted(set((0,1,2,3,len(rows)-1)))})
    return dict(format='E2 little-endian float32/u32 trace v1',cases=snapshots,schedules=schedules,
        history={str(n):snapshot_summary(reference_run(opt,next(c for c in corpus.cases() if c[0]=='corner-0-259-0-25'),n)) for n in range(4)})

class BodyCompositionTests(unittest.TestCase):
    def test_multi_update_state_floor_and_parity_O0_O2(self):
        for name in ('sustained-wall','falling-ledge','steep-descent','corner-history','bridge-tutorial','bridge-full'):
            want=schedule('-O0',name)
            self.assertEqual(schedule('-O2',name),want,name)
            for opt in ('-O0','-O2'):self.assertEqual(schedule(opt,name,True),want,(opt,name))

    def test_known_wall_steep_identity_and_floor_body_distinction(self):
        cases={c[0]:c for c in corpus.cases()}
        wall=reference_run('-O2',cases['wall-258']);t=corpus.Trace.from_buffer_copy(wall[5])
        self.assertEqual(list(t.final),[F(-37.666668).value,1784,-3754.125]);self.assertEqual((t.iterations,t.hits),(2,1))
        for unique,record in ((91,1701),(93,404),(108,260)):
            self.assertIn(record,corpus.triangle(0,unique)[4])
            row=reference_run('-O2',cases[f'steep-{unique}']);t=corpus.Trace.from_buffer_copy(row[5]);first=t.iteration[0]
            self.assertEqual(first.record,record);self.assertEqual(first.grounded,0);self.assertEqual(row[3],0)
            self.assertLess(Floor.from_buffer_copy(bytes(first.floor)).normal[1],.432)
            self.assertNotEqual(list(t.final),list(first.initial));self.assertGreater(t.hits,0)
        eligible=reference_run('-O2',cases['seed-0-237']);t=corpus.Trace.from_buffer_copy(eligible[5])
        self.assertTrue(any(it.role==0 and it.record==476 and it.normal[1]==1 for it in t.iteration[:t.iterations]))
        self.assertEqual(eligible[3],1)
        # A ground-eligible triangle can be a body hit before support is reacquired.

    def test_strict_long_movement_and_zero_motion(self):
        rows={c[0]:reference_run('-O2',c) for c in corpus.cases() if c[0].startswith('long-') or c[0]=='plateau-zero'}
        for name,expected in (('long-65.999755859375',False),('long-66',False),('long-66.000244140625',True)):
            self.assertEqual(bool(corpus.Trace.from_buffer_copy(rows[name][5]).iteration[0].paths&64),expected)
        zero=corpus.Trace.from_buffer_copy(rows['plateau-zero'][5]);self.assertEqual(list(zero.final),[0,1800,0]);self.assertEqual(zero.hits,0)

    def test_new_fixture_matches_independent_original_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/body_golden.json').read_text())
        for opt in ('-O0','-O2'):self.assertEqual(goldens(opt),frozen)

    def test_query_error_is_not_floor_miss_and_atomic(self):
        w=ProductionWorld('-O2',(0,1800,0),1,0x9db1)
        before=bytes(w.state),bytes(w.floor),bytes(w.hist)
        # Explicit outside-domain input. No fabricated successful floor/contact.
        s=w.state;f=Frame();f.previous[:]=s.position;f.candidate[:]=(1e9,1800,0);t=corpus.Trace()
        self.assertEqual(w.lib.bp_resolve(C.byref(w.hist),C.byref(s),C.byref(f),C.byref(w.floor),*[C.byref(v) for v in w.views],C.byref(w.math),0,C.byref(w.scratch),C.byref(t)),-1)
        self.assertEqual((bytes(w.state),bytes(w.floor),bytes(w.hist)),before)

    def test_original_stuck_counter_and_forced_ground_boundary(self):
        case=next(c for c in corpus.cases() if c[0]=='corner-0-259-0-25')
        for before in range(4):
            expected=reference_run('-O0',case,before)
            for opt in ('-O0','-O2'):
                self.assertEqual(reference_run(opt,case,before),expected)
                self.assertEqual(production_run(opt,case,before),expected)
            t=corpus.Trace.from_buffer_copy(expected[5])
            self.assertEqual((t.iterations,t.hits,t.exhausted),(5,5,1))
            self.assertEqual(t.forced,before==3)
            self.assertEqual(expected[4],min(before+1,3))
            self.assertEqual(expected[3],before==3)
