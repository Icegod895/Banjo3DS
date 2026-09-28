"""Test-only SORT reference; never used by the exporter or runtime.

SORT-only traversal deliberately visits ALL LOD/DRAWDIST/CAMERA children
and ALL SELECTOR alternatives in stored order. It is not a visible-frame
simulation. Unknown node types fail rather than silently dropping geometry.
Sources: src/core2/modelRender.c:595,719,752,791,847,858;
include/core2/model.h:64; src/core1/mlmtx.c:521.
"""

from dataclasses import dataclass
import struct


def f32(value):
    return struct.unpack(">f", struct.pack(">f", value))[0]


@dataclass(frozen=True)
class SortNode:
    point1: tuple
    point2: tuple
    flags: int
    branches: tuple

    def plane_score(self, camera):
        """Algebraic map-space equivalent, evaluated in Python precision."""
        return sum((b - a) * (c - a)
                   for a, b, c in zip(self.point1, self.point2, camera))

    def original_score(self, camera):
        """Literal camera-relative float32 subtract/dot path, no fast-math.

        Maps have NULL position/rotation and scale=1: p_i = P_i - C.
        Keep this separate from plane_score: rounding near a plane can differ.
        """
        p1 = tuple(f32(a - f32(c)) for a, c in zip(self.point1, camera))
        p2 = tuple(f32(b - f32(c)) for b, c in zip(self.point2, camera))
        products = [f32(f32(b - a) * a) for a, b in zip(p1, p2)]
        return -f32(f32(products[0] + products[1]) + products[2])

    def branch_order(self, camera):
        q = self.original_score(camera)
        # The source's RUN_BOTH_BIT name is misleading: set means ONE branch.
        if self.flags & 1:
            return (2,) if q >= 0 else (1,)
        return (1, 2) if q >= 0 else (2, 1)


class SortOnlyTree:
    def __init__(self, data):
        self.data = data
        self.root = self.read(">I", 4)

    def read(self, fmt, offset):
        return struct.unpack_from(fmt, self.data, offset)[0]

    def sort_node(self, offset):
        if self.read(">I", offset) != 1:
            raise ValueError(f"Not SORT: {offset:#x}")
        p = struct.unpack_from(">6f", self.data, offset + 8)
        flags, b1, b2 = struct.unpack_from(">hhi", self.data, offset + 32)
        return SortNode(p[:3], p[3:], flags,
                        tuple(offset + b if b else None for b in (b1, b2)))

    def load_order(self, camera, start=None):
        """Return complete LOADDL order, including next siblings, SORT-only."""
        output = []

        def visit(offset, ancestors):
            if offset in ancestors:
                raise ValueError(f"Cyclic geo tree at {offset:#x}")
            ancestors = ancestors | {offset}
            kind = self.read(">I", offset)
            if kind == 1:
                node = self.sort_node(offset)
                for number in node.branch_order(camera):
                    branch = node.branches[number - 1]
                    if branch is not None:
                        visit(branch, ancestors)
            elif kind == 3:
                output.append(self.read(">h", offset + 8))
            elif kind in (8, 13, 15):
                fmt, field = {8: (">i", 28), 13: (">h", 20),
                              15: (">h", 8)}[kind]
                branch = self.read(fmt, offset + field)
                if branch:
                    visit(offset + branch, ancestors)
            elif kind == 12:
                for index in range(self.read(">h", offset + 8)):
                    branch = self.read(">i", offset + 12 + 4 * index)
                    if branch:
                        visit(offset + branch, ancestors)
            else:
                raise ValueError(f"Unsupported SORT-only node {kind:#x} at {offset:#x}")
            following = self.read(">i", offset + 4)
            if following:
                visit(offset + following, ancestors)

        visit(self.root if start is None else start, set())
        return output
