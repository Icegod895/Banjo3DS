"""D.3A: original index provenance, independent of the production mapper."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from tools.banjo3ds.bridge_state import movement_binding as production
from tools.banjo3ds.floor_collision import export_collision, scene_collision
from test_movement import Vertex, Triangle

ROOT = Path(__file__).resolve().parents[3]
OPA = ROOT/'assets/model/14CF.model.bin'
XLU = ROOT/'assets/model/14D0.model.bin'


def source(data):
    """Independent BKModelBin/BKCollisionList/mesh reader; no exporter calls."""
    u16 = lambda at: int.from_bytes(data[at:at+2], 'big')
    s16 = lambda at: int.from_bytes(data[at:at+2], 'big', signed=True)
    u32 = lambda at: int.from_bytes(data[at:at+4], 'big')
    vo, co, mo = u32(16), u32(28), u32(36)
    xyz = [tuple(s16(vo+24+16*i+2*a) for a in range(3)) for i in range(u16(vo+20))]
    cells = [(s16(co+24+4*i), s16(co+26+4*i)) for i in range(s16(co+16))]
    start = co+24+4*len(cells)
    raw = [tuple([s16(start+12*i+2*j) for j in range(4)]+[u32(start+12*i+8)])
           for i in range(s16(co+20))]
    unique = []
    for record in raw:
        if record not in unique:
            unique.append(record)
    used = [i for i in range(len(xyz)) if any(i in r[:3] for r in unique)]
    meshes = {}
    if mo:
        p = mo+2
        for _ in range(s16(mo)):
            mesh, n = s16(p), s16(p+2)
            meshes[mesh] = [s16(p+4+2*i) for i in range(n)]
            p += 4+2*n
    return dict(xyz=xyz, cells=cells, raw=raw, unique=unique, used=used, meshes=meshes)


def reference(opa, xlu):
    """Retain selected identity while simulating exact first-record export order."""
    a, b = source(opa), source(xlu)
    vbase, tbase = len(a['used']), len(a['unique'])
    vertices, triangles, occurrences, meshes = [], [], [], []
    for slot, mesh in enumerate((497, 498, 499)):
        ids = b['meshes'][mesh]
        mapped = [vbase+b['used'].index(i) for i in ids if i in b['used']]
        related = [tbase+j for j,r in enumerate(b['unique']) if any(i in ids for i in r[:3])]
        nocc = sum(any(v in ids for v in b['raw'][j][:3]) for first,n in b['cells'] for j in range(first,first+n))
        meshes.append(dict(mesh=mesh, mesh_slot=slot, source_vertices=ids,
                           movement_vertices=mapped, excluded_source_vertices=[i for i in ids if i not in b['used']],
                           movement_triangles=related, occurrence_count=nocc))
        vertices.extend(dict(source_vertex=i, movement_vertex=vbase+b['used'].index(i), mesh_slot=slot)
                        for i in ids if i in b['used'])
    for index, record in enumerate(b['unique']):
        affected = [m for m in (497,498,499) if any(i in b['meshes'][m] for i in record[:3])]
        if affected:
            triangles.append(dict(movement_triangle=tbase+index, source_unique_triangle=index,
                                  source_vertices=list(record[:3]),
                                  movement_vertices=[vbase+b['used'].index(i) for i in record[:3]],
                                  meshes=affected, surface=record[3], flags=record[4]))
    selected = {r['movement_triangle'] for r in triangles}
    for cell,(first,n) in enumerate(b['cells']):
        for i in range(first,first+n):
            dst = tbase+b['unique'].index(b['raw'][i])
            if dst in selected:
                occurrences.append(dict(cell=cell, raw_record=i, movement_triangle=dst))
    return dict(meshes=meshes, vertices=vertices, triangles=triangles, occurrences=occurrences)


class BridgeMovementBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_opa, cls.raw_xlu = OPA.read_bytes(), XLU.read_bytes()
        cls.info = production.provenance(OPA, XLU)
        cls.oracle = reference(cls.raw_opa, cls.raw_xlu)

    def test_exact_mesh_vertex_triangle_and_occurrence_chain(self):
        for key, expected in self.oracle.items():
            self.assertEqual(self.info[key], expected, key)
        self.assertEqual(self.info['movement_vertex_count'],4537)
        self.assertEqual(self.info['movement_triangle_count'],3145)
        expected = ((497,range(134,138),range(4346,4350),range(3040,3042),4),
                    (498,range(150,166),(),(),0),
                    (499,range(138,150),range(4350,4362),range(3042,3050),16))
        for row,(mesh,src,vertices,tris,n) in zip(self.info['meshes'],expected):
            self.assertEqual((row['mesh'],row['source_vertices'],row['movement_vertices'],row['movement_triangles'],row['occurrence_count']),
                             (mesh,list(src),list(vertices),list(tris),n))
        self.assertEqual(self.info['meshes'][1]['excluded_source_vertices'],list(range(150,166)))
        self.assertEqual(self.info['occurrences'],[
            dict(cell=cell,raw_record=raw,movement_triangle=3040+i)
            for cell,first in ((17,119),(18,153)) for i,raw in enumerate(range(first,first+10))])
        self.assertEqual(len(self.info['triangles']),10)
        # Resolution is by records/indices including winding, surface and flags.
        vertices, triangles = scene_collision((OPA,XLU))
        raw = source(self.raw_xlu)
        # Same XYZ, different source identity and opposite bridge lifecycle:
        # 138 belongs to 499 and collision; 150 belongs to 498 and is absent.
        self.assertEqual(raw['xyz'][138],raw['xyz'][150])
        self.assertIn(138,[r['source_vertex'] for r in self.info['vertices']])
        self.assertNotIn(150,[r['source_vertex'] for r in self.info['vertices']])
        for row in self.info['triangles']:
            actual = triangles[row['movement_triangle']]
            self.assertEqual(actual,tuple(row['movement_vertices'])+(row['surface'],row['flags']))
            for src,dst in zip(row['source_vertices'],row['movement_vertices']):
                self.assertEqual(vertices[dst],raw['xyz'][src])
        for o in self.info['occurrences']:
            row = next(r for r in self.info['triangles'] if r['movement_triangle']==o['movement_triangle'])
            self.assertEqual(raw['raw'][o['raw_record']],tuple(row['source_vertices'])+(row['surface'],row['flags']))

    def test_upstream_export_changes_recalculate_destination_indices(self):
        # Add one used OPA vertex and one unique record by changing a repeated
        # occurrence. All file offsets stay intact. No observed output index is
        # authoritative in production; both XLU bases must move automatically.
        data = bytearray(self.raw_opa);old = source(data)
        unused = next(i for i in range(len(old['xyz'])) if i not in old['used'])
        occurrence = next(i for i,r in enumerate(old['raw']) if old['raw'].count(r)>1)
        co = int.from_bytes(data[28:32],'big');at = co+24+4*len(old['cells'])+12*occurrence
        struct.pack_into('>h',data,at,unused)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'opa.bin';p.write_bytes(data)
            info=production.provenance(p,XLU)
            for key,want in reference(data,self.raw_xlu).items():self.assertEqual(info[key],want)
        self.assertEqual([r['movement_vertex'] for r in info['vertices']],
                         [r['movement_vertex']+1 for r in self.info['vertices']])
        self.assertEqual([r['movement_triangle'] for r in info['triangles']],
                         [r['movement_triangle']+1 for r in self.info['triangles']])

    def test_vertex_identity_permutation_without_changing_geometry(self):
        # Swap raw IDs everywhere, including the mesh lists and vertex bytes.
        # Geometric positions are unchanged. A coordinate-based matcher cannot
        # establish this deliberately changed identity.
        data=bytearray(self.raw_xlu);a,b=138,200
        swap=lambda v: b if v==a else a if v==b else v
        vo,co,mo=(int.from_bytes(data[p:p+4],'big') for p in (16,28,36))
        pa,pb=vo+24+16*a,vo+24+16*b
        data[pa:pa+16],data[pb:pb+16]=data[pb:pb+16],data[pa:pa+16]
        raw=source(self.raw_xlu);at=co+24+4*len(raw['cells'])
        for i,r in enumerate(raw['raw']):struct.pack_into('>3h',data,at+12*i,*map(swap,r[:3]))
        p=mo+2
        for _ in range(int.from_bytes(data[mo:mo+2],'big')):
            n=int.from_bytes(data[p+2:p+4],'big')
            for i in range(n):
                q=p+4+2*i;struct.pack_into('>h',data,q,swap(int.from_bytes(data[q:q+2],'big')))
            p+=4+2*n
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'xlu.bin';p.write_bytes(data)
            info=production.provenance(OPA,p)
            for key,want in reference(self.raw_opa,data).items():self.assertEqual(info[key],want)
        self.assertIn(200,info['meshes'][2]['source_vertices'])
        self.assertNotIn(138,info['meshes'][2]['source_vertices'])

    def test_current_floor_rules_accept_exactly_four_top_triangles_O0_O2(self):
        # Compile unchanged production floor rules; restrict each query to one
        # mapped record. No new slope/flag interpretation in the binding.
        vv,tt=scene_collision((OPA,XLU))
        vertices=(Vertex*len(vv))(*(Vertex(*v) for v in vv));F=C.c_float
        with tempfile.TemporaryDirectory() as d:
            for opt in ('-O0','-O2'):
                so=Path(d)/(opt+'.so')
                subprocess.run(['cc','-std=c99',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                                str(ROOT/'platform/3ds/source/movement.c'),'-lm','-o',str(so)],check=True)
                lib=C.CDLL(str(so));lib.movementFloor.restype=C.c_bool
                lib.movementFloor.argtypes=[C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t,F,F,F,C.POINTER(F)]
                walkable=[]
                for row in self.info['triangles']:
                    t=tt[row['movement_triangle']];center=[sum(vv[i][axis] for i in t[:3])/3 for axis in range(3)]
                    triangle=Triangle(*t);height=F()
                    if lib.movementFloor(vertices,C.byref(triangle),1,center[0],center[2],center[1],C.byref(height)):
                        walkable.append(row['movement_triangle'])
                self.assertEqual(walkable,[3042,3043,3044,3045])

    def test_deterministic_separate_artifacts_and_payload_size(self):
        header=production.export_header(self.info);audit=production.export_audit(self.info)
        self.assertEqual(json.loads(audit),self.info)
        with tempfile.TemporaryDirectory() as d:
            h,j=Path(d)/'binding.h',Path(d)/'binding.json'
            args=[sys.executable,'-B','-m','tools.banjo3ds.bridge_state.movement_binding',str(OPA),str(XLU),str(h),str(j)]
            for _ in range(2):
                subprocess.run(args,cwd=ROOT,check=True)
                self.assertEqual(h.read_bytes(),header.encode());self.assertEqual(j.read_bytes(),audit.encode())
            # The consumer format is only 16 triples of uint16: no padding,
            # no coordinates, no copied collision records or resident hashes.
            c=Path(d)/'size.c';c.write_text('#include "binding.h"\n_Static_assert(sizeof(banjo_bridge_movement_binding)==96,"payload");\nint main(void){return 0;}\n')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(c),'-o',str(Path(d)/'size')],check=True)
        self.assertEqual(len(self.info['vertices']),16)

    def test_existing_collision_export_and_model_header_are_unchanged(self):
        collision=export_collision((OPA,XLU))
        self.assertEqual(hashlib.sha256(collision.encode()).hexdigest(),
                         '0199b14f719357a42ae0ab61d3bfebd4705db9418e79ff8699521130b5e405c7')
        header=(ROOT/'platform/3ds/source/generated_model.h').read_bytes()
        self.assertIn(collision.encode(),header)
        self.assertEqual(hashlib.sha256(header).hexdigest(),
                         '4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c')


if __name__=='__main__':unittest.main()
