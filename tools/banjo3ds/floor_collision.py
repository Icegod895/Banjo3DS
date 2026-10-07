"""Static map collision for the diagnostic floor query; no render triangles.

BKModelBin collision_list_offset and BKCollisionList/BKCollisionTriangle:
include/core2/model.h. Keep source winding, surface and flags; remove only
identical full records repeated by spatial-grid cells. No actor collision.
"""
import struct
from pathlib import Path


def read_collision(path):
    data = Path(path).read_bytes()
    offset = struct.unpack_from('>I', data, 0x1c)[0]
    if not offset:
        return [], []
    vertex_list = struct.unpack_from('>I', data, 0x10)[0]
    count = struct.unpack_from('>H', data, vertex_list + 0x14)[0]
    vertices = [struct.unpack_from('>3h', data, vertex_list+24+16*i) for i in range(count)]
    header = struct.unpack_from('>11h', data, offset)
    cells, _, triangles = header[8:11]
    if cells < 0 or triangles < 0:
        raise ValueError('Invalid collision counts')
    start = offset + 24 + cells*4
    for i in range(cells):
        first, length = struct.unpack_from('>2h', data, offset+24+i*4)
        if first < 0 or length < 0 or first+length > triangles:
            raise ValueError('Invalid collision cell range')
    records = list(dict.fromkeys(struct.unpack_from('>4hI', data, start+12*i)
                                for i in range(triangles)))
    if any(not 0 <= index < count for t in records for index in t[:3]):
        raise ValueError('Invalid collision vertex index')
    return vertices, records


def collision_models(paths):
    """Yield the actual export remap, before source identity is discarded.

    This is transient host metadata, not a new movement collision format.
    Sparse consumers can retain selected identities without coordinate matching.
    """
    vertex_base, triangle_base = 0, 0
    for path in paths:
        local_vertices, local_triangles = read_collision(path)
        # Export only vertices actually referenced by collision, preserving a
        # deterministic source-index mapping and original triangle winding.
        used = sorted({i for t in local_triangles for i in t[:3]})
        remap = {old: vertex_base+i for i, old in enumerate(used)}
        yield path, local_vertices, local_triangles, remap, triangle_base
        vertex_base += len(used)
        triangle_base += len(local_triangles)
    if vertex_base > 65536:
        raise ValueError('Collision vertex indices exceed uint16')


def scene_collision(paths):
    vertices, triangles = [], []
    for _, local_vertices, local_triangles, remap, _ in collision_models(paths):
        used = sorted(remap)
        vertices.extend(local_vertices[i] for i in used)
        triangles.extend(tuple(remap[i] for i in t[:3])+t[3:] for t in local_triangles)
    return vertices, triangles


def export_collision(paths):
    vertices, triangles = scene_collision(paths)
    lines = ['\n/* Static map collision; independent of draw/SORT order. */\n',
             '#include "movement.h"\n',
             f'#define BANJO_FLOOR_VERTEX_COUNT {len(vertices)}\n',
             f'#define BANJO_FLOOR_TRIANGLE_COUNT {len(triangles)}\n',
             'static const FloorVertex banjo_floor_vertices[] = {\n']
    lines.extend('    { %d, %d, %d },\n' % v for v in vertices)
    lines.append('};\nstatic const FloorTriangle banjo_floor_triangles[] = {\n')
    lines.extend('    { %d, %d, %d, %d, 0x%08Xu },\n' % t for t in triangles)
    lines.append('};\n')
    return ''.join(lines)
