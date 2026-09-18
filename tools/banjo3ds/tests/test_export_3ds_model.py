import unittest

from tools.banjo3ds.export_3ds_model import export_vertex_data
from tools.banjo3ds.n64_displaylist_decoder import BanjoVertex


class TestExport3DSModel(unittest.TestCase):
    def test_exports_vertex_data(self):
        vertices = [
            BanjoVertex(
                x=0,
                y=18,
                z=0,
                s=247,
                t=722,
                r=254,
                g=254,
                b=254,
                a=255,
            ),
            BanjoVertex(
                x=-18,
                y=-18,
                z=0,
                s=587,
                t=-32,
                r=254,
                g=254,
                b=254,
                a=255,
            ),
            BanjoVertex(
                x=18,
                y=-18,
                z=0,
                s=-146,
                t=-32,
                r=254,
                g=254,
                b=254,
                a=255,
            ),
        ]

        result = export_vertex_data(vertices)

        self.assertEqual(
            result,
            (
                "    { 0.0f, 18.0f, 0.0f },\n"
                "    { -18.0f, -18.0f, 0.0f },\n"
                "    { 18.0f, -18.0f, 0.0f },\n"
            ),
        )


if __name__ == "__main__":
    unittest.main()


class TestExport3DSHeader(unittest.TestCase):
    def test_exports_header(self):
        from tools.banjo3ds.export_3ds_model import export_header

        vertices = [
            BanjoVertex(
                x=0,
                y=18,
                z=0,
                s=247,
                t=722,
                r=254,
                g=254,
                b=254,
                a=255,
            ),
        ]

        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoRenderData,
            BanjoTriangle,
        )

        render_data = BanjoRenderData(
            vertices=vertices,
            triangles=[BanjoTriangle(0, 0, 0)],
            textures=[],
            texture_loads=[],
        )

        result = export_header(render_data)

        self.assertIn(
            "static const Banjo3DSVertex banjo_vertices[] = {",
            result,
        )
        self.assertIn(
            "    { 0.0f, 18.0f, 0.0f },",
            result,
        )
        self.assertIn(
            "#define BANJO_VERTEX_COUNT 3",
            result,
        )


class TestExport3DSTriangles(unittest.TestCase):
    def test_exports_vertices_in_triangle_order(self):
        from tools.banjo3ds.export_3ds_model import export_triangle_vertices
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoRenderData,
            BanjoTriangle,
        )

        vertices = [
            BanjoVertex(10, 0, 0, 0, 0, 255, 255, 255, 255),
            BanjoVertex(20, 0, 0, 0, 0, 255, 255, 255, 255),
            BanjoVertex(30, 0, 0, 0, 0, 255, 255, 255, 255),
            BanjoVertex(99, 0, 0, 0, 0, 255, 255, 255, 255),
        ]

        render_data = BanjoRenderData(
            vertices=vertices,
            triangles=[BanjoTriangle(2, 0, 1)],
            textures=[],
            texture_loads=[],
        )

        result = export_triangle_vertices(render_data)

        self.assertEqual(
            result,
            (
                "    { 30.0f, 0.0f, 0.0f },\n"
                "    { 10.0f, 0.0f, 0.0f },\n"
                "    { 20.0f, 0.0f, 0.0f },\n"
            ),
        )


