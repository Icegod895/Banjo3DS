"""A3P1 actor mesh export for original skeletal models.

Banjo's B3P3 packet and generated_model.h stay untouched. This walker follows
modelRender_reset: appendage 1 selects its first branch and every other
selector is hidden. A packet with no animation bytes is the boneless identity
pose used when an actor's starting animation asset is 0 (closed molehill).
"""
from dataclasses import dataclass
from pathlib import Path
import argparse
import struct

from tools.banjo3ds.canonical_banjo import IDENTITY
from tools.banjo3ds.static_idle import (
    DEFAULT_CHANNELS, IdleChannels, add, euler_quaternion, f32, mul, quaternion_matrix,
)

BASE = 0xffff
# Display-list opcodes already interpreted for the world mesh.
ALLOWED_OPCODES = {
    4, 0x06, 0xB1, 0xB6, 0xB7, 0xB8, 0xBA, 0xBB, 0xBD, 0xBF,
    0xE6, 0xE7, 0xF0, 0xF2, 0xF3, 0xF5, 0xFC, 0xFD,
}
# modelRender_reset sets selector 1 to 1 and selector 2 to 0. mole.c clears 3 and 4.
SELECTOR_RESET = {1: 1}
PLACE_X, PLACE_Y, PLACE_Z = 2250.0, -34.0, 2774.0
PLACE_YAW, PLACE_SCALE = 0.0, 1.0
IDLE_DURATION = 7.0
MAX_MATRICES, MAX_LOADS, MAX_CORNERS, MAX_BONES = 64, 2048, 8192, 128


def _read(data, fmt, offset):
    return struct.unpack_from(fmt, data, offset)[0]


class ActorGeometry:
    """Geo/RSP walk that records the matrix slot active at each vertex load."""

    def __init__(self, model, selectors):
        self.model = model
        self.data = model.data
        self.selectors = selectors
        self.cpu = [BASE]
        self.rsp = [BASE, BASE]
        self.loads = []
        self.calls = []
        self.selector_log = []
        self.invalid_references = 0
        self.current_list = 0
        self._steps = 0

    def read(self, fmt, offset):
        return _read(self.data, fmt, offset)

    def pop(self):
        if len(self.rsp) <= 1:
            raise ValueError('actor RSP matrix stack underflow')
        self.rsp.pop()

    def display_list(self, index):
        self.current_list = index
        self.calls.append(index)
        end = self.read('>I', self.model.gfx_offset)
        for command in range(index, end):
            offset = self.model.gfx_offset + 8 + command * 8
            w0, w1 = struct.unpack_from('>II', self.data, offset)
            opcode = w0 >> 24
            if opcode == 0xBD:
                if w1 != 0:
                    raise ValueError('only modelview G_POPMTX is supported')
                self.pop()
            elif opcode not in ALLOWED_OPCODES:
                raise ValueError(f'unsupported actor display-list opcode {opcode:#x}')
            yield offset, w0, w1
            if opcode == 0xB8:
                return
        raise ValueError('unterminated actor display list')

    def _step(self):
        self._steps += 1
        if self._steps > 100000:
            raise ValueError('actor geometry walk did not terminate')

    def visit(self, offset):
        while offset:
            self._step()
            kind = self.read('>I', offset)
            if kind == 2:
                record = self.read('>b', offset + 9)
                if record < -1:
                    raise ValueError('invalid actor bone matrix id')
                self.cpu.append(BASE if record == -1 else record)
                self.rsp.append(self.cpu[-1])
                branch = self.read('>B', offset + 8)
                if branch:
                    yield from self.visit(offset + branch)
                self.cpu.pop()
                self.pop()
            elif kind == 3:
                yield from self.display_list(self.read('>h', offset + 8))
            elif kind == 5:
                yield from self.display_list(self.read('>h', offset + 8))
                field = offset + 10
                while self.read('>h', field):
                    self.rsp.append(self.cpu[-1])
                    yield from self.display_list(self.read('>h', field))
                    field += 2
            elif kind == 12:
                index = self.read('>h', offset + 10)
                count = self.read('>h', offset + 8)
                if not 0 <= index <= 0x29:
                    raise ValueError('actor selector index out of range')
                selection = 0 if index == 0 else self.selectors.get(index, 0)
                taken = False
                if index != 0 and selection > 0 and selection <= count:
                    branch = self.read('>i', offset + 12 + 4 * (selection - 1))
                    taken = bool(branch)
                    if branch:
                        yield from self.visit(offset + branch)
                elif index != 0 and selection < 0:
                    bits = -selection
                    for branch_index in range(count):
                        if bits & 1:
                            branch = self.read('>i', offset + 12 + 4 * branch_index)
                            taken = taken or bool(branch)
                            if branch:
                                yield from self.visit(offset + branch)
                        bits >>= 1
                self.selector_log.append((index, selection, taken))
            elif kind != 10:
                raise ValueError(f'unsupported actor geo node {kind:#x}')
            following = self.read('>i', offset + 4)
            offset = offset + following if following else 0

    def commands(self):
        yield from self.visit(self.read('>I', 4))
        self.pop()
        if self.cpu != [BASE] or self.rsp != [BASE]:
            raise ValueError('unbalanced actor matrix stacks')

    def transform_load(self, vertex, command, slot, source):
        raw = (vertex.x, vertex.y, vertex.z)
        matrix = self.rsp[-1]
        if matrix != BASE and not 0 <= matrix < MAX_MATRICES:
            raise ValueError('actor load matrix is outside the packet')
        self.loads.append((*raw, matrix))
        return raw


