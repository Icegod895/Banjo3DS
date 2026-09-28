"""Golden values from the independent original-semantics fallback reference.

These tests do not import the production decoder/exporter. The geometry is
canonical 034D near/reset selection, not a claim about Banjo's animated idle.
"""
from collections import Counter
from pathlib import Path
import unittest

from banjo_pose_reference import CALLS, IDENTITY, canonical_reference, translation


@unittest.skipUnless((Path(__file__).resolve().parents[3] /
                     'assets/model/034D.model.bin').exists(), '034D asset unavailable')
class BanjoPoseReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = canonical_reference()

    def test_canonical_fallback_triangle_stream(self):
        r = self.reference
        summary = r.summary()
        self.assertEqual(r.calls, CALLS)
        self.assertEqual(len(set(r.calls)), 49)
        self.assertEqual(summary['triangles'], 695)
        self.assertEqual(summary['loads'], 723)
        self.assertEqual(summary['used_loads'], 723)
        self.assertEqual(summary['bounds'], [(-74, 74), (34, 122), (-24, 56)])
        # 695 triangles * 3 corners * XYZ big-endian float32; no padding,
        # indices, UVs or colors. Model-space positions, traversal order.
        self.assertEqual(summary['triangle_xyz_be_f32_sha256'],
                         '8f6830d0a108f9e013276b2e3609ba65d0039fb542179f86581e5bf0eec36532')
        self.assertEqual(len(r.records), 60)
        self.assertEqual(r.bones, [IDENTITY] * 60)
        for entry in r.loads:
            self.assertEqual(entry['xyz'], entry['raw'])
            self.assertEqual(entry['view_xyz'],
                             (entry['raw'][0], entry['raw'][1], entry['raw'][2]-100))

    def test_distributed_golden_samples(self):
        samples = {0: (33,42,-11), 120: (-39,60,15), 240: (65,73,6),
                   360: (-38,81,-9), 420: (0,91,39), 627: (4,114,23),
                   834: (12,87,15), 894: (12,87,-23), 1014: (5,87,-10)}
        by_vertex = {entry['vertex']: entry['xyz'] for entry in self.reference.loads}
        self.assertEqual({v: by_vertex[v] for v in samples}, samples)

    def test_stack_balance_and_zero_triangle_lists(self):
        r = self.reference
        self.assertEqual(r.cpu, [translation(0,0,-100)])
        self.assertEqual(r.rsp, [IDENTITY])
        self.assertEqual(Counter(e['action'] for e in r.events),
                         {'rsp_push_load':34, 'rsp_pop':34,
                          'refpoint_cpu_push':7, 'refpoint_cpu_pop':7})
        # Integer locations below geo root are the asset's own G_POPMTX.
        asset_pops = [e for e in r.events if e['action'] == 'rsp_pop'
                      and isinstance(e['location'], int) and e['location'] < 0x16E98]
        self.assertEqual(len(asset_pops), 15)
        self.assertEqual(r.summary()['max_rsp_depth'], 8)
        self.assertEqual(r.summary()['max_cpu_depth'], 8)
        empty = [c for c in r.call_ranges if c['triangles'][0] == c['triangles'][1]]
        self.assertEqual([c['gfx'] for c in empty],
                         [39,72,119,200,233,280,404,439,466,507,542,569,585,657,1349])
        self.assertTrue(all(c['loads'][1] > c['loads'][0] for c in empty))
        self.assertEqual(r.summary()['final_cache'],
                         list(range(999,1017)) + [998] + list(range(969,976)) +
                         [946,947,948,949,888,889])

    def test_skinning_transforms_at_load_and_keeps_parent_cache_entries(self):
        # Artificial matrices isolate semantics; this is not an animation pose.
        r = canonical_reference(bone_overrides={7: translation(0,20,0),
                                                9: translation(10,0,0)})
        parent = [e for e in r.loads if e['command'] == 46]
        child = [e for e in r.loads if e['command'] == 48]
        self.assertEqual([e['slot'] for e in parent], [0,1,2,3])
        self.assertEqual([e['slot'] for e in child], [28,29,30,31])
        for e in parent:
            self.assertEqual(e['xyz'], (e['raw'][0], e['raw'][1]+20, e['raw'][2]))
        for e in child:
            # BONE uses base * absolute bone matrix, not parent * bone.
            self.assertEqual(e['xyz'], (e['raw'][0]+10, e['raw'][1], e['raw'][2]))
        self.assertEqual(r.triangles[30], (30,31,37))
        self.assertEqual([r.loads[i]['xyz'] for i in r.triangles[30]],
                         [(29,71,-8), (29,72,3), (43,55,7)])
        self.assertNotEqual(r.summary()['triangle_xyz_be_f32_sha256'],
                            self.reference.summary()['triangle_xyz_be_f32_sha256'])

    def test_refpoints_do_not_change_rsp_or_geometry(self):
        r = self.reference
        self.assertEqual([ref[1:3] for ref in r.refs],
                         [(8,9),(7,15),(6,23),(1,17),(5,29),(9,31),(2,3)])
        self.assertEqual(r.refs[0][3], (50.5,47,-5.5))
        events = [e for e in r.events if e['action'].startswith('refpoint')]
        for push, pop in zip(events[::2], events[1::2]):
            self.assertEqual(push['rsp_matrix'], pop['rsp_matrix'])
            self.assertEqual(push['rsp_depth'], pop['rsp_depth'])
            self.assertEqual(push['cpu_depth'], pop['cpu_depth']+1)


if __name__ == '__main__':
    unittest.main()
