"""Frozen original-semantics transition goldens, independent of production."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from transition_reference import (F, IdleAnimation, WalkAnimation, Transition,
                                  blend_pose, raw_blend, scenarios, pose_summary, pack, digest, blend_library, ROOT)

FIXTURE=Path(__file__).parent/'fixtures/transition_006f_0003_golden.json'
IDENTITY=(0.,0.,0.,1.,1.,1.,1.,0.,0.,0.)

class TransitionReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden=json.loads(FIXTURE.read_text())
        cls.actual=scenarios()

    def test_all_four_hash_streams_match_frozen_reference(self):
        self.assertEqual(json.loads(json.dumps(self.actual)),self.golden['scenarios'])
        self.assertEqual(json.loads(json.dumps(scenarios('-O2'))),self.golden['scenarios'])

    def test_destination_advances_and_endpoints_are_exact(self):
        for source_clip,phase,destination in ((IdleAnimation,.37,'0003'),(WalkAnimation,.625,'006F')):
            with self.subTest(destination=destination):
                source,_=source_clip().transforms(phase)
                t=Transition(source,destination)
                current,record=t.sample()
                self.assertEqual(pack(current,10),pack(source,10))
                raw,_=raw_blend(source,t.animation.transforms(0)[0],0)
                self.assertEqual(pack(raw,10),pack(source,10))
                previous=0
                for i in range(8):
                    current,record=t.step(.025)
                    self.assertGreater(t.phase,previous);previous=t.phase
                    self.assertEqual(t.factor,(i+1)/8)
                    self.assertEqual(record['source_hash'],digest(source,10))
                target,_=t.animation.transforms(t.phase)
                self.assertEqual(pack(current,10),pack(target,10))
                self.assertEqual(pose_summary(current),pose_summary(target))
                start_target,_=t.animation.transforms(0)
                self.assertNotEqual(pack(current,10),pack(start_target,10))
                self.assertAlmostEqual(t.phase,.2/t.duration,places=6)
                # Factor remains 1 while destination continues after transition.
                next_pose,_=t.step(.025)
                self.assertEqual(t.factor,1)
                self.assertEqual(pack(next_pose,10),pack(t.animation.transforms(t.phase)[0],10))

    def test_interruption_freezes_mixed_values_not_old_clip(self):
        source,_=IdleAnimation().transforms(.37)
        first=Transition(source,'0003')
        for _ in range(3):mixed,record=first.step(.025)
        self.assertEqual(first.factor,.375)
        self.assertNotEqual(pack(mixed,10),pack(source,10))
        copied=[list(b) for b in mixed]
        second=Transition(copied,'006F')
        copied[1][7]+=12345 # Caller mutation cannot alter frozen state.
        self.assertEqual(pack(second.sample()[0],10),pack(mixed,10))
        # No further evaluation of the old destination/source animation object.
        with patch.object(first.animation,'transforms',side_effect=AssertionError('old clip evaluated')):
            for _ in range(8):
                result,row=second.step(.025)
                self.assertEqual(row['source_hash'],digest(mixed,10))
        self.assertEqual(pack(result,10),pack(second.animation.transforms(second.phase)[0],10))
        self.assertEqual(self.actual['interruption']['return_to_idle'][0]['bones'],record['bones'])

    def test_identical_quaternion_copy_and_linear_scale_translation(self):
        source=[IDENTITY]*109
        destination=[(0.,0.,0.,1.,3.,5.,7.,10.,20.,30.)]*109
        out,stats=raw_blend(source,destination,.25)
        self.assertEqual(stats,(-1,0))
        self.assertEqual(out[0],(0.,0.,0.,1.,1.5,2.,2.5,2.5,5.,7.5))

    def test_shortest_path_and_near_equal_fallback_without_normalization(self):
        source=[IDENTITY]*109
        # Small, deliberately non-unit quaternion verifies no implicit normalize.
        q=(F(.0001).value,0.,0.,F(1.000001).value)
        positive=[q+IDENTITY[4:]]*109
        negative=[tuple(-v for v in q)+IDENTITY[4:]]*109
        a,stats=raw_blend(source,positive,.5)
        b,negstats=raw_blend(source,negative,.5)
        self.assertEqual(stats,(-1,0));self.assertEqual(negstats,(-1,0))
        self.assertEqual(a,b)
        self.assertEqual(a[0][:4],(F(q[0]*.5).value,0.,0.,F(.5+F(q[3]*.5).value).value))
        self.assertNotEqual(sum(v*v for v in a[0][:4]),1.)

    def test_slerp_uses_original_lookup_including_original_zero_dot_quirk(self):
        source=[IDENTITY]*109
        q=(F(math.sin(.5)).value,0.,0.,F(math.cos(.5)).value)
        destination=[q+IDENTITY[4:]]*109
        out,stats=raw_blend(source,destination,.5)
        self.assertGreater(stats[1],0);self.assertLess(stats[0],90)
        # Spherical interpolation is observably different from component lerp.
        self.assertNotEqual(out[0][0],F(q[0]*.5).value)
        # Original memory index 90 is zero, and upperIdx==90 returns zero
        # degrees. Preserve that quirk: dot=0 falls back to component lerp.
        out,stats=raw_blend(source,[(1.,0.,0.,0.)+IDENTITY[4:]]*109,.5)
        self.assertEqual(stats[0],90)
        self.assertEqual(out[0][:4],(.5,0.,0.,.5))
        probe=(C.c_int*2)()
        self.assertEqual(blend_library().lookup_probe(0,probe),0)
        self.assertEqual(probe[0],90)

    def test_lookup_tail_proven_by_original_rom_when_available(self):
        rom=ROOT/'decompressed.us.v10.z64'
        if not rom.exists():self.skipTest('Original decompressed ROM not available')
        data=rom.read_bytes()
        evidence=self.golden['lookup_evidence']
        self.assertEqual(hashlib.sha256(data).hexdigest(),evidence['rom_sha256'])
        table=data[0xf524ec:0xf524ec+368]
        self.assertEqual(hashlib.sha256(table).hexdigest(),evidence['table92_sha256'])
        self.assertEqual(table[360:],bytes(8))
        text=(ROOT/'src/core1/ml.c').read_text()
        literals=text.split('f32 sLookupTableAcosDegrees[90] = {',1)[1].split('};',1)[0]
        declared=pack(((float(v),) for v in literals.split(',') if v.strip()),1)
        self.assertEqual(table[:360],declared)

    def test_real_asset_transition_uses_verified_tail(self):
        rows=self.actual['idle_tail_to_walk']
        self.assertTrue(any(r['lookup_max']==90 for r in rows))
        self.assertTrue(all(r['lookup_max']<92 for r in rows))

    def test_factor_one_bypasses_raw_interpolation_rounding(self):
        source,_=IdleAnimation().transforms(.37)
        destination,_=WalkAnimation().transforms(F(1/3).value)
        raw,_=raw_blend(source,destination,1)
        self.assertNotEqual(pack(raw,10),pack(destination,10))
        endpoint,_=blend_pose(source,destination,1)
        self.assertEqual(pack(endpoint,10),pack(destination,10))

    def test_transition_time_and_destination_loop_are_separate(self):
        source,_=IdleAnimation().transforms(0)
        t=Transition(source,'0003');t.phase=F(.99).value
        t.step(.025)
        self.assertLess(t.phase,.1)
        self.assertEqual(t.factor,.125)
        with self.assertRaises(ValueError):blend_pose(source,source,1.01)

if __name__=='__main__':unittest.main()