def bind_actor(path, selectors=None):
    from tools.banjo3ds.n64_displaylist_decoder import BKModel, interpret_display_list
    model = BKModel(path)
    pose = ActorGeometry(model, SELECTOR_RESET if selectors is None else selectors)
    render = interpret_display_list(model, pose=pose)
    if len(render.vertices) != len(pose.loads):
        raise ValueError('actor vertex loads and decoded vertices diverged')
    corners = [index for triangle in render.triangles for index in (triangle.v0, triangle.v1, triangle.v2)]
    if any(index is None or not 0 <= index < len(pose.loads) for index in corners):
        raise ValueError('actor triangle uses an unbound vertex')
    # A display list can shade vertices before its first texture load.
    # Those triangles stay in the mesh with material -1 and their combine.
    if any(triangle.combine is None for triangle in render.triangles):
        raise ValueError('actor triangle has no decoded combiner')
    return model, render, pose, corners


def skeleton_bytes(model_data):
    offset = struct.unpack_from('>I', model_data, 24)[0]
    if not offset:
        raise ValueError('actor model has no animation list')
    count = struct.unpack_from('>h', model_data, offset + 4)[0]
    if count <= 0:
        raise ValueError('actor skeleton is empty')
    records = model_data[offset + 8:offset + 8 + count * 16]
    if len(records) != count * 16:
        raise ValueError('actor skeleton is truncated')
    return model_data[offset:offset + 4], count, records


def _channel_bones(animation, bone_limit):
    first, last, count, pad = struct.unpack_from('>hhhH', animation)
    if first != 0 or pad != 0 or count <= 0:
        raise ValueError('unexpected actor animation header')
    bones = []
    offset = 8
    for _ in range(count):
        packed, keys = struct.unpack_from('>Hh', animation, offset)
        bone, channel = packed >> 4, packed & 15
        if keys <= 0 or bone >= bone_limit or channel > 8:
            raise ValueError('actor animation channel is out of range')
        bones.append(bone)
        offset += 4 + 4 * keys
        if offset > len(animation):
            raise ValueError('actor animation channel overruns the file')
    if offset != len(animation):
        raise ValueError('actor animation length does not match its channels')
    return last, count, bones


