"""Bounded import of extracted Rare YAML; data only, not a dialogue interpreter.

See DIALOGUE_IMPORT.md for the schema, limits and original source evidence.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path

import yaml

RESOURCE_IDS = (0xD38, 0xDF4, 0xDF5)
STREAM_NAMES = ('bottom', 'top')
SPEAKERS = {0x80: (0, 0xC), 0x81: (1, 0xD), 0x83: (3, 0xF)}
CONTROLS = (0x04, 0x06)
MAX_FILE_BYTES = 16384
MAX_STREAM_RECORDS = 16
MAX_TEXT_BYTES = 254
MAX_RESOURCE_TEXT_BYTES = 1024
MAX_YAML_NODES = 256
MAX_YAML_DEPTH = 8


class DialogueError(ValueError):
    """Invalid or outside the explicitly supported extracted-resource subset."""


class _Loader(yaml.SafeLoader):
    """Reject aliases, excessive nesting and duplicate keys before construction."""
    def __init__(self, stream):
        super().__init__(stream)
        self.node_count = 0
        self.depth = 0

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise DialogueError('YAML aliases are unsupported')
        self.node_count += 1
        self.depth += 1
        try:
            if self.node_count > MAX_YAML_NODES or self.depth > MAX_YAML_DEPTH:
                raise DialogueError('YAML complexity bound exceeded')
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str or key in result:
                raise DialogueError('mapping keys must be unique strings')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


@dataclass(frozen=True)
class Record:
    opcode: int
    payload: bytes

    @property
    def speaker(self):
        return SPEAKERS.get(self.opcode, (0xFF, 0xFF))[0]

    @property
    def portrait(self):
        return SPEAKERS.get(self.opcode, (0xFF, 0xFF))[1]


@dataclass(frozen=True)
class Resource:
    resource_id: int
    streams: tuple  # bottom, top; immutable tuples of Record


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise DialogueError('unexpected or missing mapping fields')


def parse_resource(resource_id, data):
    """Decode UTF-8 YAML and preserve ASCII speech bytes, without terminators."""
    if type(resource_id) is not int or resource_id not in RESOURCE_IDS:
        raise DialogueError('unsupported resource ID')
    if type(data) is not bytes or len(data) > MAX_FILE_BYTES:
        raise DialogueError('resource file size/type bound')
    try:
        document = yaml.load(data.decode('utf-8', errors='strict'), Loader=_Loader)
    except (UnicodeError, yaml.YAMLError) as exc:
        raise DialogueError(f'invalid UTF-8/YAML: {exc}') from exc
    _keys(document, ('type', 'bottom', 'top'))
    if document['type'] != 'Dialog':
        raise DialogueError('expected type Dialog')
    streams = []
    total = 0
    for name in STREAM_NAMES:
        raw = document[name]
        if type(raw) is not list or not 1 <= len(raw) <= MAX_STREAM_RECORDS:
            raise DialogueError('stream record count bound')
        records = []
        for i, item in enumerate(raw):
            _keys(item, ('cmd', 'string'))
            opcode, text = item['cmd'], item['string']
            if type(opcode) is not int or opcode not in (*CONTROLS, *SPEAKERS):
                raise DialogueError('unsupported command/speaker opcode')
            if type(text) is not str:
                raise DialogueError('string payload required')
            try:
                payload = text.encode('ascii', errors='strict')
            except UnicodeError as exc:
                raise DialogueError('non-ASCII Rare text encoding is unsupported') from exc
            if b'\0' in payload or len(payload) > MAX_TEXT_BYTES:
                raise DialogueError('embedded NUL or text length bound')
            if opcode in CONTROLS and payload:
                raise DialogueError('selected control opcodes require empty payload')
            if opcode == 4 and i != len(raw) - 1:
                raise DialogueError('records after stream close')
            records.append(Record(opcode, payload))
            total += len(payload)
        if records[-1].opcode != 4:
            raise DialogueError('stream must terminate with close')
        streams.append(tuple(records))
    if total > MAX_RESOURCE_TEXT_BYTES:
        raise DialogueError('aggregate resource text bound')
    return Resource(resource_id, tuple(streams))


def import_resources(paths):
    """Require exactly the three canonical filenames; reject duplicate identities."""
    resources = {}
    names = {f'{rid:04X}.dialog': rid for rid in RESOURCE_IDS}
    for path in map(Path, paths):
        if path.name not in names:
            raise DialogueError(f'unsupported resource filename: {path.name}')
        rid = names[path.name]
        if rid in resources:
            raise DialogueError(f'duplicate resource ID: {rid:04X}')
        try:
            with path.open('rb') as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError as exc:
            raise DialogueError(f'cannot read resource: {path}') from exc
        resources[rid] = parse_resource(rid, data)
    if set(resources) != set(RESOURCE_IDS):
        raise DialogueError('missing required resources')
    return tuple(resources[rid] for rid in RESOURCE_IDS)


def generate_header(resources):
    """Emit immutable fixed-width data; offsets/lengths address bytes, not C strings."""
    resources = tuple(sorted(resources, key=lambda r: r.resource_id))
    if tuple(r.resource_id for r in resources) != RESOURCE_IDS:
        raise DialogueError('expected each selected resource exactly once')
    # Revalidate public Resource inputs rather than trusting handcrafted instances.
    for resource in resources:
        if len(resource.streams) != 2:
            raise DialogueError('expected two streams')
        doc = {'type': 'Dialog'}
        for name, stream in zip(STREAM_NAMES, resource.streams):
            doc[name] = [{'cmd': r.opcode, 'string': r.payload.decode('ascii')}
                         for r in stream]
        parse_resource(resource.resource_id, yaml.safe_dump(doc).encode('utf-8'))
    lines = [
        '/* Generated by tools.banjo3ds.dialogue_import. Data only; ASCII payloads. */',
        '#ifndef BANJO3DS_GENERATED_DIALOGUE_H', '#define BANJO3DS_GENERATED_DIALOGUE_H',
        '#include <stdint.h>',
        '#define BANJO_DIALOGUE_RESOURCE_COUNT 3',
        '#define BANJO_DIALOGUE_STREAM_COUNT 2',
        '#define BANJO_DIALOGUE_BOTTOM 0', '#define BANJO_DIALOGUE_TOP 1',
        '#define BANJO_DIALOGUE_NO_SPEAKER 255',
        '/* No implicit NUL: text_offset + text_length <= resource.text_length. */',
        'typedef struct {',
        '    uint16_t text_offset, text_length;',
        '    uint8_t opcode, speaker, portrait;',
        '} BanjoDialogueRecord;',
        'typedef struct {',
        '    const BanjoDialogueRecord *records;',
        '    uint8_t identity, count;',
        '} BanjoDialogueStream;',
        'typedef struct {',
        '    const uint8_t *text;',
        '    uint16_t resource_id, text_length;',
        '    BanjoDialogueStream streams[BANJO_DIALOGUE_STREAM_COUNT];',
        '} BanjoDialogueResource;',
    ]
    rows = []
    for resource in resources:
        prefix = f'banjo_dialogue_{resource.resource_id:04x}'
        payload = b''.join(r.payload for stream in resource.streams for r in stream)
        # ISO C forbids zero-size arrays; empty resources have an unused sentinel.
        storage = payload or b'\0'
        lines.append(f'static const uint8_t {prefix}_text[{len(storage)}] = {{')
        for i in range(0, len(storage), 16):
            lines.append('    ' + ', '.join(f'0x{x:02x}' for x in storage[i:i+16]) + ',')
        lines.append('};')
        offset = 0
        for name, stream in zip(STREAM_NAMES, resource.streams):
            lines.append(f'static const BanjoDialogueRecord {prefix}_{name}[{len(stream)}] = {{')
            for record in stream:
                lines.append(f'    {{{offset}, {len(record.payload)}, 0x{record.opcode:02x}, '
                             f'0x{record.speaker:02x}, 0x{record.portrait:02x}}},')
                offset += len(record.payload)
            lines.append('};')
        streams = ', '.join(f'{{{prefix}_{name}, {i}, {len(resource.streams[i])}}}'
                            for i, name in enumerate(STREAM_NAMES))
        rows.append(f'    {{{prefix}_text, 0x{resource.resource_id:04x}, {len(payload)}, '
                    '{' + streams + '}},')
    lines += ['static const BanjoDialogueResource banjo_dialogue_resources[3] = {',
              *rows, '};', '#endif', '']
    return '\n'.join(lines).encode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'assets/dialog')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        resources = import_resources(args.assets_dir / f'{rid:04X}.dialog' for rid in RESOURCE_IDS)
        output = generate_header(resources)
    except DialogueError as exc:
        parser.error(str(exc))
    args.output.write_bytes(output)


if __name__ == '__main__':
    main()
