"""Production bake checked against the independent M3.3 reference."""
import hashlib
from dataclasses import replace
from pathlib import Path
import struct
import unittest

from tools.banjo3ds.canonical_banjo import CanonicalBanjoPose, decode_canonical_banjo
from tools.banjo3ds.n64_displaylist_decoder import BKModel, interpret_display_list
from tools.banjo3ds.export_3ds_model import (
    build_draw_batches, build_draw_plan, combine_render_passes, export_models,
    export_scene, export_canonical_banjo, place_static_banjo, STATIC_BANJO_TRANSLATION,
)
from banjo_pose_reference import canonical_reference, translation


ROOT = Path(__file__).resolve().parents[3]
ASSET = ROOT / 'assets/model/034D.model.bin'
GOLDEN = '8f6830d0a108f9e013276b2e3609ba65d0039fb542179f86581e5bf0eec36532'
M2_HASH = 'fbcf9cf77aba9779db18049990204c921d0012de83c2312d36b288ec5f087057'


def triangle_xyz(data):
    return [(data.vertices[i].x, data.vertices[i].y, data.vertices[i].z)
            for t in data.triangles for i in (t.v0,t.v1,t.v2)]


@unittest.skipUnless(ASSET.exists(), '034D asset unavailable')
class TestCanonicalBanjo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = decode_canonical_banjo(BKModel(ASSET))
        cls.reference = canonical_reference()

    def test_full_production_stream_matches_independent_golden(self):
        data, ref = self.data, self.reference
        actual = triangle_xyz(data)
        expected = [ref.loads[i]['xyz'] for t in ref.triangles for i in t]
        self.assertEqual(actual, expected)
        self.assertEqual(hashlib.sha256(b''.join(struct.pack('>3f', *p)
                                                for p in actual)).hexdigest(), GOLDEN)
        self.assertEqual([(min(p[a] for p in actual), max(p[a] for p in actual))
                          for a in range(3)], [(-74,74),(34,122),(-24,56)])
        self.assertEqual(len(actual), 2085)

    def test_all_calls_loads_and_stack_effects_survive(self):
        data, ref = self.data, self.reference
        self.assertEqual(data.pose.calls, ref.calls)
        self.assertEqual(len(data.pose.calls), 49)
        self.assertEqual(data.pose.loads, [(e['command'],e['slot'],e['vertex'],e['xyz'])
                                           for e in ref.loads])
        self.assertEqual(len(data.vertices), 723)
        self.assertEqual(len({i for t in data.triangles for i in (t.v0,t.v1,t.v2)}), 723)
        self.assertEqual(data.pose.invalid_references, 0)
        self.assertEqual(data.pose.pops, 15)
        self.assertEqual(len(data.pose.cpu), 1)
        self.assertEqual(len(data.pose.rsp), 1)
        self.assertEqual(sum(count == 0 for first,count in data.display_list_ranges.values()), 15)
        self.assertEqual(len(data.textures), 11)
        self.assertEqual(len(data.materials), 16)
        self.assertEqual(len(build_draw_batches(data.triangles)), 28)

    def test_nonidentity_matrices_detect_double_parent_and_late_transform(self):
        # Test seam only: production entry point always constructs identity bones.
        overrides = {7: translation(0,20,0), 9: translation(10,0,0)}
        model = BKModel(ASSET)
        pose = CanonicalBanjoPose(model)
        for index, matrix in overrides.items():
            pose.bones[index] = matrix
        data = interpret_display_list(model, pose=pose)
        ref = canonical_reference(bone_overrides=overrides)
        self.assertEqual(triangle_xyz(data),
                         [ref.loads[i]['xyz'] for t in ref.triangles for i in t])
        self.assertEqual(triangle_xyz(data)[90:93],
                         [(29,71,-8), (29,72,3), (43,55,7)])

    def test_other_assets_cannot_silently_use_canonical_state(self):
        model = BKModel(ASSET)
        model.data = model.data[:-1] + bytes([model.data[-1] ^ 1])
        with self.assertRaisesRegex(ValueError, 'verified 034D'):
            decode_canonical_banjo(model)


@unittest.skipUnless(all((ROOT / f'assets/model/{asset}.model.bin').exists()
                        for asset in ('14CF','14D0')), 'M2 assets unavailable')
class TestM2ByteIdentical(unittest.TestCase):
    def test_map_only_export_is_byte_identical(self):
        output = export_models(ROOT / 'assets/model/14CF.model.bin',
                               ROOT / 'assets/model/14D0.model.bin')
        self.assertEqual(hashlib.sha256(output.encode()).hexdigest(), M2_HASH)


@unittest.skipUnless(all((ROOT / f'assets/model/{asset}.model.bin').exists()
                        for asset in ('14CF','14D0','034D')), 'Scene assets unavailable')
class TestStaticBanjoScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opa_model = BKModel(ROOT / 'assets/model/14CF.model.bin')
        cls.xlu_model = BKModel(ROOT / 'assets/model/14D0.model.bin')
        cls.opa = interpret_display_list(cls.opa_model)
        cls.xlu = interpret_display_list(cls.xlu_model)
        cls.banjo = decode_canonical_banjo(BKModel(ASSET))
        cls.placed = place_static_banjo(cls.banjo)
        opaque, cls.actor_start = combine_render_passes(cls.opa, cls.placed)
        cls.data, cls.xlu_start = combine_render_passes(opaque, cls.xlu)
        cls.batches, _, cls.nodes, cls.roots = build_draw_plan(
            cls.data, cls.xlu_start,
            [(cls.opa_model,cls.opa,0), (cls.xlu_model,cls.xlu,cls.xlu_start)], cls.actor_start)

    def test_placement_is_separate_from_pose(self):
        self.assertEqual(STATIC_BANJO_TRANSLATION, (0,1800,0))
        for local, world in zip(self.banjo.vertices, self.placed.vertices):
            self.assertEqual((world.x,world.y,world.z), (local.x,local.y+1800,local.z))
            self.assertEqual(replace(world, y=world.y-1800), local)
        self.assertEqual(hashlib.sha256(b''.join(struct.pack('>3f', *p)
                         for p in triangle_xyz(self.banjo))).hexdigest(), GOLDEN)

    def test_pass_offsets_and_all_geometry_attributes(self):
        self.assertEqual((self.actor_start,self.xlu_start), (3136,3831))
        self.assertEqual(len(self.data.triangles)*3, 12600)
        self.assertEqual((len(self.data.textures),len(self.data.materials),len(self.batches)),
                         (97,469,510))
        first_triangle = first_vertex = material_offset = texture_offset = load_offset = 0
        for source in (self.opa,self.placed,self.xlu):
            for local, combined in zip(source.triangles,
                                       self.data.triangles[first_triangle:]):
                self.assertEqual(combined, replace(local,
                    v0=local.v0+first_vertex, v1=local.v1+first_vertex, v2=local.v2+first_vertex,
                    material_index=(local.material_index+material_offset
                                    if local.material_index is not None else None)))
            self.assertEqual(self.data.vertices[first_vertex:first_vertex+len(source.vertices)],
                             source.vertices)
            texture_ids = {t.texture_index:texture_offset+i for i,t in enumerate(source.textures)}
            self.assertEqual(self.data.textures[texture_offset:texture_offset+len(source.textures)],
                             [replace(t,texture_index=texture_ids[t.texture_index]) for t in source.textures])
            self.assertEqual(self.data.texture_loads[load_offset:load_offset+len(source.texture_loads)],
                             [replace(t,texture_index=texture_ids[t.texture_index]) for t in source.texture_loads])
            self.assertEqual(self.data.materials[material_offset:material_offset+len(source.materials)],
                             [replace(m,texture_load_index=m.texture_load_index+load_offset) for m in source.materials])
            first_triangle += len(source.triangles)
            first_vertex += len(source.vertices)
            material_offset += len(source.materials)
            texture_offset += len(source.textures)
            load_offset += len(source.texture_loads)
        self.assertEqual(sum(b[1] for b in self.batches),12600)
        self.assertEqual(self.batches[436][0],9408)
        self.assertEqual(self.batches[464][0],11493)

    def test_map_sort_and_batches_only_shift_by_actor_offsets(self):
        old, boundary = combine_render_passes(self.opa,self.xlu)
        batches, _, nodes, roots = build_draw_plan(old,boundary,
            [(self.opa_model,self.opa,0),(self.xlu_model,self.xlu,boundary)])
        self.assertEqual(self.roots, roots)
        self.assertEqual(self.batches[:436],batches[:436])
        self.assertEqual(self.nodes, [replace(n, first_draw=n.first_draw+28)
                                    if n.kind == 0 else n for n in nodes])
        self.assertEqual(len(self.nodes),36)
        self.assertEqual(sum(n.kind == 1 for n in self.nodes),4)
        expected = [(first+2085,count,material+16 if material >= 0 else material,mode,combine,cull)
                    for first,count,material,mode,combine,cull in batches[436:]]
        self.assertEqual(self.batches[464:],expected)

    def test_serialized_headers_and_actor_vertex_stream(self):
        header = export_scene(self.opa_model.path,self.xlu_model.path,ASSET)
        for name,value in [('VERTEX',12600),('TEXTURE',97),('MATERIAL',469),('DRAW',510),
                           ('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {value}\n',header)
        self.assertIn('#define BANJO_ACTOR_FIRST_DRAW 436\n',header)
        standalone = export_canonical_banjo(ASSET)
        for name,value in [('VERTEX',2085),('TEXTURE',11),('MATERIAL',16),('DRAW',28)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {value}\n',standalone)
        def positions(text):
            array = text.split('banjo_vertices[] = {\n',1)[1].split('};',1)[0]
            return [tuple(float(v.strip().removesuffix('f')) for v in row.strip(' {},').split(',')[:3])
                    for row in array.splitlines()]
        local = positions(standalone)
        self.assertEqual(local,triangle_xyz(self.banjo))
        self.assertEqual(positions(header)[9408:11493],
                         local)


if __name__ == '__main__':
    unittest.main()
