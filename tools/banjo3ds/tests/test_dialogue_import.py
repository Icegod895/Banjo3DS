"""Real extracted records and adversarial validation; no dialogue runtime."""
import copy
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.banjo3ds import dialogue_import as d

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / 'assets/dialog'
PATHS = tuple(ASSETS / f'{rid:04X}.dialog' for rid in d.RESOURCE_IDS)


class DialogueImportTests(unittest.TestCase):
    def setUp(self):
        self.resources = d.import_resources(PATHS)
        self.by_id = {r.resource_id: r for r in self.resources}
        self.doc = yaml.safe_load((ASSETS / '0DF4.dialog').read_text())

    def parse(self, doc):
        return d.parse_resource(0xDF4, yaml.safe_dump(doc).encode())

    def test_df4_counts(self):
        r = self.by_id[0xDF4]
        self.assertEqual(tuple(map(len, r.streams)), (7, 6))
        self.assertEqual(sum(len(s) for s in r.streams), 13)
        self.assertEqual(sum(bool(x.payload) for s in r.streams for x in s), 6)

    def test_exact_real_bytes_and_order(self):
        for path, resource in zip(PATHS, self.resources):
            raw = yaml.safe_load(path.read_text(encoding='utf-8'))
            for name, stream in zip(('bottom', 'top'), resource.streams):
                self.assertEqual([(x.opcode, x.payload) for x in stream],
                                 [(x['cmd'], x['string'].encode('ascii')) for x in raw[name]])

    def test_df4_speaker_order_from_original_dispatch(self):
        # dialog.c:724 starts bottom on a leading control; 432/460 switch boxes.
        streams = self.by_id[0xDF4].streams
        positions, active, speech = [0, 0], 0, []
        for _ in range(13):
            r = streams[active][positions[active]]
            positions[active] += 1
            if r.opcode in (4, 6):
                active ^= 1
            else:
                speech.append(r.opcode)
        self.assertEqual(speech, [0x80, 0x83, 0x81, 0x83, 0x81, 0x83])
        self.assertEqual(positions, [7, 6])

    def test_df5_structure(self):
        self.assertEqual([[r.opcode for r in s] for s in self.by_id[0xDF5].streams],
                         [[0x83, 4], [4]])

    def test_d38_empty_closing_streams(self):
        self.assertEqual(self.by_id[0xD38].streams,
                         ((d.Record(4, b''),), (d.Record(4, b''),)))

    def test_speakers_portraits_and_controls(self):
        for opcode, speaker, portrait in [(0x80, 0, 12), (0x81, 1, 13), (0x83, 3, 15),
                                         (4, 255, 255), (6, 255, 255)]:
            r = d.Record(opcode, b'')
            self.assertEqual((r.speaker, r.portrait), (speaker, portrait))

    def test_deterministic_input_order(self):
        self.assertEqual(d.generate_header(self.resources),
                         d.generate_header(d.import_resources(reversed(PATHS))))

    def test_missing_resource(self):
        with self.assertRaises(d.DialogueError):
            d.import_resources(PATHS[:-1])
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(d.DialogueError):
            d.import_resources([Path(tmp) / '0DF4.dialog'])

    def test_duplicate_identity(self):
        with self.assertRaises(d.DialogueError):
            d.import_resources((*PATHS, PATHS[0]))

    def test_invalid_identity(self):
        for rid in (0xDF3, -1, 65536, True, '0xDF4'):
            with self.subTest(rid=rid), self.assertRaises(d.DialogueError):
                d.parse_resource(rid, b'')
        with self.assertRaises(d.DialogueError):
            d.import_resources([ASSETS / 'df4.dialog'])

    def test_root_structure(self):
        for doc in (None, [], {}, {**self.doc, 'extra': 1}, {**self.doc, 'type': 'Other'}):
            with self.subTest(doc=doc), self.assertRaises(d.DialogueError):
                self.parse(doc)

    def test_stream_structure(self):
        for value in (None, {}, '', [], self.doc['bottom'] * 3):
            with self.subTest(value=value), self.assertRaises(d.DialogueError):
                self.parse({**self.doc, 'bottom': value})
        with self.assertRaises(d.DialogueError):
            self.parse({k: v for k, v in self.doc.items() if k != 'top'})

    def test_record_structure(self):
        for value in (None, [], {'cmd': 4}, {'cmd': 4, 'string': '', 'x': 0},
                      {'cmd': 4, 'string': 0}):
            doc = copy.deepcopy(self.doc)
            doc['bottom'][0] = value
            with self.subTest(value=value), self.assertRaises(d.DialogueError):
                self.parse(doc)

    def test_opcode_validation(self):
        for cmd in (True, 1.0, '0x80', -1, 256, 0, 0x82, 7):
            doc = copy.deepcopy(self.doc)
            doc['bottom'][1]['cmd'] = cmd
            with self.subTest(cmd=cmd), self.assertRaises(d.DialogueError):
                self.parse(doc)

    def test_termination(self):
        for stream in (self.doc['top'][:-1], self.doc['top'] + [{'cmd': 0x80, 'string': 'X'}]):
            with self.assertRaises(d.DialogueError):
                self.parse({**self.doc, 'top': stream})

    def test_control_payload_rejected(self):
        for cmd in (4, 6):
            with self.assertRaises(d.DialogueError):
                self.parse({**self.doc, 'top': [{'cmd': cmd, 'string': 'X'}, {'cmd': 4, 'string': ''}]})

    def test_record_text_bounds(self):
        doc = copy.deepcopy(self.doc)
        doc['bottom'][1]['string'] = 'x' * d.MAX_TEXT_BYTES
        self.parse(doc)
        doc['bottom'][1]['string'] += 'x'
        with self.assertRaises(d.DialogueError):
            self.parse(doc)

    def test_aggregate_bound(self):
        doc = {'type': 'Dialog', 'bottom': [{'cmd': 0x83, 'string': 'x'*254} for _ in range(4)] +
               [{'cmd': 0x83, 'string': 'x'*8}, {'cmd': 4, 'string': ''}],
               'top': [{'cmd': 4, 'string': ''}]}
        self.parse(doc)
        doc['bottom'][-2]['string'] += 'x'
        with self.assertRaises(d.DialogueError):
            self.parse(doc)

    def test_file_bound(self):
        with self.assertRaises(d.DialogueError):
            d.parse_resource(0xDF4, b' '*(d.MAX_FILE_BYTES+1))

    def test_unsupported_encoding_and_nul(self):
        for text in ('café', '\u2603', '\ud800', 'A\0B'):
            doc = copy.deepcopy(self.doc)
            doc['bottom'][1]['string'] = text
            with self.subTest(text=repr(text)), self.assertRaises(d.DialogueError):
                self.parse(doc)
        with self.assertRaises(d.DialogueError):
            d.parse_resource(0xDF4, b'\xff')

    def test_special_characters_preserved(self):
        text = '"quoted" \\ slash\n\r\t\x01\x7f'
        self.doc['bottom'][1]['string'] = text
        resource = self.parse(self.doc)
        self.assertEqual(resource.streams[0][1].payload, text.encode('ascii'))
        changed = tuple(resource if r.resource_id == 0xDF4 else r for r in self.resources)
        self.compile_and_check(changed)

    def test_yaml_rejection(self):
        for raw in (b'type: Dialog\ntype: Dialog', b'[', b'---\n{}\n---\n{}',
                    b'!!python/object/apply:os.system [false]', b'x: &a [*a]',
                    b'['*20 + b']'*20, b'[' + b'0,'*300 + b']'):
            with self.subTest(raw=raw[:50]), self.assertRaises(d.DialogueError):
                d.parse_resource(0xDF4, raw)

    def test_duplicate_record_keys(self):
        raw = (ASSETS / '0DF4.dialog').read_bytes().replace(b'cmd: 0x06', b'cmd: 0x06, cmd: 0x04', 1)
        with self.assertRaises(d.DialogueError):
            d.parse_resource(0xDF4, raw)

    def test_header_validates_resources(self):
        for resources in (self.resources[:-1], (*self.resources, self.resources[0]),
                          (d.Resource(0xD38, ()), *self.resources[1:])):
            with self.assertRaises(d.DialogueError):
                d.generate_header(resources)

    def compile_and_check(self, resources):
        # Execute a strict ISO-C consumer that checks every opcode, byte and offset.
        checks = ['#include "generated.h"', '#include <assert.h>', 'int main(void) {']
        for i, resource in enumerate(resources):
            base = f'banjo_dialogue_resources[{i}]'
            checks.append(f'assert({base}.resource_id == {resource.resource_id});')
            offset = 0
            for j, stream in enumerate(resource.streams):
                checks.append(f'assert({base}.streams[{j}].identity == {j});')
                checks.append(f'assert({base}.streams[{j}].count == {len(stream)});')
                for k, record in enumerate(stream):
                    rec = f'{base}.streams[{j}].records[{k}]'
                    for key, value in [('opcode', record.opcode), ('text_offset', offset),
                                       ('text_length', len(record.payload)), ('speaker', record.speaker),
                                       ('portrait', record.portrait)]:
                        checks.append(f'assert({rec}.{key} == {value});')
                    for n, value in enumerate(record.payload):
                        checks.append(f'assert({base}.text[{offset+n}] == {value});')
                    offset += len(record.payload)
            checks.append(f'assert({base}.text_length == {offset});')
        checks.append('return 0; }')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'generated.h').write_bytes(d.generate_header(resources))
            (p/'test.c').write_text('\n'.join(checks))
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic',
                            str(p/'test.c'), '-o', str(p/'test')], check=True, capture_output=True)
            subprocess.run([str(p/'test')], check=True, capture_output=True)

    def test_generated_c_lengths_and_bytes(self):
        self.compile_and_check(self.resources)

    def test_cli_determinism_and_asset_integrity(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS}
        with tempfile.TemporaryDirectory() as tmp:
            import sys
            outputs = [Path(tmp)/n for n in ('a.h', 'b.h')]
            for path in outputs:
                subprocess.run([sys.executable, '-B', '-m', 'tools.banjo3ds.dialogue_import',
                                '--output', str(path)], cwd=ROOT, check=True, capture_output=True)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS})


if __name__ == '__main__':
    unittest.main()
