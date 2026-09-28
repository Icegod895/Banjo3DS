"""Production export and actual C traversal checked against fixed golden orders."""

import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tools.banjo3ds.export_3ds_model import (
    build_draw_batches, build_draw_plan, combine_render_passes, export_header, export_model,
)
from tools.banjo3ds.geo_sort import export_geo_header, read_sort_tree, sort_boundaries
from tools.banjo3ds.n64_displaylist_decoder import BKModel, BanjoTriangle, interpret_display_list
# Only fixed expected lists; production code never imports the reference helper.
from tools.banjo3ds.tests.test_geo_sort_reference import EXPECTED, A, B, C, D, E


ROOT = Path(__file__).resolve().parents[3]


def f32(value):
    return struct.unpack('>f', struct.pack('>f', value))[0]


def ordered_leaves(nodes, root, eye):
    """C-equivalent float plane test over the compiled, indexed representation."""
    result = []
    while root >= 0:
        node = nodes[root]
        if node.kind == 0:
            result.append(node)
        else:
            terms = [f32(f32(b - a) * f32(c - a))
                     for a, b, c in zip(node.point1, node.point2, eye)]
            q = f32(f32(terms[0] + terms[1]) + terms[2])
            children = ((node.child1, node.child2) if q >= 0
                        else (node.child2, node.child1))
            if node.flags & 1:
                children = children[1:]
            for child in children:
                result.extend(ordered_leaves(nodes, child, eye))
        root = node.next
    return result


class TestGeoSortExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = [BKModel(ROOT / f'assets/model/{name}.model.bin')
                      for name in ('14CF', '14D0')]
        cls.sources = list(map(interpret_display_list, cls.models))
        cls.data, cls.boundary = combine_render_passes(*cls.sources)
        cls.geo_sources = [(cls.models[0], cls.sources[0], 0),
                           (cls.models[1], cls.sources[1], cls.boundary)]
        cls.batches, cls.opa, cls.nodes, cls.roots = build_draw_plan(
            cls.data, cls.boundary, cls.geo_sources)

    def cases(self):
        for index, node in enumerate(self.nodes):
            if not node.kind:
                continue
            for sign, (expected, root_expected) in zip((1, -1, 0), EXPECTED[node.source_offset]):
                eye = tuple(f32(a + sign * (b - a))
                            for a, b in zip(node.point1, node.point2))
                yield index, eye, expected, root_expected

    def test_real_payloads_and_counts(self):
        sorts = [n for n in self.nodes if n.kind]
        self.assertEqual(len(sorts), 4)
        self.assertEqual(len(self.nodes), 36)
        expected = {
            0xD030: ((2728.462890625, 0, 0), (2727.462890625, 0, 0)),
            0xD058: ((0, 62.5, 0), (0, 63.5, 0)),
            0xD0D0: ((0, 1098.761962890625, 0),
                     (-0.13940666615962982, 1097.789306640625, -0.1858755499124527)),
            0xD190: ((0, -150, 0), (0, -149, 0)),
        }
        self.assertEqual({n.source_offset: (n.point1, n.point2) for n in sorts}, expected)
        self.assertTrue(all(n.flags == 0 for n in sorts))
        self.assertEqual(self.roots, [-1, 0])
        self.assertEqual((len(self.batches), self.opa), (482, 436))
        leaves = [n for n in self.nodes if not n.kind]
        self.assertCountEqual([n.gfx_index for n in leaves], A + B + C + D + E)
        draws = [i for n in leaves for i in range(n.first_draw, n.first_draw + n.draw_count)]
        self.assertEqual(sorted(draws), list(range(436, 482)))
        # Every mapped range covers precisely its original emitted triangles.
        for leaf in leaves:
            first, count = self.sources[1].display_list_ranges[leaf.gfx_index]
            selected = self.batches[leaf.first_draw:leaf.first_draw + leaf.draw_count]
            self.assertEqual(selected[0][0], (self.boundary + first) * 3)
            self.assertEqual(sum(b[1] for b in selected), count * 3)
        old = build_draw_batches(self.data.triangles, {self.boundary})
        self.assertEqual(self.batches, old)  # Includes material/combine/cull and vertices.

    def test_twelve_full_subtree_and_root_orders(self):
        for index, eye, expected, root_expected in self.cases():
            with self.subTest(index=index, eye=eye):
                self.assertEqual([n.gfx_index for n in ordered_leaves(self.nodes, index, eye)], expected)
                self.assertEqual([n.gfx_index for n in ordered_leaves(self.nodes, 0, eye)], root_expected)

    def test_reset_proxy_eye_order(self):
        pitch, yaw = map(math.radians, (-20, 145))
        axis = (-math.cos(pitch) * math.sin(yaw), math.sin(pitch),
                math.cos(pitch) * math.cos(yaw))
        eye = tuple(f32(f - 20000 * a) for f, a in zip((102.5, 189.5, 511.5), axis))
        self.assertEqual([n.gfx_index for n in ordered_leaves(self.nodes, 0, eye)],
                         C + D + E + B + A)

    def test_structural_boundary_prevents_otherwise_compatible_batch(self):
        triangles = [BanjoTriangle(0, 1, 2)] * 4
        self.assertEqual([b[:2] for b in build_draw_batches(triangles)], [(0, 12)])
        self.assertEqual([b[:2] for b in build_draw_batches(triangles, {2})],
                         [(0, 6), (6, 6)])

    def test_missing_or_repeated_geometry_is_rejected(self):
        tree = read_sort_tree(self.models[1].data)
        ranges = self.sources[1].display_list_ranges
        with self.assertRaises(ValueError):
            sort_boundaries(tree + tree, ranges, 369)
        with self.assertRaises(ValueError):
            sort_boundaries(tree, ranges, 370)
        with self.assertRaises(ValueError):
            sort_boundaries(tree, {}, 369)

    def test_single_models_and_serialized_header(self):
        for name, draws in [('08A1', 1), ('14CF', 436), ('14D0', 46), ('04FD', 4)]:
            with self.subTest(name=name):
                header = export_model(ROOT / f'assets/model/{name}.model.bin')
                self.assertIn(f'#define BANJO_DRAW_COUNT {draws}\n', header)
                self.assertIn('#define BANJO_XLU_DRAW_COUNT 0\n', header)
                if name in ('08A1', '14CF'):
                    self.assertIn('#define BANJO_GEO_NODE_COUNT 0\n', header)
        header = export_header(self.data, self.boundary, self.geo_sources)
        for name, value in [('VERTEX', 10515), ('TEXTURE', 86), ('MATERIAL', 453),
                            ('DRAW', 482), ('OPA_DRAW', 436), ('XLU_DRAW', 46), ('GEO_NODE', 36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {value}\n', header)
        self.assertIn(export_geo_header(self.nodes, self.roots), header)

    def test_04fd_and_source_flag_selection(self):
        model = BKModel(ROOT / 'assets/model/04FD.model.bin')
        data = interpret_display_list(model)
        _, _, nodes, roots = build_draw_plan(data, geo_sources=[(model, data, 0)])
        for z, expected in [(-1, [0, 44, 68]), (1, [0, 68, 44]), (0, [0, 44, 68])]:
            self.assertEqual([n.gfx_index for n in ordered_leaves(nodes, roots[0], (0, 0, z))], expected)
        # Exercise the export of the source's single-child flag, not just flags=0.
        changed = bytearray(model.data)
        struct.pack_into('>h', changed, 0x1580 + 32, 1)
        model.data = bytes(changed)
        _, _, nodes, roots = build_draw_plan(data, geo_sources=[(model, data, 0)])
        for z, expected in [(-1, [0, 68]), (1, [0, 44]), (0, [0, 68])]:
            self.assertEqual([n.gfx_index for n in ordered_leaves(nodes, roots[0], (0, 0, z))], expected)

    def test_actual_c_traversal_with_exported_nodes(self):
        compiler = shutil.which('cc')
        if compiler is None:
            self.skipTest('Host C compiler required for runtime traversal harness')
        source = (ROOT / 'platform/3ds/source/main.c').read_text()
        start = source.index('static void sceneDrawGeo(')
        traversal = source[start:source.index('\n#endif', start)]
        harness = '''#include <stdio.h>
#include <stdlib.h>
typedef struct { float x, y, z, w; } C3D_FVec;
typedef struct { int unused; } Banjo3DSRenderState;
static void sceneDrawRange(unsigned int first, unsigned int count,
    const Banjo3DSRenderState* state) {
    (void)state;
    for (unsigned int i = first; i < first + count; ++i) printf("%u ", i);
}
'''
        harness += export_geo_header(self.nodes, self.roots) + traversal
        harness += '''
int main(int argc, char** argv) {
    if (argc != 5) return 1;
    C3D_FVec eye = {strtof(argv[2], NULL), strtof(argv[3], NULL), strtof(argv[4], NULL), 1};
    sceneDrawGeo(atoi(argv[1]), eye, NULL);
    return 0;
}
'''
        by_gfx = {n.gfx_index: n for n in self.nodes if not n.kind}
        cases = [(index, eye, expected) for index, eye, expected, _ in self.cases()]
        cases += [(0, eye, expected) for _, eye, _, expected in self.cases()]
        cases += [(0, (10882.2109375, 7029.90234375, 15906.5224609375), C + D + E + B + A)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'sort.c').write_text(harness)
            subprocess.run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-ffp-contract=off', str(path / 'sort.c'), '-o', str(path / 'sort')],
                           check=True, capture_output=True, text=True)
            for index, eye, expected in cases:
                with self.subTest(index=index, eye=eye):
                    result = subprocess.run([str(path / 'sort'), str(index), *map(str, eye)],
                                            check=True, capture_output=True, text=True)
                    expected_draws = [i for gfx in expected for i in range(
                        by_gfx[gfx].first_draw, by_gfx[gfx].first_draw + by_gfx[gfx].draw_count)]
                    self.assertEqual(list(map(int, result.stdout.split())), expected_draws)
