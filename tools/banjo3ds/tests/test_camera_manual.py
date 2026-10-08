"""Manual camera host composition vs original decomp, with full frame state."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import manual_reference as ref
import manual_corpus as corpus
import camera_reference
import zones_reference
import contact_corpus as contact
import free_b_corpus as free
import test_camera as camera
from test_camera_zones import Data,Selection,production_data
from test_free_b import PostState
from test_camera_contact import Scratch
from test_world_segment import Model
from manual_corpus import snapshot,packed,command,schedules
F=C.c_float
I=C.c_int
class State(C.Structure):
    _fields_=[('camera',camera.State),('zones',Selection),('post',PostState)]+[(n,F) for n in ref.FIELDS[22:32]]+[
      ('viewport_offset',F*3),('viewport_angles',F*3),('viewport_remaining',F),('viewport_duration',F),
      ('viewport_position',F*3),('viewport_rotation',F*3)]+[(n,F) for n in ref.FIELDS[46:52]]+[
      ('focus_mode',C.c_uint),('c_complete',C.c_uint),('viewport_state',C.c_uint),('buttons',C.c_uint)]
class Trace(C.Structure):_fields_=[('free_b',free.Trace),('contact',contact.Trace)]

def values(s,t):
    base=camera.values(s.camera);v=base[:22]+[getattr(s,n) for n in ref.FIELDS[22:32]]
    v+=list(s.viewport_offset)+list(s.viewport_angles)+[s.viewport_remaining,s.viewport_duration]+list(s.viewport_position)+list(s.viewport_rotation)
    v+=[getattr(s,n) for n in ref.FIELDS[46:52]]+[s.post.history]
    ids=base[22:]+[s.zones.group,s.zones.local,s.zones.profile,s.zones.last_zoom,s.focus_mode,s.c_complete,s.viewport_state,s.post.counter,s.buttons]
    return v,ids,contact.trace_values(t.contact)

class ManualCameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='manual-test-');cls.addClassCleanup(cls.tmp.cleanup);cls.libs=[];cls.refs=[]
        base=ref.ROOT/'tools/banjo3ds'
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so')
            sources=('camera_manual/manual.c','camera_manual/contact.c','camera/camera.c','camera_contact/contact.c','camera_contact/free_b.c','camera_zones/zones.c','world_query/segment.c')
            subprocess.run(['cc',*camera.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',*[str(base/p) for p in sources],'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));fp=C.POINTER(F)
            lib.bm_init.argtypes=[C.POINTER(State),C.POINTER(camera.Math),C.POINTER(camera.Input),fp,fp]
            lib.bm_update.argtypes=[C.POINTER(State),C.POINTER(camera.Math),C.POINTER(Data),C.POINTER(camera.Input),C.c_uint,C.c_uint,C.POINTER(Model),C.POINTER(Model),fp,C.POINTER(Scratch),C.POINTER(Trace)]
            lib.bm_update.restype=C.c_bool
            lib.bm_obstruction.argtypes=[C.POINTER(Model),C.POINTER(Model),fp,fp,C.c_uint,C.c_void_p,C.POINTER(Scratch),C.POINTER(contact.Trace)]
            lib.bm_obstruction.restype=C.c_int
            lib.banjo_camera_math_init.argtypes=[C.POINTER(camera.Math)]
            lib.bq_open.argtypes=[C.POINTER(Model),C.c_void_p,C.c_size_t]
            cls.libs.append(lib);cls.refs.append(ref.library(opt))
        cls.data,cls.keep,cls.raw=production_data()
    def run_case(self,lib,original,spec):
        zones_reference.configure(original);data=contact.load(original,spec['world']);models=[Model(),Model()];buffers=[]
        for m,(_,packet) in zip(models,data):
            b=C.create_string_buffer(packet);buffers.append(b);self.assertEqual(lib.bq_open(C.byref(m),b,len(packet)),1)
        first=spec['commands'][0];p=first['player'];eye=spec.get('eye',[p[0],p[1]+375,p[2]-850]);rot=spec.get('rotation',[340,180,0])
        original.manual_init((F*3)(*p),first['floor'],(F*3)(*eye),(F*3)(*rot))
        corpus.initialize(original,spec)
        s=State();m=camera.Math();lib.banjo_camera_math_init(C.byref(m));scratch=Scratch()
        lib.bm_init(C.byref(s),C.byref(m),C.byref(camera.make_input(first)),(F*3)(*eye),(F*3)(*rot));rows=[]
        if spec.get('disable_zones'):C.memset(s.zones.enabled,0,80)
        s.post.history=spec.get('history',0);s.post.counter=spec.get('counter',0)
        for index,c in enumerate(spec['commands']):
            target=c.get('target',[c['player'][0],c['player'][1]+80,c['player'][2]])
            args=[(F*3)(*c['player']),c['floor'],c['yaw'],c['under'],c['dt'],c['vi'],c['stable'],c['buttons'],c['enabled'],(F*3)(*target)]
            self.assertEqual(original.manual_step(*args),1,(spec['name'],index,'original query overflow'))
            t=Trace();self.assertTrue(lib.bm_update(C.byref(s),C.byref(m),C.byref(self.data),C.byref(camera.make_input(c)),c['buttons'],c['enabled'],*[C.byref(v) for v in models],(F*3)(*target),C.byref(scratch),C.byref(t)),(spec['name'],index,'production failure'))
            want=snapshot(original);got=values(s,t)
            differences=[(k,a,b) for k,a,b in zip(ref.FIELDS,got[0],want[0]) if struct.pack('>f',a)!=struct.pack('>f',b)]
            self.assertEqual(packed(got),packed(want),(spec['name'],index,differences,got[1],want[1],got[2],want[2]))
            rows.append(want)
        return rows
    def test_full_frame_parity_O0_O2(self):
        for lib,original in zip(self.libs,self.refs):
            for spec in schedules():self.run_case(lib,original,spec)

    def original_rows(self,name,original=None):
        original=original or self.refs[0];spec=next(s for s in schedules() if s['name']==name)
        corpus.initialize(original,spec)
        return [corpus.step(original,c) for c in spec['commands']]

    def test_R_convergence_release_and_visible_viewport(self):
        for original in self.refs:
            rows=self.original_rows('R-turn-90',original)
            self.assertEqual(rows[0][1][:2],[4,19]);self.assertEqual(rows[24][1][:2],[4,19])
            # Releasing before convergence does not cancel target or snap to B.
            self.assertEqual(rows[25][1][:2],[4,19]);self.assertTrue(all(r[0][23]==270 for r in rows[:26]))
            returning=next(i for i,r in enumerate(rows) if r[1][:2]==[2,19])
            self.assertEqual(rows[returning+1][1][:2],[2,11])
            self.assertLess(abs(rows[returning-1][0][23]-rows[returning-1][0][24]),4)
            self.assertNotEqual(rows[0][0][:6],rows[0][0][40:46])
            end=next(i for i,r in enumerate(rows) if r[1][10]==0)
            self.assertEqual(end,29)
            self.assertTrue(all(r[0][:6]==r[0][40:46] for r in rows[end:]))
            # R alone never queries obstruction unless effective contact changed.
            for r in rows:
                if r[1][1]==19:self.assertEqual(r[2][4],r[2][6])

    def test_C_edges_hold_retarget_and_cooldown(self):
        for original in self.refs:
            for name in ('C-left-hold-release','C-right-hold-release'):
                rows=self.original_rows(name,original)
                self.assertEqual(rows[0][1][:2],[7,10]);self.assertEqual(rows[0][1][10],0)
                end=next(i for i,r in enumerate(rows) if r[1][:2]==[2,10])
                self.assertEqual(rows[end+1][1][:2],[2,11])
                self.assertTrue(all(r[1][1]==11 for r in rows[end+1:]))
                # Active C calls obstruction even with no effective contact.
                self.assertTrue(any(r[2][4]==1 and r[2][6]==0 for r in rows))
            rows=self.original_rows('C-retarget',original)
            self.assertNotEqual(rows[11][0][26],rows[12][0][26])
            self.assertNotEqual(rows[29][0][26],rows[30][0][26])
            rows=self.original_rows('zoom-hold-no-repeat',original)
            self.assertTrue(all(r[1][3]==2 for r in rows[:31]));self.assertTrue(all(r[1][3]==3 for r in rows[31:]))
            # Preset changes now, distance profile application waits one update.
            self.assertEqual(rows[31][0][46],850);self.assertEqual(rows[32][0][46],1100)
            rows=self.original_rows('zoom-cooldown',original)
            self.assertEqual(rows[0][1][3],2);self.assertEqual(rows[31][1][3],3);self.assertEqual(rows[33][1][3],3)
            self.assertEqual(rows[60][1][3],1);self.assertEqual(rows[90][1][3],2)
            rows=self.original_rows('disabled-C-inputs',original)
            self.assertTrue(all(r[1][:2]==[2,11] and r[1][3]==2 for r in rows))

    def test_zones_override_manual_and_final_zoom_update(self):
        for original in self.refs:
            rows=self.original_rows('zone-priority',original)
            self.assertTrue(all(r[1][:4]==[9,17,32,2] for r in rows[:40]))
            self.assertEqual(rows[40][1][:2],[2,17]);self.assertEqual(rows[41][1][:2],[4,19])
            self.assertEqual(rows[120][1][:3],[9,17,32])
            rows=self.original_rows('C-zone-interruption',original)
            self.assertEqual(rows[10][1][:3],[9,17,32]);self.assertEqual(rows[40][1][:2],[2,17])
            self.assertEqual(rows[41][1][:2],[7,10])
            # C init is empty: immediately after zone exit it inherits focus1.
            self.assertEqual(rows[41][1][8],1)
            rows=self.original_rows('jump-stable-zone',original)
            self.assertTrue(all(r[1][2]==32 for r in rows[:40]))
            self.assertEqual(rows[40][1][:2],[2,17])
            rows=self.original_rows('node38-zoom',original)
            self.assertTrue(all(r[1][2]==38 for r in rows))
            self.assertEqual(rows[31][0][46:48],[950,525]);self.assertEqual(rows[32][0][46:48],[1100,675])
            rows=self.original_rows('R-zone-interruption',original)
            # Starting a zoom node does not cancel the running R viewport blend.
            self.assertEqual(rows[10][1][:2],[9,17]);self.assertEqual(rows[10][1][10],2)
            self.assertNotEqual(rows[10][0][:6],rows[10][0][40:46])

    def test_actual_manual_recovery_variants_and_shared_history(self):
        for original in self.refs:
            for button,variant in ((1,0),(2,3),(4,2)):
                rows=self.original_rows('opa-manual-'+str(button),original)
                manual_state=19 if button==1 else 10
                recovering=[(i,r) for i,r in enumerate(rows) if r[1][1]==manual_state and r[2][5]]
                self.assertTrue(recovering,(button,variant))
                i,r=recovering[0];self.assertEqual(rows[i-1][1][11],4);self.assertEqual(r[1][11],0)
                self.assertEqual(r[2][7],1)
                if variant:self.assertEqual(r[2][5],2)
                else:self.assertEqual(r[2][5],1)
                if button!=1:self.assertTrue(all(rows[j][2][4]==1 for j in range(5)))
                # Dedicated B history survives R/C; manually seeded -1 is not
                # overwritten until a qualifying B rollback check actually runs.
                self.assertTrue(all(v[0][52]==-1 for v in rows[:i+1]))
            rows=self.original_rows('C-rejected-20',original)
            self.assertTrue(any(r[2][1]>r[2][0]+r[2][4] for r in rows))

    def test_no_manual_matches_accepted_zone_goldens(self):
        import zones_corpus
        for lib,original in zip(self.libs,self.refs):
            for spec in zones_corpus.schedules()[:6]:
                manual=dict(spec,world='real',commands=[dict(c,buttons=0,enabled=35) for c in spec['commands']])
                rows=self.run_case(lib,original,manual)
                baseline=zones_reference.library('-O0');zones_corpus.initialize(baseline,spec)
                for c,row in zip(spec['commands'],rows):
                    _,old=zones_corpus.snapshot(baseline,c)
                    self.assertEqual(camera.pack(row[0][:22],row[1][:4]),camera.pack(old[0],old[1]))
                    self.assertEqual(struct.pack('>fI',row[0][52],row[1][11]),struct.pack('>fI',old[2],old[3]))

    def test_frozen_original_full_histories(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_manual_golden.json').read_text())
        for opt in ('-O0','-O2'):self.assertEqual(corpus.golden(opt),frozen)

    def test_failed_requests_retain_request_state_and_recovery_failures(self):
        for original in self.refs:
            rows=self.original_rows('C-rejected-1',original)
            self.assertEqual(rows[0][1][:2],[2,11])
            self.assertEqual(rows[0][0][26:31],[135,90,0,401,0])
            # Left failed first; right was tried and failed too. Both targets
            # were written; request-side mutations are NOT rolled back.
            self.assertEqual(rows[0][2][1],3)
            for button in (2,4):
                rows=self.original_rows('C-failed-18-candidates-'+str(button),original)
                failed=[r for r in rows if r[2][5]==18 and not r[2][7]]
                self.assertTrue(failed)
                self.assertTrue(all(r[1][11]==0 for r in failed))

    def test_obstruction_variants_original_success_miss_failure_O0_O2(self):
        for lib,original in zip(self.libs,self.refs):
            data=contact.load(original,'opa');models=[Model(),Model()];buffers=[]
            for m,(_,packet) in zip(models,data):
                b=C.create_string_buffer(packet);buffers.append(b);self.assertEqual(lib.bq_open(C.byref(m),b,len(packet)),1)
            for variant in (0,2,3):
                for target,result,attempts in (([-20,0,0],0,1 if variant==0 else 18),([-400,0,0],1,1),([200,0,0],0,0)):
                    st=contact.State(4,(F*3)(1,2,3),(F*3)(4,5,6));want=contact.State.from_buffer_copy(st)
                    a=(F*3)(50,0,0);b=(F*3)(50,0,0);t=contact.Trace();u=contact.Trace();scratch=Scratch()
                    expected=original.manual_obstruction(variant,a,(F*3)(*target),C.byref(want),C.byref(u))
                    actual=lib.bm_obstruction(*[C.byref(m) for m in models],b,(F*3)(*target),variant,C.byref(st),C.byref(scratch),C.byref(t))
                    self.assertEqual(actual,expected);self.assertEqual(bytes(a),bytes(b));self.assertEqual(bytes(st),bytes(want));self.assertEqual(bytes(t),bytes(u))
                    self.assertEqual(actual,result);self.assertEqual(t.recovery_attempts,attempts);self.assertEqual(st.counter,0)
