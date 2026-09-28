"""Production static idle versus the independent original-C M3.5 oracle."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from tools.banjo3ds.static_idle import IdleChannels, decode_static_idle
from tools.banjo3ds.n64_displaylist_decoder import BKModel
from tools.banjo3ds.export_3ds_model import (
    export_models, build_draw_batches, export_header, export_scene, STATIC_BANJO_TRANSLATION,
)
from idle_animation_reference import idle_reference

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT/'assets/model/034D.model.bin'
ANIMATION = ROOT/'assets/anim/006F.anim.bin'
BONE_HASH = '2cf3dfb9c5ebe3517ed63cda2f7b445a0cc60840870be668d16ca7c90c35b87b'
GEOMETRY_HASH = '7536cd507d67f2de4e3ab1bec2beb707fd902b361995b8c6ce5d208e16e2cc6c'
MAP_HASH = 'fbcf9cf77aba9779db18049990204c921d0012de83c2312d36b288ec5f087057'


@unittest.skipUnless(MODEL.exists() and ANIMATION.exists(), '034D/006F assets unavailable')
class TestProductionStaticIdle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = decode_static_idle(BKModel(MODEL), ANIMATION)
        cls.animation, cls.bones, _, cls.reference = idle_reference()

    def test_all_transforms_and_matrices_match_original_reference(self):
        transforms = self.data.pose.transforms
        self.assertEqual(transforms, self.bones)
        packed = b''.join(struct.pack('>10f', *bone) for bone in transforms)
        self.assertEqual(len(packed), 109*40)
        self.assertEqual(hashlib.sha256(packed).hexdigest(), BONE_HASH)
        self.assertEqual(self.data.pose.bones, list(self.animation.matrices(self.bones).values()))

    def test_complete_posed_triangle_stream_and_cache_contract(self):
        data, ref = self.data, self.reference
        positions = [(data.vertices[i].x, data.vertices[i].y, data.vertices[i].z)
                     for t in data.triangles for i in (t.v0, t.v1, t.v2)]
        self.assertEqual(positions, [ref.loads[i]['xyz'] for t in ref.triangles for i in t])
        self.assertEqual(hashlib.sha256(b''.join(struct.pack('>3f', *p)
                                                for p in positions)).hexdigest(), GEOMETRY_HASH)
        self.assertEqual(data.pose.loads, [(e['command'], e['slot'], e['vertex'], e['xyz'])
                                          for e in ref.loads])
        self.assertEqual(data.pose.calls, ref.calls)
        self.assertEqual((len(data.pose.calls), len(data.triangles), len(data.vertices)), (49,695,723))
        self.assertEqual(len({i for t in data.triangles for i in (t.v0,t.v1,t.v2)}),723)
        self.assertEqual(data.pose.invalid_references,0)
        self.assertEqual(data.pose.pops,15)
        self.assertEqual((len(data.pose.cpu),len(data.pose.rsp)),(1,1))
        self.assertEqual([(min(p[a] for p in positions),max(p[a] for p in positions))
                          for a in range(3)],ref.summary()['bounds'])
        self.assertEqual((len(data.textures),len(data.materials),len(build_draw_batches(data.triangles))),
                         (11,16,28))

    def test_every_real_key_and_midpoint_matches_original_evaluator(self):
        channels = IdleChannels(ANIMATION)
        for bone, channel, keys in self.animation.channels:
            frames = [word & 0x3fff for word,value in keys]
            samples = frames + [(a+b)/2 for a,b in zip(frames,frames[1:])]
            for frame in samples:
                with self.subTest(bone=bone,channel=channel,frame=frame):
                    self.assertEqual(channels.channel_value(bone,channel,frame),
                                     self.animation.channel_value(bone,channel,frame))

    def test_only_verified_animation_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'other.anim.bin'
            path.write_bytes(b'not the canonical asset')
            with self.assertRaisesRegex(ValueError,'verified 006F'):
                IdleChannels(path)
        with self.assertRaisesRegex(ValueError,'in-range'):
            IdleChannels(ANIMATION).channel_value(1,1,111)

    def test_map_only_export_still_matches_pre_idle_bytes(self):
        text = export_models(ROOT/'assets/model/14CF.model.bin',ROOT/'assets/model/14D0.model.bin')
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),MAP_HASH)

    def test_serialized_float32_positions_keep_the_golden_hash(self):
        # A data-only hash would miss the old one-decimal XYZ serialization.
        text = export_header(self.data)
        array = text.split('banjo_vertices[] = {\n',1)[1].split('};',1)[0]
        positions = [tuple(float(v.strip().removesuffix('f'))
                           for v in row.strip(' {},').split(',')[:3]) for row in array.splitlines()]
        self.assertEqual(hashlib.sha256(b''.join(struct.pack('>3f',*p)
                                                for p in positions)).hexdigest(),GEOMETRY_HASH)

    def test_viewer_changes_only_actor_positions_not_maps_or_sort(self):
        opa, xlu = ROOT/'assets/model/14CF.model.bin', ROOT/'assets/model/14D0.model.bin'
        old = export_scene(opa,xlu,MODEL)
        new = export_scene(opa,xlu,MODEL,ANIMATION)
        def split_vertices(text):
            prefix, rest = text.split('banjo_vertices[] = {\n',1)
            vertices, suffix = rest.split('};',1)
            return prefix, vertices.splitlines(), suffix
        op, ov, os = split_vertices(old)
        np, nv, ns = split_vertices(new)
        self.assertEqual(op,np)
        self.assertEqual(os,ns)  # All textures, states, counts and SORT nodes.
        self.assertEqual(ov[:9408],nv[:9408])
        self.assertEqual(ov[11493:],nv[11493:])
        self.assertEqual(STATIC_BANJO_TRANSLATION,(0,1800,0))
        expected = [struct.pack('>3f',e['xyz'][0],e['xyz'][1]+1800,e['xyz'][2])
                    for triangle in self.reference.triangles
                    for e in (self.reference.loads[i] for i in triangle)]
        actual = []
        for before, after in zip(ov[9408:11493],nv[9408:11493]):
            self.assertEqual(before.split(',')[3:],after.split(',')[3:])  # UV/RGBA unchanged.
            actual.append(struct.pack('>3f',*(float(v.strip().removesuffix('f'))
                           for v in after.strip(' {},').split(',')[:3])))
        self.assertEqual(actual,expected)
        for name,value in [('VERTEX',12600),('TEXTURE',97),('MATERIAL',469),('DRAW',510),
                           ('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {value}\n',new)


if __name__ == '__main__':
    unittest.main()
