import struct
import unittest

from tools.banjo3ds.n64_displaylist_decoder import (
    BKModel,
    BanjoPixel,
    BanjoRenderData,
    BanjoSampler,
    BanjoTexture,
    BanjoTextureLoad,
    BanjoTriangle,
    BanjoVertex,
    decode_rgba5551,
    interpret_display_list,
)


class TestTextureDecoding(unittest.TestCase):
    def test_decodes_rgba5551(self):
        self.assertEqual(
            decode_rgba5551(0xFFFF),
            BanjoPixel(255, 255, 255, 255),
        )
        self.assertEqual(
            decode_rgba5551(0x0001),
            BanjoPixel(0, 0, 0, 255),
        )
        self.assertEqual(
            decode_rgba5551(0xF800),
            BanjoPixel(255, 0, 0, 0),
        )

    def test_reads_rgba16_texture_pixels(self):
        model = BKModel.__new__(BKModel)
        model.data = bytearray(16 + 6)
        model.texture_data_offset = 0
        model.texture_count = 1
        model.texture_infos_offset = 0
        model.data[0:4] = (16).to_bytes(4, "big")
        model.data[4:6] = (0x04).to_bytes(2, "big")
        model.data[8] = 3
        model.data[9] = 1
        model.data[16:22] = bytes.fromhex("FFFF 0001 F800")
        self.assertEqual(
            model.read_texture_pixels(0),
            [
                BanjoPixel(255, 255, 255, 255),
                BanjoPixel(0, 0, 0, 255),
                BanjoPixel(255, 0, 0, 0),
            ],
        )

    def test_reads_ci4_texture_load_pixels(self):
        model = BKModel.__new__(BKModel)
        model.data = bytes.fromhex(
            "FFFF 0001" + " 0000" * 14 + " 01"
        )
        model.texture_data_offset = 0

        load = BanjoTextureLoad(
            texture_index=0,
            texture_type="CI4",
            width=2,
            height=1,
            palette_offset=0,
            texel_offset=32,
            load_tile=7,
        )

        self.assertEqual(
            model.read_texture_load_pixels(load),
            [
                BanjoPixel(255, 255, 255, 255),
                BanjoPixel(0, 0, 0, 255),
            ],
        )


