"""Original SORT ordering fixtures, not production renderer support.

14D0 conditional nodes deliberately bypassed by SortOnlyTree:
LOD: D280, D2B0, D2F8, D328; CAMERA: D1B8, D358, D390, D3C8;
27 DRAWDIST nodes. There are no SELECTOR nodes in 14D0.
All conditional children are included: these orders are NOT visible-frame
orders and assert nothing about LOD, camera-area visibility or animation.
"""

from pathlib import Path
import unittest

from tools.banjo3ds.tests.geo_sort_reference import SortNode, SortOnlyTree, f32


ASSETS = Path(__file__).resolve().parents[3] / "assets" / "model"

# Explicit leaf groups transcribed from the binary's branch/next links.
# Expectations do not call the traversal or derive ordering from its score.
A = [0, 25]
B = [43, 69, 94]
C = [131, 207]
D = [234, 256, 276, 297]
E = [318, 334, 350, 366, 382, 402, 422, 445, 466, 488, 510,
     533, 556, 579, 599, 620, 640, 662, 682, 702, 722]

# Entries are positive, negative, equality; each contains subtree and root.
EXPECTED = {
    0xD030: (
        (A[::-1] + B + C + D + E, A[::-1] + B + C + D + E),
        (B + C + D + E + A[::-1], B + C + D + E + A[::-1]),
        (A[::-1] + B + C + D + E, A[::-1] + B + C + D + E),
    ),
    0xD058: (
        (A, A + B + C + D + E),
        (A[::-1], A[::-1] + B + C + D + E),
        (A, A + B + C + D + E),
    ),
    0xD0D0: (
        (B + C + D + E, A + B + C + D + E),
        (C + D + E + B, A + C + D + E + B),
        (B + C + D + E, A + B + C + D + E),
    ),
    0xD190: (
        (D + E, A[::-1] + B + C + D + E),
        (E + D, A[::-1] + B + C + E + D),
        (D + E, A[::-1] + B + C + D + E),
    ),
}


def reference_cases(tree):
    for offset, expectations in EXPECTED.items():
        node = tree.sort_node(offset)
        for sign, (subtree, root) in zip((1, -1, 0), expectations):
            camera = tuple(f32(a + sign * (b - a))
                           for a, b in zip(node.point1, node.point2))
            yield offset, sign, camera, subtree, root


class TestGeoSortReference(unittest.TestCase):
    def asset_tree(self, name):
        path = ASSETS / f"{name}.model.bin"
        if not path.is_file():
            self.skipTest(f"Requires extracted real asset: {path}")
        return SortOnlyTree(path.read_bytes())

    def test_14d0_sort_payloads(self):
        tree = self.asset_tree("14D0")
        self.assertEqual(tree.root, 0xD030)
        payloads = {
            0xD030: ((2728.462890625, 0, 0), (2727.462890625, 0, 0),
                     (0xD058, 0xD0D0)),
            0xD058: ((0, 62.5, 0), (0, 63.5, 0), (0xD080, 0xD0A8)),
            0xD0D0: ((0, 1098.761962890625, 0),
                     (-0.13940666615962982, 1097.789306640625,
                      -0.1858755499124527), (0xD0F8, 0xD140)),
            0xD190: ((0, -150, 0), (0, -149, 0), (0xD1B8, 0xD268)),
        }
        for offset, (p1, p2, branches) in payloads.items():
            with self.subTest(offset=hex(offset)):
                self.assertEqual(tree.sort_node(offset), SortNode(p1, p2, 0, branches))

    def test_14d0_full_subtree_and_nested_root_orders(self):
        tree = self.asset_tree("14D0")
        for offset, sign, camera, expected_subtree, expected_root in reference_cases(tree):
            with self.subTest(offset=hex(offset), sign=sign, camera=camera):
                node = tree.sort_node(offset)
                for q in (node.original_score(camera), node.plane_score(camera)):
                    self.assertEqual((q > 0) - (q < 0), sign)
                self.assertEqual(node.branch_order(camera),
                                 (2, 1) if sign < 0 else (1, 2))
                self.assertEqual(tree.load_order(camera, offset), expected_subtree)
                actual_root = tree.load_order(camera)
                self.assertEqual(actual_root, expected_root)
                self.assertEqual(len(actual_root), 32)
                self.assertCountEqual(actual_root, A + B + C + D + E)

    def test_04fd_sort_swaps_last_displaylist_groups(self):
        tree = self.asset_tree("04FD")
        self.assertEqual(tree.root, 0x1570)
        node = tree.sort_node(0x1580)
        self.assertEqual(node, SortNode((0, 0, 0), (0, 0, -1), 0,
                                       (0x15A8, 0x15B8)))
        for z, expected in ((-1, [0, 44, 68]), (1, [0, 68, 44]),
                            (0, [0, 44, 68])):
            with self.subTest(z=z):
                camera = (0, 0, z)
                self.assertEqual(node.original_score(camera), -z)
                self.assertEqual(tree.load_order(camera), expected)

    def test_source_flag_bit_selects_only_one_branch(self):
        # The source symbol RUN_BOTH_BIT must not invert the actual contract.
        node = SortNode((0, 0, 0), (0, 0, -1), 1, (100, 200))
        for z, expected in ((-1, (2,)), (1, (1,)), (0, (2,))):
            with self.subTest(z=z):
                self.assertEqual(node.branch_order((0, 0, z)), expected)


if __name__ == "__main__":
    unittest.main()
