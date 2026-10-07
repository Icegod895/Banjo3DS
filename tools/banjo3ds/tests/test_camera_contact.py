import ctypes as C
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import contact_reference as ref
import contact_corpus as corpus
from test_world_segment import Model,Hit

F=C.c_float
class Triangle(C.Structure):
    _fields_=[('ab',F*3),('ac',F*3),('normal',F*3),('xyz',(F*3)*3),('record',C.c_int32),('cell',C.c_int32)]
class Scratch(C.Structure):
    _fields_=[('triangles',Triangle*100)]

class CameraContactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='contact-test-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[]
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*ref.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                str(ref.ROOT/'tools/banjo3ds/world_query/segment.c'),str(ref.ROOT/'tools/banjo3ds/camera_contact/contact.c'),'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));mp=C.POINTER(Model);fp=C.POINTER(F);hp=C.POINTER(Hit);sp=C.POINTER(Scratch)
            lib.bq_open.argtypes=[mp,C.c_void_p,C.c_size_t]
            lib.bq_segment.argtypes=[mp,mp,fp,fp,C.c_uint32,hp]
            lib.bc_sphere.argtypes=[mp,mp,fp,F,C.c_uint32,hp]
            for n in ('bc_moving','bc_gated'):getattr(lib,n).argtypes=[mp,mp,fp,fp,F,C.c_int,C.c_uint32,sp,hp]
            lib.bc_contact.argtypes=[mp,mp,fp,fp,sp,C.POINTER(corpus.Trace)]
            lib.bc_state_b.argtypes=[mp,mp,fp,fp,fp,C.POINTER(corpus.State),sp,C.POINTER(corpus.Trace)]
            cls.libs.append(lib);cls.refs.append(ref.library(opt))

    def models(self,lib,data):
        buffers=[C.create_string_buffer(p) for _,p in data];models=[Model(),Model()]
        for m,b in zip(models,buffers):self.assertEqual(lib.bq_open(C.byref(m),b,len(b)-1),1)
        return models,buffers

    def query(self,lib,models,case):
        _,_,k,a,b,r,steps,mask=case;a=(F*3)(*a);b=(F*3)(*b);out=Hit();scratch=Scratch()
        C.memset(C.byref(out),0xa5,C.sizeof(out));old=bytes(out);old_b=bytes(b)
        args=[C.byref(m) for m in models]
        if k==0:h=lib.bc_sphere(*args,a,r,mask,C.byref(out))
        elif k==3:h=lib.bq_segment(*args,a,b,mask,C.byref(out))
        else:h=getattr(lib,'bc_moving' if k==1 else 'bc_gated')(*args,a,b,r,steps,mask,C.byref(scratch),C.byref(out))
        if h==1:
            self.assertEqual(bytes(out.position),bytes(a if k==0 else b))
            return h,list(b),list(out.normal),[out.role,out.occurrence,out.cell,out.surface,C.c_int32(out.flags).value,*out.indices]
        self.assertEqual(bytes(out),old);self.assertEqual(bytes(b),old_b)
        return h,list(b),[101.,102.,103.],[-1]*8

    def update(self,lib,models,previous,camera,target,state,obs):
        a=(F*3)(*previous);b=(F*3)(*camera);t=corpus.Trace();scratch=Scratch();args=[C.byref(m) for m in models]
        if obs:r=lib.bc_state_b(*args,a,b,(F*3)(*target),C.byref(state),C.byref(scratch),C.byref(t))
        else:r=lib.bc_contact(*args,a,b,C.byref(scratch),C.byref(t))
        return r,list(a),list(b),[state.counter,*state.position_step,*state.angular_step],corpus.trace_values(t)

    def test_original_primitives_bit_exact_O0_O2(self):
        for lib,oracle in zip(self.libs,self.refs):
            last=None
            for case in corpus.cases():
                if case[1]!=last:
                    data=corpus.load(oracle,case[1]);models,buffers=self.models(lib,data);last=case[1]
                want=corpus.query(oracle,case);got=self.query(lib,models,case)
                self.assertGreaterEqual(want[0],0,case)
                self.assertEqual(corpus.pack_query(got),corpus.pack_query(want),(case,got,want))

    def test_original_correction_and_qualifying_counter_bit_exact(self):
        for lib,oracle in zip(self.libs,self.refs):
            for name,w,obs,steps in corpus.schedules():
                models,buffers=self.models(lib,corpus.load(oracle,w))
                s=corpus.State(2 if 'counter' in name or name=='miss-resets' else 0,(F*3)(1,2,3),(F*3)(4,5,6));p=corpus.State.from_buffer_copy(s)
                for step in steps:
                    want=corpus.update(oracle,*step,s,obs);got=self.update(lib,models,*step,p,obs)
                    self.assertEqual(corpus.pack_update(got),corpus.pack_update(want),(name,step,got,want))

    def test_frozen_independent_goldens(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_contact_golden.json').read_text())
        for oracle in self.refs:self.assertEqual(corpus.golden(oracle),frozen)

    def test_explicit_contact_boundaries(self):
        lib=self.libs[1];oracle=self.refs[1];cases=corpus.cases();results={}
        for case in cases:
            if case[1]=='real':continue
            models,buffers=self.models(lib,corpus.load(oracle,case[1]))
            results[case[0]]=self.query(lib,models,case)
        for name in ('gate-34.999996','gate-35','bisect','special-sphere-no-skip','special-moving-no-skip','two-sided-flip'):
            self.assertEqual(results[name][0],1,name)
        for name in ('gate-35.000004','endpoint-no-overlap','tangent-34.5','tangent-35','backface-reject'):
            self.assertEqual(results[name][0],0,name)
        self.assertEqual(results['tangent-34.499996'][0],1)
        self.assertEqual(results['special-line'][3][0],1)
        self.assertEqual(results['two-sided-flip'][2],[-1.,0.,0.])
        self.assertEqual(results['sphere-no-two-sided-flip'][2],[1.,0.,0.])
        self.assertEqual(results['bisect-zero'][1],[50.,0.,0.])
        self.assertEqual(results['moving-stationary-overlap'][1],[20.,0.,0.])
        # OPA pushes20->35. XLU bisects50->35, producing46.25. An independent
        # XLU query of50->20 produces46.25 too here; distinguish other endpoints
        # explicitly below rather than infer shared-input behavior from one hit.
        self.assertEqual(results['shared-1'][1],[46.25,0.,0.])
        self.assertEqual(results['shared-mutated-endpoint'][1],[45.078125,0.,0.])
        self.assertEqual(results['xlu-original-endpoint'][1],[45.625,0.,0.])

    def test_counter_only_on_executed_obstructions(self):
        g=corpus.golden(self.refs[1])['sequences']
        unchanged=g['unchanged-preserves-counter'][0]
        self.assertEqual(unchanged[0],0);self.assertEqual(unchanged[3][0],2);self.assertEqual(unchanged[4][4],0)
        self.assertEqual(g['miss-resets'][0][3][0],0)
        seq=g['five-qualifying'];self.assertEqual([r[3][0] for r in seq],[1,2,3,4,0])
        self.assertTrue(all(r[0]==1 and r[4][4]==1 for r in seq))
        self.assertEqual(seq[-1][4][7],1)
        self.assertEqual(seq[-1][3][1:],[0.]*6)
        failed=g['five-recovery-fails'][-1]
        self.assertEqual(failed[3][0],0);self.assertEqual(failed[4][5:8],[11,1,0])
        self.assertEqual(failed[3][1:],[1.,2.,3.,4.,5.,6.])
        self.assertEqual(g['real-opa-wall'][0][0],1)
        self.assertEqual(g['real-xlu-wall'][0][0],1)
        push=g['previous-pushout'][0]
        self.assertEqual(push[1],[21.5,0.,0.]);self.assertEqual(push[4][0],2)
        extended=g['line-extension'][0]
        self.assertEqual(extended[4][11:14],[-15.,0.,0.]);self.assertEqual(extended[4][14:17],[35.,0.,0.])

    def test_node32_collision_disabled_and_no_direct_primitive_in_main(self):
        import camera_reference
        _,node=camera_reference.setup()
        self.assertEqual(node[-1],0x75652082);self.assertEqual(node[-1]&1,0)
        self.assertNotIn('bc_contact',(ref.ROOT/'platform/3ds/source/main.c').read_text())

    def test_scratch_sizes_and_atomic_error(self):
        self.assertEqual(C.sizeof(Scratch),8000);self.assertEqual(C.sizeof(corpus.State),28);self.assertEqual(C.sizeof(corpus.Trace),68)
        lib=self.libs[1];models,buffers=self.models(lib,corpus.world('real'))
        bad=('overflow','real',1,(-9000,-500,-8000),(9000,7000,8000),35,3,0)
        self.assertEqual(self.query(lib,models,bad)[0],-1)
        s=corpus.State(2,(F*3)(1,2,3),(F*3)(4,5,6));old=bytes(s)
        r=self.update(lib,models,(float('inf'),0,0),(0,0,0),(0,0,0),s,True)
        self.assertEqual(r[0],-1);self.assertEqual(bytes(s),old)

    def test_occurrences_are_not_deduplicated(self):
        for lib,oracle in zip(self.libs,self.refs):
            models,buffers=self.models(lib,corpus.load(oracle,'duplicates'))
            for case in [c for c in corpus.cases() if c[1]=='duplicates']:
                want=corpus.query(oracle,case);got=self.query(lib,models,case)
                self.assertEqual(corpus.pack_query(got),corpus.pack_query(want))
                self.assertEqual(got[3][:3],[0,2,1])
                # Normal sum is (2,0,1), not the deduplicated (1,0,1).
                self.assertEqual(got[2][0],2*got[2][2])

    def test_active_triangle_capacity_is_explicit_and_atomic(self):
        for lib,oracle in zip(self.libs,self.refs):
            for count in (100,101):
                v,records=corpus.wall();data=[corpus.synthetic(0,v,records*count),corpus.synthetic(1,*corpus.wall(-1000))]
                for role,(raw,_) in enumerate(data):oracle.ref_load(role,C.create_string_buffer(raw))
                models,buffers=self.models(lib,data)
                case=('capacity','synthetic',1,(50,0,0),(20,0,0),35,3,0)
                got=self.query(lib,models,case)
                self.assertEqual(got[0],1 if count==100 else -1)
                # The reference overflow observer excludes undefined original
                # writes; it does NOT define new original-game semantics.
                want=corpus.query(oracle,case)
                if count==100:self.assertEqual(corpus.pack_query(got),corpus.pack_query(want))
                else:self.assertEqual(want[0],-1)
