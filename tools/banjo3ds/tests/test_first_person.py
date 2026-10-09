"""Host-only first-person parity. Existing camera/renderer never linked/edited."""
import ctypes as C
import hashlib
import itertools
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import first_person_reference as ref
import first_person_corpus as corpus

class FirstPersonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='fp-tests-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[]
        for opt in ('-O0','-O2'):
            path=Path(cls.tmp.name)/(opt+'.so')
            result=subprocess.run(['cc',*ref.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',str(ref.ROOT/'tools/banjo3ds/camera_first_person/first_person.c'),'-lm','-o',str(path)],capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stderr)
            if result.stderr:raise RuntimeError('Unexpected compiler diagnostics: '+result.stderr)
            lib=C.CDLL(str(path));ref.configure(lib,'fp_');cls.libs.append(lib);cls.refs.append(ref.library(opt))
            if cls.refs[-1].compiler_output:raise RuntimeError(cls.refs[-1].compiler_output)

    def test_original_source_fingerprints(self):
        data=json.loads((ref.ROOT/'tools/banjo3ds/tests/fixtures/first_person_golden.json').read_text())
        for path,digest in data['original_sources'].items():
            self.assertEqual(hashlib.sha256((ref.ROOT/path).read_bytes()).hexdigest(),digest,path)

    def test_full_camera_frame_histories_O0_O2(self):
        self.compare_histories(corpus.camera_schedules())
    def test_full_dronelook_frame_histories_O0_O2(self):
        self.compare_histories(corpus.look_schedules())
    def compare_histories(self,specs):
        frozen=json.loads((ref.ROOT/'tools/banjo3ds/tests/fixtures/first_person_golden.json').read_text())['histories']
        for lib,original in zip(self.libs,self.refs):
            for spec in specs:
                p=corpus.Driver(lib,False,spec);r=corpus.Driver(original,True,spec);digest=hashlib.sha256()
                for i,d in enumerate(spec['rows']):
                    actual=p.step(d);expected=r.step(d)
                    self.assertEqual(actual,expected,(spec['name'],i,'first mismatching byte',next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),None)))
                    digest.update(expected)
                self.assertEqual(frozen[spec['name']],{'frames':len(spec['rows']),'sha256':digest.hexdigest()})

    def test_stand_walk_priorities_O0_O2(self):
        for lib,original in zip(self.libs,self.refs):
            cam=ref.Camera()
            for context,zone,buttons,stable in itertools.product((1,31,2,3,4),range(5),range(16),(0,1)):
                v=corpus.make_input(dict(context=context,zone=zone,buttons=buttons,stable_flag=stable,target_speed=500 if zone==4 else 150))
                self.assertEqual(lib.fp_select(C.byref(cam),C.byref(v),buttons),original.ref_select(C.byref(cam),C.byref(v),buttons),(context,zone,buttons,stable))
            for flags in itertools.product((0,1),repeat=4):
                for context in (1,31,2,3,4):
                    v=corpus.make_input(dict(context=context,buttons=7,fall=flags[0],slide=flags[1],can_claw=flags[2],can_roll=flags[3]))
                    self.assertEqual(lib.fp_select(C.byref(cam),C.byref(v),7),original.ref_select(C.byref(cam),C.byref(v),7))
            for state,blocked,ground,vy in itertools.product(range(5),(0,1),(0,1),(-1,0,1)):
                cam.state=state;v=corpus.make_input(dict(map_blocks=blocked,stable_flag=ground,vy=vy))
                self.assertEqual(lib.fp_eligible(C.byref(cam),C.byref(v)),original.ref_eligible(C.byref(cam),C.byref(v)))

    def rows(self,name):
        spec=next(s for s in corpus.camera_schedules()+corpus.look_schedules() if s['name']==name)
        d=corpus.Driver(self.refs[0],True,spec);out=[]
        for f in spec['rows']:
            packed=d.step(f)
            out.append((ref.Camera.from_buffer_copy(d.camera),ref.Look.from_buffer_copy(d.look),d.visible.value,packed))
        return out
    def test_timer_visibility_and_reset_contract(self):
        rows=self.rows('timer-exact')
        self.assertEqual([rows[i][0].state for i in (30,31,63,64,94,95,96)],[1,2,2,3,3,4,4])
        self.assertEqual(rows[31][0].timer,0)
        for suffix,want in [('39.999996185302734',0),('40',1),('40.000003814697266',1)]:
            self.assertEqual(self.rows('visibility-1-'+suffix)[0][2],want)
            self.assertEqual(self.rows('visibility-3-'+suffix)[0][2],want)
        rows=self.rows('reenter-reset-pass')
        self.assertEqual(rows[120][0].state,0)
        self.assertEqual(rows[120][0].timer,rows[119][0].timer)
        self.assertEqual(list(rows[120][0].position),[0,0,0])
    def test_entry_exit_events_and_no_jump_on_exit(self):
        rows=self.rows('look-context1-exit1');cam,look,_,_=rows[0]
        self.assertEqual(list(look.velocity),[0,0,0]);self.assertEqual(look.target_speed,0)
        self.assertEqual((look.animation,look.animation_duration,look.animation_starts),(0x6f,5.5,1))
        self.assertEqual(list(look.update_types),[1,1,3,2])
        self.assertEqual(list(look.events)[:look.event_count],list(range(1,10)))
        cam,look,visible,_=rows[170]
        self.assertEqual((cam.state,look.active,look.flag,look.requested),(3,0,0,1))
        self.assertEqual(look.exits,1);self.assertEqual(visible,0)
        self.assertNotEqual(look.requested,5)
    def test_held_buttons_and_ground_exit_threshold(self):
        for name in ('entry-held-A','entry-held-Cup'):
            self.assertEqual(self.rows(name)[-1][1].exits,0)
        self.assertEqual(self.rows('loss-24')[-1][1].exits,0)
        for name in ('loss-25','loss-26','positive-vy'):
            self.assertEqual(self.rows(name)[90][1].exits,1)
        self.assertEqual(self.rows('fast-zone4')[-1][1].entries,0)
    def test_eye_sampling_prephysics_and_no_underlay_write(self):
        rows=self.rows('look-context1-exit1')
        # Inputs are externally advanced player positions, not an eye bone or
        # camera-after-physics callback. Every active state samples THIS input.
        for i in range(170):self.assertEqual(list(rows[i][0].eye),[ref.F(i*.01).value,1900,0])
        rows=self.rows('never-enter-pass')
        for row in rows:
            floats=struct.unpack_from('>6f',row[3],84)
            self.assertEqual(floats,(10,2105,-845,341,181,0))
    def test_nonlinear_angle_and_interruption_boundaries(self):
        for lib in self.libs:
            c=ref.Camera();p=(ref.F*3)(0,0,100);r=(ref.F*3)(0,0,0)
            lib.fp_state(C.byref(c),1,p,r)
            lib.fp_target(C.byref(c),(ref.F*3)(0,0,0),(ref.F*3)(0,180,0))
            visible=C.c_int32(1);clock=ref.Clock(.25,(ref.F*4)(10,10,120,120),1)
            lib.fp_view(C.byref(c),C.byref(clock),p,r,C.byref(visible))
            self.assertGreater(c.position[2],75) # nested sine ease, not linear
            self.assertEqual(c.rotation[1],0) # ENTER angular delay
            clock.dt=.5
            lib.fp_view(C.byref(c),C.byref(clock),p,r,C.byref(visible))
            self.assertAlmostEqual(c.rotation[1],90,places=4)
            oldp=bytes(c.position);oldr=bytes(c.rotation)
            lib.fp_state(C.byref(c),3,p,r)
            lib.fp_state(C.byref(c),1,(ref.F*3)(999,888,777),(ref.F*3)(20,30,40))
            self.assertEqual(bytes(c.source),oldp);self.assertEqual(bytes(c.source_rotation),oldr)
        plus=self.rows('plus180')[1][0].rotation[1]
        minus=self.rows('minus180')[1][0].rotation[1]
        self.assertGreater(plus,0);self.assertGreater(minus,180) # -180 resolves to +180
        rows=self.rows('pitch-limits')
        self.assertIn(305,[r[0].look[0] for r in rows]);self.assertIn(70,[r[0].look[0] for r in rows])

    def test_inherited_gains_and_vi_are_observable(self):
        a=self.rows('camera-default-vi1')[100][0]
        b=self.rows('camera-apparent-arguments-vi1')[100][0]
        c=self.rows('camera-default-vi2')[100][0]
        self.assertNotEqual(bytes(a.rotation),bytes(b.rotation));self.assertNotEqual(bytes(a.rotation),bytes(c.rotation))

if __name__=='__main__':unittest.main()