def build_packet(model_data, loads, corners, animation=b'', *, boneless=False):
    factor, matrix_count, records = skeleton_bytes(model_data)
    if matrix_count > MAX_MATRICES or len(loads) > MAX_LOADS or len(corners) > MAX_CORNERS:
        raise ValueError('actor packet exceeds the evaluator caps')
    max_bone = 0
    for index in range(matrix_count):
        bone, parent = struct.unpack_from('>hh', records, 16 * index + 12)
        if bone < 0 or parent < -1 or parent >= index:
            raise ValueError('actor skeleton record is inconsistent')
        max_bone = max(max_bone, bone)
    anim = b'' if boneless else bytes(animation)
    anim_last = anim_channels = 0
    if anim:
        anim_last, anim_channels, channel_bones = _channel_bones(anim, MAX_BONES)
        max_bone = max([max_bone, *channel_bones])
    elif animation:
        raise ValueError('boneless packets do not carry animation bytes')
    bone_slots = max_bone + 1
    if not 1 <= bone_slots <= MAX_BONES:
        raise ValueError('actor bone table is outside the evaluator caps')
    header = struct.pack(
        '>4s6IHH', b'A3P1', 1, matrix_count, len(loads), len(corners),
        bone_slots, len(anim), anim_last, anim_channels,
    ) + factor + struct.pack('>3I', 0, 0, 0)
    if len(header) != 48:
        raise ValueError('actor packet header is not 48 bytes')
    body = b''.join(struct.pack('>3hH', *load) for load in loads)
    body += struct.pack('>' + str(len(corners)) + 'H', *corners)
    return header + records + body + anim


class ActorClip(IdleChannels):
    """Channel sampler for one original animation file, without a SHA lock."""

    def __init__(self, data, bone_slots):
        self.bone_slots = bone_slots
        self.first, self.last, count, pad = struct.unpack_from('>hhhH', data)
        if (self.first, pad) != (0, 0) or count <= 0:
            raise ValueError('unexpected actor animation header')
        self.channels = {}
        offset = 8
        for _ in range(count):
            packed, keys = struct.unpack_from('>Hh', data, offset)
            bone, channel = packed >> 4, packed & 15
            if keys <= 0 or bone >= bone_slots or channel > 8:
                raise ValueError('actor animation channel is out of range')
            keys_out = []
            for index in range(keys):
                word, raw = struct.unpack_from('>Hh', data, offset + 4 + 4 * index)
                if raw >= 32768:
                    raw -= 65536
                keys_out.append((word, raw))
            self.channels[bone, channel] = keys_out
            offset += 4 + 4 * keys
        if offset != len(data) or len(self.channels) != count:
            raise ValueError('actor animation did not parse cleanly')

    def transforms(self, phase):
        frame = f32(f32(phase) * f32(float(self.last)))
        if not self.first <= frame <= self.last:
            raise ValueError('actor frame is outside the clip')
        channels = [list(DEFAULT_CHANNELS) for _ in range(self.bone_slots)]
        for bone, channel in self.channels:
            channels[bone][channel] = self.channel_value(bone, channel, frame)
        return [euler_quaternion(row[:3]) + tuple(row[3:]) for row in channels]


def _translate(matrix, xyz):
    for column in range(3):
        delta = add(add(mul(matrix[0][column], xyz[0]), mul(matrix[1][column], xyz[1])),
                    mul(matrix[2][column], xyz[2]))
        matrix[3][column] = add(matrix[3][column], delta)


def compose_records(factor, records, transforms):
    """Rare row-vector matrices. Parent is applied once; translation scale is factor."""
    rows = []
    for index, (pivot, bone, parent) in enumerate(records):
        if not -1 <= parent < index or not 0 <= bone < len(transforms):
            raise ValueError('invalid actor bone matrix record')
        matrix = [list(row) for row in (IDENTITY if parent == -1 else rows[parent])]
        rotation = transforms[bone][:4]
        scale = transforms[bone][4:7]
        translation = transforms[bone][7:]
        _translate(matrix, [add(point, mul(factor, channel)) for point, channel in zip(pivot, translation)])
        if rotation != (0., 0., 0., 1.):
            basis = quaternion_matrix(rotation)
            rotated = [[0.] * 3 for _ in range(3)]
            for row in range(3):
                for column in range(3):
                    for term in range(3):
                        rotated[row][column] = add(rotated[row][column], mul(basis[row][term], matrix[term][column]))
            for row in range(3):
                matrix[row][:3] = rotated[row]
        for row in range(3):
            matrix[row][:3] = [mul(value, scale[row]) for value in matrix[row][:3]]
        _translate(matrix, [-point for point in pivot])
        rows.append(matrix)
    return [tuple(tuple(row) for row in matrix) for matrix in rows]