class TestExport3DSModelPipeline(unittest.TestCase):
    def test_exports_real_08a1_model(self):
        from pathlib import Path

        from tools.banjo3ds.export_3ds_model import export_model

        result = export_model(Path("assets/model/08A1.model.bin"))

        self.assertIn(
            "    { 0.0f, 18.0f, 0.0f,",
            result,
        )
        self.assertIn(
            "    { -18.0f, -18.0f, 0.0f,",
            result,
        )
        self.assertIn(
            "    { 18.0f, -18.0f, 0.0f,",
            result,
        )
        self.assertIn(
            "#define BANJO_VERTEX_COUNT 3",
            result,
        )

    def test_exports_real_08a1_model_with_texture_coordinates(self):
        from pathlib import Path

        from tools.banjo3ds.export_3ds_model import export_model

        result = export_model(Path("assets/model/08A1.model.bin"))

        self.assertIn(
            "    { 0.0f, 18.0f, 0.0f, 0.482421875f, 1.410156250f },",
            result,
        )
        self.assertIn(
            "    { -18.0f, -18.0f, 0.0f, 1.146484375f, -0.062500000f },",
            result,
        )
        self.assertIn(
            "    { 18.0f, -18.0f, 0.0f, -0.285156250f, -0.062500000f },",
            result,
        )

    def test_exports_real_08a1_vertex_structure_with_texture_coordinates(self):
        from pathlib import Path

        from tools.banjo3ds.export_3ds_model import export_model

        result = export_model(Path("assets/model/08A1.model.bin"))

        self.assertIn(
            "    float u;\n"
            "    float v;\n",
            result,
        )

    def test_exports_real_08a1_texture_for_3ds(self):
        from pathlib import Path
        from tools.banjo3ds.export_3ds_model import export_model

        result = export_model(Path("assets/model/08A1.model.bin"))

        self.assertIn("#define BANJO_TEXTURE_WIDTH 8", result)
        self.assertIn("#define BANJO_TEXTURE_HEIGHT 8", result)
        self.assertIn(
            "static const unsigned char banjo_texture[] = {",
            result,
        )

