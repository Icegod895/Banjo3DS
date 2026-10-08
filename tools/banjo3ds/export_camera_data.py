"""Embed proven B3Q1 bytes and real SM triggers; independent of model export."""
import hashlib
from pathlib import Path
import sys

from tools.banjo3ds.world_query_packet import read_model
from tools.banjo3ds.camera.setup import read_spiral_camera
from tools.banjo3ds.camera_zones.setup import read_zones

PACKET_HASHES = (
    '59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953',
    '500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f',
)


def export_camera_data(opa_path, xlu_path, setup_path):
    out = ['#pragma once', '#include "camera.h"']
    for role, path in enumerate((opa_path, xlu_path)):
        packet = read_model(path, role, 0x14CF+role).serialize()
        if hashlib.sha256(packet).hexdigest() != PACKET_HASHES[role]:
            raise ValueError('B3Q1 camera packet differs from the proven golden')
        name = ('opa', 'xlu')[role]
        out.append(f'static const uint8_t camera_{name}_packet[] __attribute__((aligned(4))) = {{')
        out.extend('    '+','.join(f'0x{x:02x}' for x in packet[i:i+24])+','
                   for i in range(0, len(packet), 24))
        out.append('};')
    data = read_spiral_camera(setup_path)
    def vec(values):
        return '{'+','.join(float(x).hex()+'f' for x in values)+'}'
    z = data['zoom']
    out.append('static const BanjoCameraZoom camera_zoom = {'+
               ','.join((vec(z[:3]),vec(z[3:6]),vec(z[6:8]),vec(z[8:10]),
                         float(z[10]).hex()+'f',float(z[11]).hex()+'f',str(z[12])))+'};')
    out.append('static const BanjoCameraTrigger camera_triggers[] = {')
    for t in data['triggers']:
        out.append('    {{'+','.join(map(str,t['position']))+'},'+
                   ','.join(str(t[k]) for k in ('radius','node','mask'))+'},')
    out.extend(('};', '#define CAMERA_TRIGGER_COUNT '+str(len(data['triggers']))))
    zones=read_zones(Path(setup_path))
    out.append('#include "camera_zones/zones.h"')
    out.append('static const BanjoCameraTrigger camera_zone_triggers[] = {')
    for group in zones['groups']:
        for t in group:
            out.append('    {{'+','.join(map(str,t['position']))+'},'+
                       ','.join(str(t[k]) for k in ('radius','node','mask'))+'},')
    out.append('};')
    out.append('static const BzGroup camera_zone_groups[] = {')
    first=0
    for group in zones['groups']:
        out.append('    {'+f"{first},{len(group)},{group[0]['node']}"+'},')
        first+=len(group)
    out.append('};')
    out.append('static const BzNode camera_zone_nodes[43] = {')
    for i,n in sorted(zones['nodes'].items()):
        f=n['fields'];payload='{{0,0,0},{0,0,0},{0,0},{0,0},0,0,0}';profile=0
        if n['type']==4:profile=f[1]
        if n['type']==3:
            payload='{'+','.join((vec(f[1]),vec(f[4]),vec(f[2]),vec(f[3]),
                float(f[6][0]).hex()+'f',float(f[6][1]).hex()+'f',str(f[5])))+'}'
        out.append(f"    [{i}] = {{.type={n['type']},.profile={profile},.zoom={payload}}},")
    out.extend(('};','static const BzData camera_zone_data = {camera_zone_triggers, camera_zone_groups, camera_zone_nodes, 27, 43};'))
    return '\n'.join(out)+'\n'


if __name__ == '__main__':
    opa, xlu, setup, output = sys.argv[1:]
    Path(output).write_text(export_camera_data(opa,xlu,setup))
