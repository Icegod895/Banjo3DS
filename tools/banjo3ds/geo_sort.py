"""Static-map SORT export, not a general geometry-tree interpreter.

LOD/CAMERA/DRAWDIST children and SELECTOR alternatives are included
unconditionally, preserving the viewer's SORT-only scope. No game state
is inferred. Matrix-changing nodes cannot be combined with SORT here.
See include/core2/model.h and src/core2/modelRender.c:595,858.
"""

from dataclasses import dataclass
import struct


@dataclass
class GeoNode:
    offset: int
    gfx_index: int = -1
    point1: tuple = (0.0, 0.0, 0.0)
    point2: tuple = (0.0, 0.0, 0.0)
    flags: int = 0
    children: tuple = ()


@dataclass
class DrawNode:
    kind: int  # 0 = draw range, 1 = SORT
    next: int = -1
    child1: int = -1
    child2: int = -1
    first_draw: int = 0
    draw_count: int = 0
    flags: int = 0
    point1: tuple = (0.0, 0.0, 0.0)
    point2: tuple = (0.0, 0.0, 0.0)
    # Host-side provenance for inspection and regression tests.
    source_offset: int = 0
    gfx_index: int = -1


def read_sort_tree(data):
    """Return a SORT-only tree, or [] for a model without SORT."""
    read = lambda fmt, offset: struct.unpack_from(fmt, data, offset)[0]
    root = read(">I", 4)
    if not root:
        return []
    has_sort = False
    has_transform = False

    def visit(offset, ancestors):
        nonlocal has_sort, has_transform
        if offset in ancestors:
            raise ValueError(f"Cyclic geo tree at {offset:#x}")
        ancestors = ancestors | {offset}
        kind = read(">I", offset)
        result = []
        if kind == 1:
            has_sort = True
            points = struct.unpack_from(">6f", data, offset + 8)
            flags, a, b = struct.unpack_from(">hhi", data, offset + 32)
            if flags & ~1:
                raise ValueError(f"Unsupported SORT flags {flags:#x}")
            children = tuple(visit(offset + branch, ancestors) if branch else []
                             for branch in (a, b))
            result.append(GeoNode(offset, point1=points[:3], point2=points[3:],
                                  flags=flags, children=children))
        elif kind in (3, 7):
            result.append(GeoNode(offset, gfx_index=read(">h", offset + (8 if kind == 3 else 10))))
        elif kind in (0, 2, 6, 8, 13, 14, 15):
            if kind in (0, 2):
                has_transform = True
            fmt, field = {0: (">h", 8), 2: (">B", 8), 6: (">i", 8),
                          8: (">i", 28), 13: (">h", 20),
                          14: (">h", 16), 15: (">h", 8)}[kind]
            branch = read(fmt, offset + field)
            if branch:
                result.extend(visit(offset + branch, ancestors))
        elif kind == 12:
            for index in range(read(">h", offset + 8)):
                branch = read(">i", offset + 12 + 4 * index)
                if branch:
                    result.extend(visit(offset + branch, ancestors))
        elif kind in (4, 9, 10, 11):
            pass  # NOP / reference point: no geometry child.
        else:
            raise ValueError(f"Unsupported geo node {kind:#x} at {offset:#x}")
        following = read(">i", offset + 4)
        if following:
            result.extend(visit(offset + following, ancestors))
        return result

    tree = visit(root, set())
    if has_sort and has_transform:
        raise ValueError("SORT with geo matrix transforms is not supported")
    return tree if has_sort else []


def leaves(tree):
    for node in tree:
        if node.children:
            for child in node.children:
                yield from leaves(child)
        else:
            yield node


def sort_boundaries(tree, ranges, triangle_count):
    """Validate one-to-one triangle coverage before allowing reordering."""
    covered = []
    boundaries = set()
    seen = set()
    for leaf in leaves(tree):
        if leaf.gfx_index in seen:
            raise ValueError("Repeated display list in SORT tree")
        seen.add(leaf.gfx_index)
        if leaf.gfx_index not in ranges:
            raise ValueError(f"Unknown display-list start {leaf.gfx_index}")
        first, count = ranges[leaf.gfx_index]
        boundaries.update((first, first + count))
        covered.extend(range(first, first + count))
    if sorted(covered) != list(range(triangle_count)):
        raise ValueError("SORT tree does not cover each emitted triangle exactly once")
    return boundaries


def compile_draw_tree(tree, ranges, batches, triangle_offset, nodes):
    """Append linked draw/SORT nodes; ranges refer to the unchanged draw array."""
    starts = {batch[0] // 3: index for index, batch in enumerate(batches)}
    starts[sum(batch[1] for batch in batches) // 3] = len(batches)

    def emit(sequence):
        root = previous = -1
        for source in sequence:
            index = len(nodes)
            node = DrawNode(int(bool(source.children)), source_offset=source.offset,
                            gfx_index=source.gfx_index)
            nodes.append(node)
            if root == -1:
                root = index
            if previous != -1:
                nodes[previous].next = index
            previous = index
            if source.children:
                node.point1, node.point2, node.flags = source.point1, source.point2, source.flags
                node.child1, node.child2 = (emit(child) for child in source.children)
            else:
                first, count = ranges[source.gfx_index]
                first += triangle_offset
                node.first_draw = starts[first]
                node.draw_count = starts[first + count] - node.first_draw
        return root

    return emit(tree)


def export_geo_header(nodes, roots):
    text = (f"#define BANJO_GEO_NODE_COUNT {len(nodes)}\n"
            f"#define BANJO_OPA_GEO_ROOT {roots[0]}\n"
            f"#define BANJO_XLU_GEO_ROOT {roots[1]}\n")
    if not nodes:
        return text
    text += ("typedef struct {\n"
             "    int kind, next, child1, child2;\n"
             "    unsigned int first_draw, draw_count, flags;\n"
             "    float point1[3], point2[3];\n"
             "} Banjo3DSGeoNode;\n"
             "static const Banjo3DSGeoNode banjo_geo_nodes[] = {\n")
    for node in nodes:
        p1 = ", ".join(f"{x:.9e}f" for x in node.point1)
        p2 = ", ".join(f"{x:.9e}f" for x in node.point2)
        text += (f"    {{ {node.kind}, {node.next}, {node.child1}, {node.child2}, "
                 f"{node.first_draw}, {node.draw_count}, {node.flags}, "
                 f"{{ {p1} }}, {{ {p2} }} }},\n")
    return text + "};\n"
