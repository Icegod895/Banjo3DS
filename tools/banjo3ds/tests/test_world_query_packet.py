"""Losslessness first; candidate enumeration only, never ray/floor evaluation."""
import hashlib
import json
import random
import struct
import unittest
from pathlib import Path
from tools.banjo3ds import world_query_packet as prod
from tools.banjo3ds.floor_collision import export_collision
import world_query_reference as ref

FIXTURE=Path(__file__).parent/'fixtures/world_query_golden.json'

class WorldQueryPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.refs=[ref.original(a,r) for r,a in enumerate((0x14CF,0x14D0))]
        cls.models=[prod.read_model(ref.ROOT/f'assets/model/{a:04X}.model.bin',r,a)
                    for r,a in enumerate((0x14CF,0x14D0))]

    def test_independent_complete_losslessness_and_frozen_hashes(self):
        golden=json.loads(FIXTURE.read_text())
        for m,r in zip(self.models,self.refs):
            with self.subTest(asset=m.asset):
                self.assertEqual(m.serialize(),r['packet'])
                self.assertEqual(prod.decode(m.serialize()),m)
                self.assertEqual(list(m.vertex_header),r['vh'])
                self.assertEqual(list(m.grid),r['grid'])
                self.assertEqual(list(m.cells),r['cells'])
                self.assertEqual(list(m.records),r['records'])
                self.assertEqual(list(m.vertices),r['xyz'])
                self.assertEqual(m.vertex_block,r['vb'])
                self.assertEqual(m.collision_block,r['cb'])
                self.assertEqual(prod.semantic_stream(m),r['semantic'])
                self.assertEqual(ref.metrics(r),golden[f'{m.asset:04X}'])
                self.assertEqual(len(m.serialize())%4,0)

    def test_every_cell_and_raw_record_occurrence(self):
        for m,r in zip(self.models,self.refs):
            visited=[]
            for cell,(first,count) in enumerate(r['cells']):
                expected=[(m.role,cell,j,r['records'][j]) for j in range(first,first+count)]
                actual=prod.candidates(m,[cell],0)
                self.assertEqual(list(actual),expected)
                visited.extend(j for _,_,j,_ in actual)
            self.assertEqual(visited,list(range(len(r['records']))))

    def test_cell102_preserves_15_before_3_and_edge(self):
        m=self.models[0];unique=list(dict.fromkeys(m.records));first,count=m.cells[102]
        order=[unique.index(r) for r in m.records[first:first+count]]
        self.assertLess(order.index(15),order.index(3))
        self.assertEqual(len(set(unique[15][:3])&set(unique[3][:3])),2)
        self.assertEqual(unique[15][:3],(3325,3326,3324))
        self.assertEqual(unique[3][:3],(3325,3328,3326))

    def test_automatic_duplicate_order_empty_boundary_and_shared_vertices(self):
        for m,expected in zip(self.models,(177,9)):
            ids={r:i for i,r in enumerate(dict.fromkeys(m.records))}
            inversions=0;seen={};duplicate=False;empty=False;edge=False;vertex=False
            for cell,(first,n) in enumerate(m.cells):
                rows=m.records[first:first+n];order=[ids[r] for r in rows]
                inversions+=any(a>b for a,b in zip(order,order[1:]))
                empty |= n==0
                for r in rows:
                    duplicate |= r in seen and seen[r]!=cell
                    seen[r]=cell
                for a,b in zip(rows,rows[1:]):
                    shared=len(set(a[:3])&set(b[:3]));edge |= shared==2;vertex |= shared>=1
            self.assertEqual(inversions,expected)
            self.assertTrue(duplicate and empty and edge and vertex)
            self.assertEqual(prod.selected_cells(m,(-100000,)*3,(-100000,)*3),(0,))
            self.assertEqual(prod.selected_cells(m,(100000,)*3,(100000,)*3),(len(m.cells)-1,))

    def test_grid_selection_and_filtered_candidate_order_independently(self):
        rng=random.Random(1486)
        for m,r in zip(self.models,self.refs):
            scale=m.grid[9]
            cases=[((-scale,)*3,(-scale,)*3),((0,1799,0),(0,1801,0)),((-100000,)*3,(100000,)*3)]
            for _ in range(100):
                lo=tuple(rng.randint(-12000,12000) for _ in range(3))
                cases.append((lo,tuple(x+rng.randint(0,1500) for x in lo)))
            for lo,hi in cases:
                cells=ref.select(r,lo,hi)
                self.assertEqual(list(prod.selected_cells(m,lo,hi)),cells)
                for mask in (0,0x800000,0x400000,0x5e0000,0xf800ff0f):
                    expected=[]
                    if m.role or mask&0x80001f00 != 0x80001f00:
                        for c in cells:
                            first,n=r['cells'][c]
                            for j in range(first,first+n):
                                if not r['records'][j][4]&mask:expected.append((m.role,c,j,r['records'][j]))
                    self.assertEqual(list(prod.candidates(m,cells,mask)),expected)

    def test_reject_corrupt_packet(self):
        p=self.models[0].serialize()
        for bad in (p[:-1],p+b'\0',b'NOPE'+p[4:],p[:6]+b'\0\1'+p[8:]):
            with self.assertRaises(ValueError):prod.decode(bad)
        b=bytearray(p);at=64+len(self.models[0].vertex_block)+24
        struct.pack_into('>hh',b,at,-1,1)
        with self.assertRaises(ValueError):prod.decode(b)

    def test_existing_movement_export_remains_frozen(self):
        paths=[ref.ROOT/f'assets/model/{a:04X}.model.bin' for a in (0x14CF,0x14D0)]
        golden=json.loads(FIXTURE.read_text())
        self.assertEqual(hashlib.sha256(export_collision(paths).encode()).hexdigest(),golden['movement_sha256'])