def _identity_matrix():
    return tuple(tuple(1.0 if row == column else 0.0 for column in range(4)) for row in range(4))


@dataclass
class PacketView:
    matrix_count: int
    load_count: int
    corner_count: int
    bone_slots: int
    anim_bytes: int
    anim_last: int
    anim_channels: int
    factor: float
    boneless: bool
    records: bytes
    loads: list
    corners: list
    animation: bytes


def parse_packet(packet):
    if len(packet) < 48 or packet[:4] != b'A3P1':
        raise ValueError('not an A3P1 packet')
    version, matrix_count, load_count, corner_count, bone_slots, anim_bytes = struct.unpack_from('>6I', packet, 4)
    anim_last, anim_channels = struct.unpack_from('>HH', packet, 28)
    factor = struct.unpack_from('>f', packet, 32)[0]
    if version != 1 or struct.unpack_from('>3I', packet, 36) != (0, 0, 0):
        raise ValueError('unsupported A3P1 header')
    cursor = 48
    records = packet[cursor:cursor + matrix_count * 16]
    cursor += matrix_count * 16
    loads = [struct.unpack_from('>3hH', packet, cursor + 8 * index) for index in range(load_count)]
    cursor += load_count * 8
    corners = list(struct.unpack_from('>' + str(corner_count) + 'H', packet, cursor)) if corner_count else []
    cursor += corner_count * 2
    animation = packet[cursor:cursor + anim_bytes]
    if cursor + anim_bytes != len(packet) or len(records) != matrix_count * 16:
        raise ValueError('A3P1 packet length does not match its header')
    return PacketView(
        matrix_count, load_count, corner_count, bone_slots, anim_bytes,
        anim_last, anim_channels, factor, anim_bytes == 0, records, loads, corners, animation,
    )


def reference_evaluate(packet, phase):
    """Independent sampler. Boneless packets stay on identity matrices."""
    info = parse_packet(packet)
    if not 0.0 <= phase <= 1.0:
        raise ValueError('actor phase must be inside [0,1]')
    if info.boneless:
        transforms = [euler_quaternion((0., 0., 0.)) + (1., 1., 1., 0., 0., 0.)] * info.bone_slots
        matrices = [_identity_matrix() for _ in range(info.matrix_count)]
    else:
        clip = ActorClip(info.animation, info.bone_slots)
        if (clip.last, len(clip.channels)) != (info.anim_last, info.anim_channels):
            raise ValueError('packet animation header does not match its bytes')
        transforms = clip.transforms(phase)
        parsed = []
        for index in range(info.matrix_count):
            *pivot, bone, parent = struct.unpack_from('>3fhh', info.records, 16 * index)
            parsed.append((pivot, bone, parent))
        matrices = compose_records(f32(info.factor), parsed, transforms)
    identity = _identity_matrix()
    xyz = []
    for x, y, z, matrix_id in info.loads:
        matrix = identity if matrix_id == BASE else matrices[matrix_id]
        posed = []
        for column in range(3):
            result = 0.0
            for row in range(4):
                value = matrix[row][column]
                if row == 3 and column == 2:
                    value = f32(value - 100.0)
                scaled = f32(value * 65536.0)
                result += (int(scaled) / 65536.0) * (1 if row == 3 else (x, y, z)[row])
            posed.append(f32(result + (100.0 if column == 2 else 0.0)))
        xyz.append(tuple(posed))
    return transforms, matrices, xyz


def _geo_type(model_data):
    value = struct.unpack_from('>h', model_data, 10)[0]
    if value & ~0x6:
        raise ValueError(f'unsupported actor geo type {value:#x}')
    if value & 0x4:
        raise ValueError('actor environment mapping is outside this slice')
    return value


def _paint(render, xyz):
    if len(render.vertices) != len(xyz):
        raise ValueError('posed loads do not match the decoded mesh')
    for vertex, posed in zip(render.vertices, xyz):
        vertex.x, vertex.y, vertex.z = posed


