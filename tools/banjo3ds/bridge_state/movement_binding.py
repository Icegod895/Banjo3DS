"""Sparse, source-index provenance for the SM bridge movement collision.

No runtime overlay. The shared movement exporter supplies the actual remap;
the original mesh list and raw collision records supply identity, never XYZ.
"""
import hashlib
import json
from pathlib import Path
import struct

from ..floor_collision import collision_models, export_collision

MESH_IDS = (497, 498, 499)  # Existing BridgeState.mesh slot order.


def mesh_members(data, vertex_count):
    pos = struct.unpack_from('>I', data, 0x24)[0]
    count = struct.unpack_from('>h', data, pos)[0]
    pos += 2
    if count < 0:
        raise ValueError('Invalid mesh count')
    meshes = {}
    for _ in range(count):
        mesh, n = struct.unpack_from('>hh', data, pos)
        pos += 4
        if n < 0:
            raise ValueError('Invalid mesh member count')
        members = list(struct.unpack_from('>' + str(n) + 'h', data, pos))
        pos += 2*n
        if mesh in MESH_IDS:
            if mesh in meshes or len(set(members)) != n or any(v < 0 or v >= vertex_count for v in members):
                raise ValueError('Invalid bridge membership')
            meshes[mesh] = members
    if set(meshes) != set(MESH_IDS):
        raise ValueError('Missing bridge mesh')
    all_members = [v for m in MESH_IDS for v in meshes[m]]
    if len(set(all_members)) != len(all_members):
        raise ValueError('A bridge vertex belongs to multiple mesh states')
    return meshes


def provenance(opa_path, xlu_path):
    paths = (Path(opa_path), Path(xlu_path))
    models = list(collision_models(paths))
    _, vertices, triangles, remap, triangle_base = models[1]
    data = paths[1].read_bytes()
    meshes = mesh_members(data, len(vertices))
    members = {v: mesh for mesh in MESH_IDS for v in meshes[mesh]}
    co = struct.unpack_from('>I', data, 0x1c)[0]
    header = struct.unpack_from('>11h', data, co)
    raw_start = co + 24 + header[8]*4
    raw_records = [struct.unpack_from('>4hI', data, raw_start+12*i) for i in range(header[10])]
    # Full-record identity matches the existing dedup contract (including
    # winding, surface and flags), not positions or an unordered vertex set.
    unique_index = {record: i for i, record in enumerate(triangles)}
    selected = {}
    for i, record in enumerate(triangles):
        affected = sorted({members[v] for v in record[:3] if v in members})
        if affected:
            selected[triangle_base+i] = dict(
                movement_triangle=triangle_base+i, source_unique_triangle=i,
                source_vertices=list(record[:3]),
                movement_vertices=[remap[v] for v in record[:3]],
                meshes=affected, surface=record[3], flags=record[4])
    occurrences = []
    for cell in range(header[8]):
        first, length = struct.unpack_from('>hh', data, co+24+4*cell)
        for raw_index in range(first, first+length):
            movement_triangle = triangle_base + unique_index[raw_records[raw_index]]
            if movement_triangle in selected:
                occurrences.append(dict(cell=cell, raw_record=raw_index,
                                        movement_triangle=movement_triangle))
    vertex_rows = []
    mesh_rows = []
    for slot, mesh in enumerate(MESH_IDS):
        mapped = []
        for source in meshes[mesh]:
            movement = remap.get(source)
            if movement is not None:
                vertex_rows.append(dict(source_vertex=source, movement_vertex=movement, mesh_slot=slot))
                mapped.append(movement)
        related = [i for i, row in selected.items() if mesh in row['meshes']]
        mesh_rows.append(dict(mesh=mesh, mesh_slot=slot,
                              source_vertices=meshes[mesh], movement_vertices=mapped,
                              excluded_source_vertices=[v for v in meshes[mesh] if v not in remap],
                              movement_triangles=related,
                              occurrence_count=sum(o['movement_triangle'] in related for o in occurrences)))
    vertex_count = sum(len(m[3]) for m in models)
    triangle_count = sum(len(m[2]) for m in models)
    if any(row['movement_vertex'] > 65535 or row['source_vertex'] > 65535 for row in vertex_rows):
        raise ValueError('Bridge binding exceeds uint16')
    collision_text = export_collision(paths).encode('utf-8')
    return dict(format='Banjo3DS bridge movement provenance v1',
                model_role='XLU', source_asset='14D0',
                source_sha256={asset: hashlib.sha256(p.read_bytes()).hexdigest()
                               for asset, p in zip(('14CF', '14D0'), paths)},
                movement_collision_text_sha256=hashlib.sha256(collision_text).hexdigest(),
                movement_vertex_count=vertex_count, movement_triangle_count=triangle_count,
                meshes=mesh_rows, vertices=vertex_rows,
                triangles=list(selected.values()), occurrences=occurrences)


def export_header(info):
    rows = info['vertices']
    lines = ['/* Generated source-index provenance. No coordinate matching. */\n',
             '#ifndef BANJO_BRIDGE_MOVEMENT_BINDING_H\n#define BANJO_BRIDGE_MOVEMENT_BINDING_H\n',
             '#include <stdint.h>\n',
             '#define BANJO_BRIDGE_MOVEMENT_BINDING_VERSION 1\n',
             f'#define BANJO_BRIDGE_MOVEMENT_BINDING_COUNT {len(rows)}\n',
             f'#define BANJO_BRIDGE_MOVEMENT_VERTEX_COUNT {info["movement_vertex_count"]}\n',
             f'#define BANJO_BRIDGE_MOVEMENT_TRIANGLE_COUNT {info["movement_triangle_count"]}\n',
             '/* Asset and exact collision-export identity; not resident strings. */\n']
    for asset, digest in info['source_sha256'].items():
        lines.append(f'/* {asset} SHA256: {digest} */\n')
    lines.append(f'/* Collision text SHA256: {info["movement_collision_text_sha256"]} */\n')
    for mesh in info['meshes']:
        lines.append(f'/* Slot {mesh["mesh_slot"]}: mesh {mesh["mesh"]}, '
                     f'{len(mesh["source_vertices"])} source vertices, '
                     f'{len(mesh["movement_vertices"])} movement vertices, '
                     f'{len(mesh["movement_triangles"])} triangles, '
                     f'{mesh["occurrence_count"]} raw occurrences. */\n')
    lines.append('/* Columns: movement vertex, original 14D0 vertex, BridgeState.mesh slot. */\n'
                 'static const uint16_t banjo_bridge_movement_binding[BANJO_BRIDGE_MOVEMENT_BINDING_COUNT][3] = {\n')
    lines.extend('    { %d, %d, %d },\n' % (r['movement_vertex'], r['source_vertex'], r['mesh_slot']) for r in rows)
    lines.append('};\n#endif\n')
    return ''.join(lines)


def export_audit(info):
    return json.dumps(info, indent=2, sort_keys=True) + '\n'


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('opa', type=Path)
    parser.add_argument('xlu', type=Path)
    parser.add_argument('header', type=Path)
    parser.add_argument('audit', type=Path)
    args = parser.parse_args()
    info = provenance(args.opa, args.xlu)
    args.header.write_text(export_header(info), encoding='utf-8', newline='\n')
    args.audit.write_text(export_audit(info), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