class TestTextureCoordinates(unittest.TestCase):
    def test_converts_s10_5_to_texel_coordinate(self):
        from tools.banjo3ds.export_3ds_model import s10_5_to_texel

        self.assertEqual(s10_5_to_texel(0), 0.0)
        self.assertEqual(s10_5_to_texel(32), 1.0)
        self.assertEqual(s10_5_to_texel(-32), -1.0)
        self.assertEqual(s10_5_to_texel(247), 247 / 32)

    def test_applies_rsp_texture_scale(self):
        from tools.banjo3ds.export_3ds_model import apply_texture_scale

        self.assertEqual(apply_texture_scale(1.0, 0xFFFF), 0xFFFF / 65536)
        self.assertEqual(apply_texture_scale(1.0, 0x8000), 0.5)
        self.assertEqual(apply_texture_scale(247 / 32, 0x8000), 3.859375)

    def test_normalizes_texel_coordinate(self):
        from tools.banjo3ds.export_3ds_model import normalize_texel_coordinate

        self.assertEqual(normalize_texel_coordinate(0.0, 8), 0.0)
        self.assertEqual(normalize_texel_coordinate(4.0, 8), 0.5)
        self.assertEqual(normalize_texel_coordinate(8.0, 8), 1.0)
        self.assertEqual(normalize_texel_coordinate(-1.0, 8), -0.125)

    def test_clamps_texel_coordinate(self):
        from tools.banjo3ds.export_3ds_model import clamp_texel_coordinate

        self.assertEqual(clamp_texel_coordinate(-1.0, 8), 0.0)
        self.assertEqual(clamp_texel_coordinate(0.0, 8), 0.0)
        self.assertEqual(clamp_texel_coordinate(3.5, 8), 3.5)
        self.assertEqual(clamp_texel_coordinate(7.0, 8), 7.0)
        self.assertEqual(clamp_texel_coordinate(8.0, 8), 7.0)

    def test_converts_n64_texture_coordinate_to_normalized_uv(self):
        from tools.banjo3ds.export_3ds_model import n64_texture_coordinate_to_uv

        self.assertEqual(
            n64_texture_coordinate_to_uv(247, 0x8000, 8),
            0.482421875,
        )
        self.assertEqual(
            n64_texture_coordinate_to_uv(722, 0x8000, 8),
            1.41015625,
        )
        self.assertEqual(
            n64_texture_coordinate_to_uv(-32, 0x8000, 8),
            -0.0625,
        )

    def test_exports_vertex_with_texture_coordinates(self):
        from tools.banjo3ds.export_3ds_model import export_textured_vertex
        from tools.banjo3ds.n64_displaylist_decoder import BanjoVertex

        vertex = BanjoVertex(
            x=0,
            y=18,
            z=0,
            s=247,
            t=722,
            r=254,
            g=254,
            b=254,
            a=255,
        )

        result = export_textured_vertex(
            vertex,
            scale_s=0x8000,
            scale_t=0x8000,
            texture_width=8,
            texture_height=8,
        )

        self.assertEqual(
            result,
            "    { 0.0f, 18.0f, 0.0f, 0.482421875f, 1.410156250f },\n",
        )

    def test_exports_textured_vertex_data(self):
        from tools.banjo3ds.export_3ds_model import export_textured_vertex_data

        vertices = [
            BanjoVertex(0, 18, 0, 247, 722, 254, 254, 254, 255),
            BanjoVertex(-18, -18, 0, 587, -32, 254, 254, 254, 255),
            BanjoVertex(18, -18, 0, -146, -32, 254, 254, 254, 255),
        ]

        result = export_textured_vertex_data(
            vertices,
            scale_s=0x8000,
            scale_t=0x8000,
            texture_width=8,
            texture_height=8,
        )

        self.assertEqual(
            result,
            (
                "    { 0.0f, 18.0f, 0.0f, 0.482421875f, 1.410156250f },\n"
                "    { -18.0f, -18.0f, 0.0f, 1.146484375f, -0.062500000f },\n"
                "    { 18.0f, -18.0f, 0.0f, -0.285156250f, -0.062500000f },\n"
            ),
        )

    def test_converts_8x8_texture_coordinates_to_3ds_swizzle_index(self):
        from tools.banjo3ds.export_3ds_model import texture_3ds_swizzle_index

        self.assertEqual(texture_3ds_swizzle_index(0, 0), 0)
        self.assertEqual(texture_3ds_swizzle_index(1, 0), 1)
        self.assertEqual(texture_3ds_swizzle_index(0, 1), 2)
        self.assertEqual(texture_3ds_swizzle_index(2, 0), 4)
        self.assertEqual(texture_3ds_swizzle_index(0, 2), 8)
        self.assertEqual(texture_3ds_swizzle_index(7, 7), 63)

    def test_converts_rgba_pixel_to_3ds_rgba8_bytes(self):
        from tools.banjo3ds.export_3ds_model import rgba_pixel_to_3ds_bytes
        from tools.banjo3ds.n64_displaylist_decoder import BanjoPixel

        pixel = BanjoPixel(r=1, g=2, b=3, a=4)

        self.assertEqual(
            rgba_pixel_to_3ds_bytes(pixel),
            bytes([4, 3, 2, 1]),
        )

    def test_encodes_8x8_rgba_texture_for_3ds(self):
        from tools.banjo3ds.export_3ds_model import encode_3ds_rgba8_texture
        from tools.banjo3ds.n64_displaylist_decoder import BanjoPixel, BanjoTexture

        pixels = [
            BanjoPixel(
                r=x * 4,
                g=y * 4,
                b=(y * 8 + x) * 4,
                a=255,
            )
            for y in range(8)
            for x in range(8)
        ]
        texture = BanjoTexture(width=8, height=8, pixels=pixels)

        result = encode_3ds_rgba8_texture(texture)

        self.assertEqual(len(result), 256)
        self.assertEqual(
            result[:32],
            bytes.fromhex(
                "ff000000 ff040004 ff200400 ff240404 "
                "ff080008 ff0c000c ff280408 ff2c040c"
            ),
        )


class TestExport3DSModelCLI(unittest.TestCase):
    def test_writes_exported_model_to_file(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from tools.banjo3ds.export_3ds_model import main

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "generated_model.h"

            result = main([
                "assets/model/08A1.model.bin",
                str(output_path),
            ])

            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())
            self.assertIn(
                "#define BANJO_VERTEX_COUNT 3",
                output_path.read_text(),
            )
