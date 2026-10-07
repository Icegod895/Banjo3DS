"""Separate, bounded 14D0 mesh-to-expanded-VBO binding. No model export changes."""
import hashlib
from pathlib import Path
import struct
from ..n64_displaylist_decoder import BKModel, interpret_display_list

ASSET_SHA256 = '641b68978bfd380047793a217264bf489ac59d4d18d26e5cf939353a22903099'


def binding(path):
    model = BKModel(path)
    if hashlib.sha256(model.data).hexdigest() != ASSET_SHA256:
        raise ValueError('Bridge binding requires the proven canonical 14D0 asset')
    pos = struct.unpack_from('>I', model.data, 36)[0]
    count = struct.unpack_from('>h', model.data, pos)[0]
    pos += 2
    meshes = {}
    for _ in range(count):
        mesh, n = struct.unpack_from('>hh', model.data, pos)
        pos += 4
        ids = struct.unpack_from('>' + str(n) + 'h', model.data, pos)
        pos += 2*n
        if mesh in (497, 498, 499):
            meshes[mesh] = ids
    if meshes != {497: tuple(range(134,138)), 498: tuple(range(150,166)), 499: tuple(range(138,150))}:
        raise ValueError('Unproven bridge membership')
    ids = set(sum(meshes.values(), ()))
    corners = [i for t in interpret_display_list(model).triangles for i in (t.v0,t.v1,t.v2)]
    selected = [(k,i) for k,i in enumerate(corners) if i in ids]
    # Adjacent-state batching/SORT preserves this expanded source-corner order.
    # Mesh 497 is collision geometry with no emitted triangles in this model.
    if len(corners) != 1107 or [k for k,_ in selected] != list(range(162,210)) or set(i for _,i in selected) != set(range(138,166)):
        raise ValueError('Unproven bridge corner layout')
    return 162, tuple(i for _,i in selected), len(corners)


def export(path):
    first, ids, total = binding(path)
    return ('/* Generated bridge binding; original source IDs, no geometry rewrite. */\n'
            '#ifndef BANJO_GENERATED_BRIDGE_H\n#define BANJO_GENERATED_BRIDGE_H\n#include <stdint.h>\n'
            f'#define BANJO_BRIDGE_XLU_VERTEX_COUNT {total}\n'
            f'#define BANJO_BRIDGE_XLU_FIRST_CORNER {first}\n'
            f'#define BANJO_BRIDGE_CORNER_COUNT {len(ids)}\n'
            'static const uint16_t banjo_bridge_source_ids[BANJO_BRIDGE_CORNER_COUNT] = {\n    '
            + ', '.join(map(str, ids)) + '\n};\n#endif\n')


if __name__ == '__main__':
    import sys
    Path(sys.argv[2]).write_text(export(sys.argv[1]))
