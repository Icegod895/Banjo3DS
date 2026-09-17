import struct
import unittest

from tools.banjo3ds.n64_displaylist_decoder import (
    BanjoTextureLoad,
    interpret_display_list,
)


class FakeModel:
    def __init__(self, commands):
        self.gfx_offset = 0
        self.data = struct.pack(">I", len(commands) * 8) + bytes(4)
        self.data += b"".join(
            struct.pack(">II", w0, w1)
            for w0, w1 in commands
        )

        self.texture = {
            "index": 0,
            "offset": 0x100,
            "type": 0x01,
            "type_name": "CI4",
            "width": 64,
            "height": 64,
            "bit_depth": 4,
            "palette_size": 32,
            "size": 0x820,
        }

    def find_texture_containing_offset(self, offset):
        start = self.texture["offset"]
        end = start + self.texture["size"]

        if start <= offset < end:
            return {
                "texture": self.texture,
                "relative_offset": offset - start,
            }

        return None


class TestN64DisplayListDecoder(unittest.TestCase):
    def test_interprets_ci4_texture_load(self):
        commands = [
            (0xFD100000, 0x02000100),
            (0xF5000100, 0x01000000),
            (0xF0000000, 0x0103C000),
            (0xFD500000, 0x02000120),
            (0xF5500000, 0x07018060),
            (0xF3000000, 0x073FF200),
        ]

        loads = interpret_display_list(FakeModel(commands))

        self.assertEqual(len(loads), 1)

        load = loads[0]
        self.assertEqual(load.texture_index, 0)
        self.assertEqual(load.texture_type, "CI4")
        self.assertEqual(load.width, 64)
        self.assertEqual(load.height, 64)
        self.assertEqual(load.palette_offset, 0x00)
        self.assertEqual(load.texel_offset, 0x20)
        self.assertEqual(load.load_tile, 7)

    def test_banjo_texture_load(self):
        load = BanjoTextureLoad(
            texture_index=79,
            texture_type="CI4",
            width=64,
            height=64,
            palette_offset=0x00,
            texel_offset=0x20,
            load_tile=7,
        )

        self.assertEqual(load.texture_index, 79)
        self.assertEqual(load.palette_offset, 0x00)
        self.assertEqual(load.texel_offset, 0x20)


if __name__ == "__main__":
    unittest.main()
