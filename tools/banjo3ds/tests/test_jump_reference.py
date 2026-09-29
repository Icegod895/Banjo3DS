"""Independent original-semantics jump goldens, no production evaluator."""
import json
from pathlib import Path
import unittest
from jump_reference import JumpReference, JumpTransition, animation, golden, PHASES, f
from transition_reference import pack

class JumpReferenceTests(unittest.TestCase):
    def test_frozen_goldens_O0_O2(self):
        expected=json.loads((Path(__file__).parent/'fixtures/jump_golden.json').read_text())
        for opt in ('-O0','-O2'):
            self.assertEqual(json.loads(json.dumps(golden(opt))),expected)
        self.assertEqual([r['phase'] for r in expected['poses']],[f(p) for p in PHASES])
        self.assertEqual(expected['counts'],dict(calls=49,triangles=695,loads=723,corners=2085))

    def test_once_endpoint_is_not_locomotion_wrap(self):
        a=JumpReference()
        self.assertNotEqual(pack(a.transforms(0)[0],10),pack(a.transforms(1)[0],10))
        t=JumpTransition(animation('006F').transforms(.37)[0],'0008')
        for _ in range(100):t.advance(.05)
        self.assertEqual((t.phase,t.segment,t.duration),(f(.6667),2,4))
        self.assertEqual(pack(t.sample()[0],10),pack(a.transforms(f(.6667))[0],10))

    def test_frozen_endpoints_advancing_destination_and_interruption(self):
        source=animation('0003').transforms(.625)[0]
        t=JumpTransition(source,'0008')
        self.assertEqual(pack(t.sample()[0],10),pack(source,10))
        frozen=pack(t.source,10)
        for _ in range(3):mixed,_=t.step(.025)
        self.assertGreater(t.phase,f(.3));self.assertLess(t.factor,1)
        second=JumpTransition(mixed,'006F',5.5)
        self.assertEqual(pack(second.sample()[0],10),pack(mixed,10))
        for _ in range(8):last,_=second.step(.025)
        self.assertEqual(pack(second.source,10),pack(mixed,10))
        self.assertEqual(pack(last,10),pack(animation('006F').transforms(second.phase)[0],10))
        for _ in range(5):last,_=t.step(.025)
        self.assertEqual(pack(t.source,10),frozen)
        self.assertEqual(pack(last,10),pack(JumpReference().transforms(t.phase)[0],10))