def _c_bytes(data, indent='    '):
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        lines.append(indent + ', '.join(f'0x{byte:02x}' for byte in chunk) + ',\n')
    return ''.join(lines)


def _float_define(name, value):
    text = f'{value:.1f}' if float(value).is_integer() else f'{value:.9g}'
    if value < 0:
        return f'#define {name} ({text}f)\n'
    return f'#define {name} {text}f\n'


@dataclass
class ActorMesh:
    name: str
    model_data: bytes
    render: object
    loads: list
    corners: list
    calls: list
    selector_log: list
    packet: bytes
    geo_type: int
    linear_filter: int


def load_actor(path, name, animation=b'', *, boneless=False, selectors=None):
    model, render, pose, corners = bind_actor(path, selectors)
    packet = build_packet(model.data, pose.loads, corners, animation, boneless=boneless)
    if not boneless:
        _paint(render, reference_evaluate(packet, 0.0)[2])
    else:
        _paint(render, reference_evaluate(packet, 0.0)[2])
    geo_type = _geo_type(model.data)
    return ActorMesh(
        name, model.data, render, pose.loads, corners, pose.calls, pose.selector_log,
        packet, geo_type, 1 if geo_type & 0x2 else 0,
    )


def _texture_block(render, name, slot_base, linear_filter):
    from tools.banjo3ds.export_3ds_model import (
        encode_3ds_rgba8_pixels, export_3ds_texture_data, find_texture_slot_for_load,
        texture_wrap_to_c_constant,
    )
    text = ''
    descriptors = []
    wrap_s = texture_wrap_to_c_constant(render.sampler.wrap_s if render.sampler else 'wrap')
    wrap_t = texture_wrap_to_c_constant(render.sampler.wrap_t if render.sampler else 'wrap')
    for local, texture in enumerate(render.textures):
        slot = slot_base + local
        symbol = f'actor_texture_{slot}'
        text += f'static const unsigned char {symbol}[] = {{\n{export_3ds_texture_data(texture)}}};\n\n'
        mip_symbol = '0'
        if texture.mipmaps:
            for level, pixels in enumerate(texture.mipmaps, start=1):
                encoded = encode_3ds_rgba8_pixels(texture.width >> level, texture.height >> level, pixels)
                text += f'static const unsigned char {symbol}_mip_{level}[] = {{\n{_c_bytes(encoded)}}};\n\n'
            names = ''.join(f'    {symbol}_mip_{level},\n' for level in range(1, len(texture.mipmaps) + 1))
            text += f'static const unsigned char *const {symbol}_mipmaps[] = {{\n{names}}};\n\n'
            mip_symbol = f'{symbol}_mipmaps'
        descriptors.append(
            f'    {{ {texture.width}, {texture.height}, {len(texture.mipmaps or [])}, '
            f'{linear_filter}, {wrap_s}, {wrap_t}, {symbol}, {mip_symbol} }},\n'
        )
    slots = []
    for material in render.materials:
        load = render.texture_loads[material.texture_load_index]
        local = find_texture_slot_for_load(render, load)
        if local is None:
            raise ValueError(f'{name} material lost its texture')
        slots.append(slot_base + local)
    return text, ''.join(descriptors), slots


