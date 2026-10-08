"""Complete free-B phase composition against unmodified original math/queries."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import free_b_reference as reference
import free_b_corpus as corpus
import contact_corpus as contact
import test_camera as camera
from test_camera_contact import Scratch
from test_world_segment import Model

F=C.c_float
class PostState(C.Structure):
    _fields_=[('counter',C.c_uint32),('history',F)]
class Phase(C.Structure):
    _fields_=[('next',camera.State),('previous',F*3),('desired',F*3),('ag',F),('ar',F),('distance',F)]

class FreeBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='free-b-test-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[]
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so');base=reference.ROOT/'tools/banjo3ds'
            subprocess.run(['cc',*reference.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *[str(base/p) for p in ('camera/camera.c','camera_contact/contact.c','camera_contact/free_b.c','world_query/segment.c')],'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));fp=C.POINTER(F);cp=C.POINTER(camera.State);mp=C.POINTER(camera.Math);ip=C.POINTER(camera.Input)
            args=[C.POINTER(camera.Zoom),C.POINTER(camera.Trigger),C.c_size_t,ip]
            lib.banjo_camera_math_init.argtypes=[mp]
            lib.banjo_camera_init.argtypes=[cp,mp,ip,fp,fp]
            lib.banjo_camera_prepare.argtypes=[C.POINTER(Phase),cp,mp,*args];lib.banjo_camera_prepare.restype=C.c_bool
            lib.bq_open.argtypes=[C.POINTER(Model),C.c_void_p,C.c_size_t]
            lib.bc_free_b_update.argtypes=[cp,C.POINTER(PostState),mp,*args,C.POINTER(Model),C.POINTER(Model),fp,C.POINTER(Scratch),C.POINTER(corpus.Trace)]
            lib.bc_free_b_update.restype=C.c_bool
            lib.bc_free_b_rollback.argtypes=[fp,fp,fp,fp,fp];lib.bc_free_b_rollback.restype=C.c_bool
            cls.libs.append(lib);cls.refs.append(reference.library(opt))
        data=camera.reader.read_spiral_camera(camera.ASSET);z=data['zoom']
        cls.zoom=camera.Zoom((F*3)(*z[:3]),(F*3)(*z[3:6]),(F*2)(*z[6:8]),(F*2)(*z[8:10]),*z[10:])
        cls.triggers=(camera.Trigger*len(data['triggers']))(*[camera.Trigger((C.c_int*3)(*t['position']),t['radius'],t['node'],t['mask']) for t in data['triggers']])

    def initialize(self,lib,ref,schedule):
        corpus.initialize(ref,schedule);s=camera.State();m=camera.Math();lib.banjo_camera_math_init(C.byref(m))
        i=camera.make_input(corpus.command(schedule['player']))
        lib.banjo_camera_init(C.byref(s),C.byref(m),C.byref(i),(F*3)(*schedule['eye']),(F*3)(*schedule['rotation']))
        if 'orbit' in schedule:s.orbit_yaw=schedule['orbit']
        s.position_step[:]=schedule.get('position_step',[0]*3);s.angular_step[:]=schedule.get('angular_step',[0]*3)
        data=contact.world(schedule['world']);buffers=[C.create_string_buffer(p) for _,p in data];models=[Model(),Model()]
        for model,b in zip(models,buffers):self.assertEqual(lib.bq_open(C.byref(model),b,len(b)-1),1)
        return s,m,PostState(schedule.get('counter',0),schedule.get('history',0)),models,buffers

    def test_complete_original_composition_bit_exact(self):
        for lib,ref in zip(self.libs,self.refs):
            for schedule in corpus.schedules():
                s,m,post,models,buffers=self.initialize(lib,ref,schedule)
                for frame,c in enumerate(schedule['commands'],1):
                    want=corpus.step(ref,c);t=corpus.Trace();s.preset=c['preset']
                    ok=lib.bc_free_b_update(C.byref(s),C.byref(post),C.byref(m),C.byref(self.zoom),self.triggers,
                        len(self.triggers) if schedule['zones'] else 0,C.byref(camera.make_input(c)),
                        *[C.byref(v) for v in models],(F*3)(*c['target']),C.byref(Scratch()),C.byref(t))
                    self.assertTrue(ok,(schedule['name'],frame))
                    v=camera.values(s);got=(v[:22],v[22:],post.history,post.counter,t)
                    self.assertEqual(corpus.packed(*got),corpus.packed(*want),
                        (schedule['name'],frame,'camera',v,want[:4],'trace',corpus.trace_values(t),corpus.trace_values(want[4])))
                    self.assertEqual(C.c_int.in_dll(ref,'viewport_noop').value,1)
                    if t.contact.recovered:
                        self.assertEqual(bytes(s.rotation),bytes(t.look))
                        self.assertEqual(list(s.position_step),[0]*3)
                        self.assertEqual(list(s.angular_step),[0]*3)

    def test_rollback_zero_history_and_b_init(self):
        for lib,ref in zip(self.libs,self.refs):
            for previous,desired,corrected,history in (
                ((0,0,0),(10,0,0),(-1,0,0),0),((0,0,0),(10,0,0),(1,0,0),-1),
                ((0,0,0),(10,0,0),(1,0,0),1),((0,0,0),(0,0,0),(1,0,0),0),
                ((0,0,0),(10,0,0),(0,0,0),-1),((0,0,0),(10,0,0),(0,1,0),0),
                ((0,0,0),(10,0,0),(0,1,0),-1),((5,6,7),(5,6,7),(5,6,7),-0.0)):
                p=(F*3)(*previous);d=(F*3)(*desired);a=(F*3)(*corrected);b=(F*3)(*corrected)
                h=F(history);rh=F(history);q=F();rq=F();rolled=C.c_int()
                r=lib.bc_free_b_rollback(C.byref(h),p,d,a,C.byref(q))
                ref.composition_rollback(p,d,b,C.byref(rh),C.byref(rq),C.byref(rolled))
                self.assertEqual((bytes(a),bytes(h),bytes(q),r),(bytes(b),bytes(rh),bytes(rq),bool(rolled.value)))
            # Actual original B-init between checks, retaining its static dot.
            history=F(0);rh=F(0);p=(F*3)(0,0,0);d=(F*3)(10,0,0)
            for i,x in enumerate((-1,1,1)):
                if i==1:
                    ref.ncDynamicCamB_init()
                    self.assertEqual(F.in_dll(ref,'original_rollback_history').value,-1)
                a=(F*3)(x,0,0);b=(F*3)(x,0,0);q=F();rq=F();r=C.c_int()
                lib.bc_free_b_rollback(C.byref(history),p,d,a,C.byref(q))
                ref.composition_rollback(p,d,b,C.byref(rh),C.byref(rq),C.byref(r))
                self.assertEqual(list(a),[0,0,0] if i<2 else [1,0,0]);self.assertEqual(bytes(a),bytes(b))

    def test_complete_pipeline_branch_coverage(self):
        ref=self.refs[1];seen=dict(negative=0,historical=0,positive=0,recovered=0,failed=0,miss_reset=0,pushout=0)
        for schedule in corpus.schedules():
            corpus.initialize(ref,schedule);previous_counter=schedule.get('counter',0);previous_dot=schedule.get('history',0)
            frames=[]
            for c in schedule['commands']:
                v,ids,h,count,t=corpus.step(ref,c);frames.append((count,t.contact.changed,t.contact.obstruction_calls))
                if t.rollback_executed:
                    self.assertEqual(bool(t.rolled_back),t.dot<0 or previous_dot<0)
                    self.assertEqual(h,t.dot)
                    if t.rolled_back:self.assertEqual(bytes(t.final_position),bytes(t.previous))
                    seen['negative']+=t.dot<0;seen['historical']+=t.rolled_back and t.dot>=0
                    seen['positive']+=not t.rolled_back and t.dot>0
                else:self.assertEqual(h,previous_dot)
                if not t.contact.changed:
                    self.assertEqual(t.contact.obstruction_calls,0);self.assertEqual(count,previous_counter)
                seen['recovered']+=t.contact.recovered
                seen['failed']+=t.contact.recovery_attempts==11 and not t.contact.recovered
                seen['miss_reset']+=t.contact.obstruction_calls==1 and previous_counter>0 and count==0 and t.contact.recovery_attempts==0
                seen['pushout']+=t.free_b and bytes(t.previous)!=bytes(t.contact.pushed_previous)
                previous_dot=h;previous_counter=count
            if schedule['name'] in ('opa-approach-slide-leave','xlu-approach-slide-leave','failed-recovery'):
                self.assertTrue(any([n for n,_,_ in frames[i:i+5]]==[1,2,3,4,0] and all(ch and ob for _,ch,ob in frames[i:i+5]) for i in range(len(frames)-4)))
                # Recovery is followed by ordinary no-effective-change frames;
                # the return leg may encounter the same wall again later.
                self.assertTrue(any(not any(ch for _,ch,_ in frames[i:i+10]) for i in range(100,len(frames)-9)))
            if schedule['name']=='negative-history-across-node32-B':
                self.assertEqual(h,-1);self.assertEqual(ids[1],11)
        self.assertTrue(all(seen.values()),seen)

    def test_phase_boundary_preserves_desired_previous_and_rotation(self):
        for lib,ref in zip(self.libs,self.refs):
            schedule=next(s for s in corpus.schedules() if s['name']=='opa-approach-slide-leave')
            s,m,post,models,buffers=self.initialize(lib,ref,schedule);old=bytes(s);phase=Phase()
            c=schedule['commands'][20]
            self.assertTrue(lib.banjo_camera_prepare(C.byref(phase),C.byref(s),C.byref(m),C.byref(self.zoom),self.triggers,0,C.byref(camera.make_input(c))))
            self.assertEqual(bytes(s),old);self.assertEqual(bytes(phase.previous),bytes(s.position))
            self.assertEqual(bytes(phase.next.rotation),bytes(s.rotation))
            self.assertEqual(bytes(phase.next.angular_step),bytes(s.angular_step))
            self.assertNotEqual(bytes(phase.next.position),bytes(phase.desired))
            self.assertNotEqual(bytes(phase.next.position_step),bytes(s.position_step))

    def test_costs_atomic_rejection_and_single_runtime_boundary(self):
        self.assertEqual(C.sizeof(PostState),8);self.assertEqual(C.sizeof(Phase),140)
        self.assertEqual(C.sizeof(corpus.Trace),156);self.assertEqual(C.sizeof(camera.State),104)
        lib=self.libs[1];ref=self.refs[1];schedule=corpus.schedules()[0]
        s,m,post,models,buffers=self.initialize(lib,ref,schedule);trace=corpus.Trace()
        before=(bytes(s),bytes(post),bytes(trace));cmd=dict(schedule['commands'][0],dt=.051)
        self.assertFalse(lib.bc_free_b_update(C.byref(s),C.byref(post),C.byref(m),C.byref(self.zoom),self.triggers,len(self.triggers),C.byref(camera.make_input(cmd)),*[C.byref(x) for x in models],(F*3)(*cmd['target']),C.byref(Scratch()),C.byref(trace)))
        self.assertEqual(before,(bytes(s),bytes(post),bytes(trace)))
        self.assertNotIn('bc_free_b_', (reference.ROOT/'platform/3ds/source/main.c').read_text())
        self.assertEqual((reference.ROOT/'platform/3ds/source/camera_runtime.c').read_text().count('bm_update('),1)

    def test_frozen_original_schedules(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/free_b_golden.json').read_text())
        for ref in self.refs:self.assertEqual(corpus.golden(ref),frozen)

if __name__=='__main__':unittest.main()