class FakeModel:
    def __init__(self, commands, texture=None):
        self.gfx_offset = 0
        self.data = struct.pack(">I", len(commands)) + bytes(4)
        self.data += b"".join(
            struct.pack(">II", w0, w1)
            for w0, w1 in commands
        )

        self.vertex_count = 3
        self.vertices = [
            {"index": 0, "x": 10, "y": 20, "z": 30, "s": 0, "t": 0, "r": 255, "g": 0, "b": 0, "a": 255},
            {"index": 1, "x": 40, "y": 50, "z": 60, "s": 32, "t": 0, "r": 0, "g": 255, "b": 0, "a": 255},
            {"index": 2, "x": 70, "y": 80, "z": 90, "s": 0, "t": 32, "r": 0, "g": 0, "b": 255, "a": 255},
        ]

        self.texture = texture or {
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

    def read_vertex(self, index):
        return self.vertices[index]

    def read_texture_pixels(self, index):
        if self.texture["type"] != 0x08:
            raise NotImplementedError

        pixel_count = self.texture["width"] * self.texture["height"]
        return [BanjoPixel(72, 79, 254, 255)] * pixel_count

    def read_texture_load_pixels(self, load):
        if load.texture_type != "CI4":
            raise NotImplementedError

        pixel_count = load.width * load.height
        return [BanjoPixel(255, 255, 255, 255)] * pixel_count

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
    def test_banjo_texture(self):
        texture = BanjoTexture(
            texture_index=7,
            width=2,
            height=1,
            pixels=[
                BanjoPixel(72, 79, 254, 0),
                BanjoPixel(255, 128, 64, 255),
            ],
        )

        self.assertEqual(texture.width, 2)
        self.assertEqual(texture.texture_index, 7)
        self.assertEqual(texture.height, 1)
        self.assertEqual(len(texture.pixels), 2)

    def test_render_data_contains_textures(self):
        texture = BanjoTexture(
            texture_index=0,
            width=1,
            height=1,
            pixels=[BanjoPixel(72, 79, 254, 0)],
        )

        render_data = BanjoRenderData(
            vertices=[],
            triangles=[],
            textures=[texture],
            texture_loads=[],
        )

        self.assertEqual(render_data.textures, [texture])

    def test_reads_rgba32_texture_pixels(self):
        model_data = bytearray(0x60)

        struct.pack_into(">I", model_data, 0x08, 0x38)
        struct.pack_into(">I", model_data, 0x38, 0x20)
        struct.pack_into(">H", model_data, 0x3C, 1)

        struct.pack_into(">I", model_data, 0x40, 0)
        struct.pack_into(">H", model_data, 0x44, 0x08)
        model_data[0x48] = 2
        model_data[0x49] = 1

        model_data[0x50:0x58] = bytes.fromhex(
            "48 4f fe 00 ff 80 40 ff"
        )

        model = BKModel.__new__(BKModel)
        model.data = bytes(model_data)
        model.texture_offset = 0x38
        model.texture_count = 1
        model.texture_infos_offset = 0x40
        model.texture_data_offset = 0x50

        self.assertEqual(
            model.read_texture_pixels(0),
            [
                BanjoPixel(72, 79, 254, 0),
                BanjoPixel(255, 128, 64, 255),
            ],
        )

    def test_interprets_ci4_texture_load(self):
        commands = [
            (0xFD100000, 0x02000100),
            (0xF5000100, 0x01000000),
            (0xF0000000, 0x0103C000),
            (0xFD500000, 0x02000120),
            (0xF5500000, 0x07018060),
            (0xF3000000, 0x073FF200),
        ]

        result = interpret_display_list(FakeModel(commands))
        loads = result.texture_loads
        self.assertEqual(
            result.textures,
            [
                BanjoTexture(
                    texture_index=0,
                    width=64,
                    height=64,
                    pixels=[BanjoPixel(255, 255, 255, 255)] * (64 * 64),
                )
            ],
        )

        self.assertEqual(len(loads), 1)

        load = loads[0]
        self.assertEqual(load.texture_index, 0)
        self.assertEqual(load.texture_type, "CI4")
        self.assertEqual(load.width, 64)
        self.assertEqual(load.height, 64)
        self.assertEqual(load.palette_offset, 0x00)
        self.assertEqual(load.texel_offset, 0x20)
        self.assertEqual(load.load_tile, 7)

    def test_interprets_rgba32_texture_load_without_palette(self):
        texture = {
            "index": 0,
            "offset": 0x000,
            "type": 0x08,
            "type_name": "RGBA32",
            "width": 8,
            "height": 8,
            "bit_depth": 32,
            "palette_size": 0,
            "size": 0x100,
        }

        commands = [
            (0xBB000001, 0x80008000),
            (0xFD180000, 0x02000000),
            (0xF5180000, 0x0708C230),
            (0xF3000000, 0x0703F200),
        ]

        result = interpret_display_list(FakeModel(commands, texture=texture))

        self.assertEqual(
            result.textures,
            [
                BanjoTexture(
                    texture_index=0,
                    width=8,
                    height=8,
                    pixels=[BanjoPixel(72, 79, 254, 255)] * 64,
                )
            ],
        )

        self.assertEqual(
            result.texture_loads,
            [
                BanjoTextureLoad(
                    texture_index=0,
                    texture_type="RGBA32",
                    width=8,
                    height=8,
                    palette_offset=None,
                    texel_offset=0x00,
                    load_tile=7,
                    scale_s=0x8000,
                    scale_t=0x8000,
                )
            ],
        )

    def test_uses_render_tile_sampler_state(self):
        commands = [
            (0xF5180000, 0x07000000),
            (0xF5180400, 0x0008C230),
        ]

        result = interpret_display_list(FakeModel(commands))

        self.assertEqual(
            result.sampler,
            BanjoSampler(
                wrap_s="clamp",
                wrap_t="clamp",
            ),
        )

    def test_binds_triangle_to_loaded_texture_material(self):
        texture = {
            "index": 0,
            "offset": 0x000,
            "type": 0x08,
            "type_name": "RGBA32",
            "width": 8,
            "height": 8,
            "bit_depth": 32,
            "palette_size": 0,
            "size": 0x100,
        }
        commands = [
            (0xBB000001, 0x80008000),
            (0xFD180000, 0x02000000),
            (0xF5180000, 0x0708C230),
            (0xF3000000, 0x0703F200),
            (0xF5180400, 0x0008C230),
            (0x04000C2F, 0x01000000),
            (0xBF000000, 0x00000204),
        ]

        result = interpret_display_list(FakeModel(commands, texture=texture))
        self.assertEqual(result.triangles[0].material_index, 0)
        self.assertEqual(result.materials[0].texture_load_index, 0)


    def test_interprets_single_triangle(self):
        commands = [
            (0x04000C2F, 0x01000000),
            (0xBF000000, 0x00000204),
        ]

        result = interpret_display_list(FakeModel(commands))

        self.assertEqual(
            result.vertices,
            [
                BanjoVertex(10, 20, 30, 0, 0, 255, 0, 0, 255),
                BanjoVertex(40, 50, 60, 32, 0, 0, 255, 0, 255),
                BanjoVertex(70, 80, 90, 0, 32, 0, 0, 255, 255),
            ],
        )
        self.assertEqual(result.triangles, [BanjoTriangle(0, 1, 2)])

    def test_interprets_triangle(self):
        commands = [
            (0x04003000, 0x01000000),
            (0xB1000204, 0x00040200),
        ]

        result = interpret_display_list(FakeModel(commands))

        self.assertEqual(len(result.triangles), 2)
        self.assertEqual(result.triangles[0], BanjoTriangle(0, 1, 2))
        self.assertEqual(result.triangles[1], BanjoTriangle(2, 1, 0))

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