def export_actor_header(bottles_path, hill_path, idle_path):
    from tools.banjo3ds.export_3ds_model import build_draw_batches, export_triangle_vertices
    idle = Path(idle_path).read_bytes()
    if struct.unpack_from('>hhhH', idle) != (0, 267, 42, 0):
        raise ValueError('Bottles idle must be original animation 013B')
    hill = load_actor(hill_path, 'molehill', boneless=True)
    bottles = load_actor(bottles_path, 'bottles', idle, boneless=False)
    if hill.linear_filter != 1 or bottles.linear_filter != 0:
        raise ValueError('molehill is the only trilinear actor in this slice')
    hill_textures, hill_descriptors, hill_slots = _texture_block(hill.render, hill.name, 0, hill.linear_filter)
    bottles_textures, bottles_descriptors, bottles_slots = _texture_block(
        bottles.render, bottles.name, len(hill.render.textures), bottles.linear_filter)
    hill_batches = build_draw_batches(hill.render.triangles)
    bottles_batches = build_draw_batches(bottles.render.triangles)
    draws = []
    for first, count, material, mode, combine, cull in hill_batches:
        draws.append((first, count, material, mode, combine, int(cull)))
    vertex_base = len(hill.corners)
    material_base = len(hill_slots)
    for first, count, material, mode, combine, cull in bottles_batches:
        shifted = material if material < 0 else material + material_base
        draws.append((first + vertex_base, count, shifted, mode, combine, int(cull)))
    draw_text = ''.join(
        f'    {{ {first}, {count}, {material}, {mode}, {cull}, '
        f'{{ {", ".join(str(value) for value in combine)} }} }},\n'
        for first, count, material, mode, combine, cull in draws
    )
    materials = ''.join(f'    {{ {slot} }},\n' for slot in hill_slots + bottles_slots)
    hill_draw_count = len(hill_batches)
    bottles_info = parse_packet(bottles.packet)
    hill_info = parse_packet(hill.packet)
    defines = (
        _float_define('ACTOR_PLACE_X', PLACE_X)
        + _float_define('ACTOR_PLACE_Y', PLACE_Y)
        + _float_define('ACTOR_PLACE_Z', PLACE_Z)
        + _float_define('ACTOR_PLACE_YAW', PLACE_YAW)
        + _float_define('ACTOR_PLACE_SCALE', PLACE_SCALE)
        + _float_define('ACTOR_BOTTLES_IDLE_DURATION', IDLE_DURATION)
        + f'#define ACTOR_VERTEX_COUNT {len(hill.corners) + len(bottles.corners)}\n'
        + f'#define ACTOR_HILL_FIRST_VERTEX 0\n'
        + f'#define ACTOR_HILL_VERTEX_COUNT {len(hill.corners)}\n'
        + f'#define ACTOR_BOTTLES_FIRST_VERTEX {len(hill.corners)}\n'
        + f'#define ACTOR_BOTTLES_VERTEX_COUNT {len(bottles.corners)}\n'
        + f'#define ACTOR_HILL_FIRST_DRAW 0\n'
        + f'#define ACTOR_HILL_DRAW_COUNT {hill_draw_count}\n'
        + f'#define ACTOR_BOTTLES_FIRST_DRAW {hill_draw_count}\n'
        + f'#define ACTOR_BOTTLES_DRAW_COUNT {len(bottles_batches)}\n'
        + f'#define ACTOR_DRAW_COUNT {len(draws)}\n'
        + f'#define ACTOR_TEXTURE_COUNT {len(hill.render.textures) + len(bottles.render.textures)}\n'
        + f'#define ACTOR_MATERIAL_COUNT {len(hill_slots) + len(bottles_slots)}\n'
        + f'#define ACTOR_HILL_PACKET_SIZE {len(hill.packet)}\n'
        + f'#define ACTOR_BOTTLES_PACKET_SIZE {len(bottles.packet)}\n'
        + f'#define ACTOR_HILL_MATRIX_COUNT {hill_info.matrix_count}\n'
        + f'#define ACTOR_HILL_BONE_SLOTS {hill_info.bone_slots}\n'
        + f'#define ACTOR_BOTTLES_MATRIX_COUNT {bottles_info.matrix_count}\n'
        + f'#define ACTOR_BOTTLES_LOAD_COUNT {bottles_info.load_count}\n'
        + f'#define ACTOR_BOTTLES_BONE_SLOTS {bottles_info.bone_slots}\n'
        + f'#define ACTOR_BOTTLES_ANIM_LAST {bottles_info.anim_last}\n'
        + f'#define ACTOR_BOTTLES_ANIM_CHANNELS {bottles_info.anim_channels}\n'
    )
    return (
        '#pragma once\n'
        '/* Include after generated_model.h. Bottles and the closed molehill\n'
        ' * share selector-2 placement. The hill packet is boneless. */\n\n'
        + defines + '\n'
        'typedef struct {\n'
        '    unsigned int width;\n'
        '    unsigned int height;\n'
        '    unsigned int mipmap_count;\n'
        '    unsigned int linear_filter;\n'
        '    int wrap_s;\n'
        '    int wrap_t;\n'
        '    const unsigned char *data;\n'
        '    const unsigned char *const *mipmaps;\n'
        '} Actor3DSTexture;\n\n'
        'static const Banjo3DSVertex actor_vertices[] = {\n'
        f'{export_triangle_vertices(hill.render)}{export_triangle_vertices(bottles.render)}}};\n\n'
        f'{hill_textures}{bottles_textures}'
        'static const Actor3DSTexture actor_texture_info[] = {\n'
        f'{hill_descriptors}{bottles_descriptors}}};\n\n'
        'static const Banjo3DSMaterial actor_materials[] = {\n'
        f'{materials}}};\n\n'
        'static const Banjo3DSDraw actor_draws[] = {\n'
        f'{draw_text}}};\n\n'
        'static const unsigned char actor_molehill_packet[] = {\n'
        f'{_c_bytes(hill.packet)}}};\n\n'
        'static const unsigned char actor_bottles_packet[] = {\n'
        f'{_c_bytes(bottles.packet)}}};\n'
    )


