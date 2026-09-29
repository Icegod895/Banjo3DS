"""Frozen M4.5 original-semantics oracle, independent of production."""
import json
from pathlib import Path
import unittest
from gait_reference import ClipReference, GaitTransition, golden, CLIPS, CASES, PRESERVE, F
from transition_reference import pack

FIXTURE=Path(__file__).parent/'fixtures/gait_golden.json'

class GaitReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected=json.loads(FIXTURE.read_text())

    def test_frozen_four_stream_goldens(self):
        for optimization in ('-O0','-O2'):
            self.assertEqual(json.loads(json.dumps(golden(optimization))),self.expected)

    def test_new_clip_endpoints_are_exact_and_required_phases_present(self):
        for name in ('0002','000C'):
            animation=ClipReference(name)
            self.assertEqual(pack(animation.transforms(0)[0],10),pack(animation.transforms(1)[0],10))
            rows=self.expected['poses'][name]
            self.assertEqual([r['phase'] for r in rows],[0.,2**-20,.25,.5,.75,1-2**-20,1-2**-24,1.])
            for key in ('bones','matrices','loads','corners'):
                self.assertEqual(rows[0][key],rows[-1][key])
        self.assertEqual(self.expected['counts'],dict(calls=49,triangles=695,loads=723,corners=2085))

    def test_original_asymmetric_phase_rules_and_advancing_endpoints(self):
        for old,new in CASES:
            source=ClipReference(CLIPS[old]).transforms(.37)[0]
            t=GaitTransition(source,old,new,.37)
            self.assertEqual(t.phase,F(.37).value if (old,new) in PRESERVE else 0.)
            self.assertEqual(pack(t.sample()[0],10),pack(source,10))
            previous=t.phase
            for _ in range(8):mixed,row=t.step(.025)
            self.assertGreater(t.phase,previous)
            self.assertEqual(t.factor,1.)
            self.assertEqual(pack(mixed,10),pack(t.animation.transforms(t.phase)[0],10))

    def test_interruption_freezes_current_mixed_values_and_preserves_destination_phase(self):
        source=ClipReference('0002').transforms(.37)[0]
        first=GaitTransition(source,'CREEP','SLOW',.37)
        for _ in range(3):mixed,at=first.step(.025)
        second=GaitTransition(mixed,'SLOW','WALK',first.phase)
        self.assertEqual(second.phase,first.phase)
        self.assertNotEqual(pack(mixed,10),pack(source,10))
        self.assertEqual(pack(second.sample()[0],10),pack(mixed,10))
        source_bytes=pack(second.source,10)
        for _ in range(8):second.step(.025)
        self.assertEqual(pack(second.source,10),source_bytes)

if __name__=='__main__':unittest.main()