def export_hill_open_header(hill_path, animation_path):
    """Separate B2-P1 packet; the FIX7 exporter and boneless packet stay unchanged."""
    animation = Path(animation_path).read_bytes()
    if len(animation) != 256 or struct.unpack_from('>hhhH', animation) != (0, 248, 6, 0):
        raise ValueError('Molehill opening must be original animation 013D')
    hill = load_actor(hill_path, 'molehill', animation, boneless=False)
    info = parse_packet(hill.packet)
    if (len(hill.packet), info.matrix_count, info.bone_slots, info.load_count,
            info.corner_count, info.factor) != (1256, 2, 70, 73, 168, 9.0):
        raise ValueError('Unexpected original molehill opening topology')
    defines = {
        'PACKET_SIZE': len(hill.packet), 'MATRIX_COUNT': info.matrix_count,
        'BONE_SLOTS': info.bone_slots, 'LOAD_COUNT': info.load_count,
        'VERTEX_COUNT': info.corner_count, 'ANIM_LAST': info.anim_last,
        'ANIM_CHANNELS': info.anim_channels, 'ANIM_BYTES': info.anim_bytes,
    }
    return ('#pragma once\n/* Original 0388 + 013D. No render assets duplicated. */\n'
            + ''.join(f'#define ACTOR_HILL_OPEN_{name} {value}\n' for name, value in defines.items())
            + '#define ACTOR_HILL_OPEN_DURATION 4.5f\n'
            + 'static const unsigned char actor_hill_open_packet[] = {\n'
            + _c_bytes(hill.packet) + '};\n')


def export_bottles_emergence_header(bottles_path, animation_path):
    """Original 0387/013A packet only; FIX7 render/idle export is untouched."""
    animation = Path(animation_path).read_bytes()
    if len(animation) != 10316 or struct.unpack_from('>hhhH', animation) != (0, 248, 52, 0):
        raise ValueError('Bottles emergence must be original animation 013A')
    actor = load_actor(bottles_path, 'bottles', animation, boneless=False)
    info = parse_packet(actor.packet)
    if (len(actor.packet), info.matrix_count, info.bone_slots, info.load_count,
            info.corner_count, info.factor) != (19378, 37, 72, 590, 1851, 9.0):
        raise ValueError('Unexpected original Bottles emergence topology')
    defines = {'PACKET_SIZE': len(actor.packet), 'MATRIX_COUNT': info.matrix_count,
               'BONE_SLOTS': info.bone_slots, 'LOAD_COUNT': info.load_count,
               'VERTEX_COUNT': info.corner_count, 'ANIM_LAST': info.anim_last,
               'ANIM_CHANNELS': info.anim_channels, 'ANIM_BYTES': info.anim_bytes}
    return ('#pragma once\n/* Original 0387 + 013A; existing Bottles geometry ownership. */\n'
            + ''.join(f'#define ACTOR_BOTTLES_EMERGE_{name} {value}\n' for name, value in defines.items())
            + '#define ACTOR_BOTTLES_EMERGE_DURATION 4.5f\n'
            + '#define ACTOR_BOTTLES_TRANSITION_DURATION 0.2f\n'
            + 'static const unsigned char actor_bottles_emerge_packet[] = {\n'
            + _c_bytes(actor.packet) + '};\n')


def export_exit_header(bottles_path, hill_path, bottles_animation, hill_animation):
    """Original exit packets only. Render assets and approved clips stay unchanged."""
    result = '#pragma once\n/* Original 0139/013C; Rare state-4/state-3 duration 1.7 s. */\n'
    for model, path, name, prefix, size, channels, topology in (
            (bottles_path, bottles_animation, 'bottles', 'BOTTLES_EXIT', 1532, 43, (10594, 37, 72, 590, 1851)),
            (hill_path, hill_animation, 'molehill', 'HILL_CLOSE', 232, 8, (1232, 2, 70, 73, 168))):
        animation = Path(path).read_bytes()
        if len(animation) != size or struct.unpack_from('>hhhH', animation) != (0, 82, channels, 0):
            raise ValueError('Exit requires original 0139/013C animation data')
        actor = load_actor(model, name, animation, boneless=False)
        info = parse_packet(actor.packet)
        if (len(actor.packet), info.matrix_count, info.bone_slots, info.load_count, info.corner_count) != topology or info.factor != 9.0:
            raise ValueError('Unexpected original exit topology')
        defines = {'PACKET_SIZE': len(actor.packet), 'MATRIX_COUNT': info.matrix_count,
                   'BONE_SLOTS': info.bone_slots, 'LOAD_COUNT': info.load_count,
                   'VERTEX_COUNT': info.corner_count, 'ANIM_LAST': info.anim_last,
                   'ANIM_CHANNELS': info.anim_channels, 'ANIM_BYTES': info.anim_bytes}
        result += ''.join(f'#define ACTOR_{prefix}_{key} {value}\n' for key, value in defines.items())
        result += f'#define ACTOR_{prefix}_DURATION 1.7f\n'
        result += f'static const unsigned char actor_{prefix.lower()}_packet[] = {{\n' + _c_bytes(actor.packet) + '};\n'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exit-header')
    parser.add_argument('--bottles-exit-animation')
    parser.add_argument('--hill-close-animation')
    parser.add_argument('--header')
    parser.add_argument('--bottles-emerge-header')
    parser.add_argument('--bottles-emerge-animation')
    parser.add_argument('--hill-open-header')
    parser.add_argument('--hill-open-animation')
    parser.add_argument('--bottles')
    parser.add_argument('--hill')
    parser.add_argument('--idle')
    args = parser.parse_args(argv)
    if args.exit_header:
        if args.header or args.hill_open_header or args.bottles_emerge_header or not all((args.bottles, args.hill, args.bottles_exit_animation, args.hill_close_animation)):
            parser.error('--exit-header requires both models and original exit/close animations only')
        Path(args.exit_header).write_text(export_exit_header(args.bottles, args.hill, args.bottles_exit_animation, args.hill_close_animation))
    elif args.bottles_emerge_header:
        if args.header or args.hill_open_header or not args.bottles or not args.bottles_emerge_animation:
            parser.error('--bottles-emerge-header requires --bottles and --bottles-emerge-animation only')
        Path(args.bottles_emerge_header).write_text(export_bottles_emergence_header(args.bottles, args.bottles_emerge_animation))
    elif args.hill_open_header:
        if args.header or not args.hill or not args.hill_open_animation:
            parser.error('--hill-open-header requires --hill-open-animation and no --header')
        Path(args.hill_open_header).write_text(export_hill_open_header(args.hill, args.hill_open_animation))
    else:
        if not args.header or not args.hill or not args.bottles or not args.idle:
            parser.error('--header requires --bottles, --hill and --idle')
        Path(args.header).write_text(export_actor_header(args.bottles, args.hill, args.idle))


if __name__ == '__main__':
    main()
