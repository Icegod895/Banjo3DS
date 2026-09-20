import unittest

from tools.banjo3ds.export_3ds_model import export_header, export_vertex_data
from tools.banjo3ds.n64_displaylist_decoder import BanjoMaterial, BanjoPixel, BanjoRenderData, BanjoTexture, BanjoTextureLoad, BanjoVertex


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
                "    { 0.0f, 18.0f, 0.0f, 254, 254, 254, 255 },\n"
                "    { -18.0f, -18.0f, 0.0f, 254, 254, 254, 255 },\n"
                "    { 18.0f, -18.0f, 0.0f, 254, 254, 254, 255 },\n"
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
            "    unsigned char r;\n"
            "    unsigned char g;\n"
            "    unsigned char b;\n"
            "    unsigned char a;\n",
            result,
        )
        self.assertIn(
            "    { 0.0f, 18.0f, 0.0f, 254, 254, 254, 255 },",
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
                "    { 30.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
                "    { 10.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
                "    { 20.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
            ),
        )

    def test_uses_triangle_material_texture(self):
        from tools.banjo3ds.export_3ds_model import export_triangle_vertices
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoMaterial,
            BanjoPixel,
            BanjoRenderData,
            BanjoTexture,
            BanjoTextureLoad,
            BanjoTriangle,
        )

        vertices = [
            BanjoVertex(0, 0, 0, 32, 64, 255, 255, 255, 255),
            BanjoVertex(1, 0, 0, 32, 64, 255, 255, 255, 255),
            BanjoVertex(0, 1, 0, 32, 64, 255, 255, 255, 255),
        ]
        textures = [
            BanjoTexture(0, 4, 4, [BanjoPixel(0, 0, 0, 255)] * 16),
            BanjoTexture(1, 8, 8, [BanjoPixel(0, 0, 0, 255)] * 64),
        ]
        texture_loads = [
            BanjoTextureLoad(0, "RGBA32", 4, 4, None, 0, 7, 0x8000, 0x8000),
            BanjoTextureLoad(1, "RGBA32", 8, 8, None, 0, 7, 0x8000, 0x8000),
        ]
        render_data = BanjoRenderData(
            vertices=vertices,
            triangles=[BanjoTriangle(0, 1, 2, material_index=0)],
            textures=textures,
            texture_loads=texture_loads,
            materials=[BanjoMaterial(texture_load_index=1)],
        )
        result = export_triangle_vertices(render_data)

        self.assertIn(
        "{ 0.0f, 0.0f, 0.0f, 0.062500000f, 0.875000000f, 255, 255, 255, 255 }",
            result,
        )

    def test_exports_texture_fields_for_material_bound_triangle(self):
        from tools.banjo3ds.export_3ds_model import export_header
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoMaterial,
            BanjoPixel,
            BanjoRenderData,
            BanjoTexture,
            BanjoTextureLoad,
            BanjoTriangle,
        )

        vertices = [
            BanjoVertex(0, 0, 0, 32, 64, 255, 255, 255, 255),
            BanjoVertex(1, 0, 0, 32, 64, 255, 255, 255, 255),
            BanjoVertex(0, 1, 0, 32, 64, 255, 255, 255, 255),
        ]
        textures = [
            BanjoTexture(0, 8, 8, [BanjoPixel(0, 0, 0, 255)] * 64),
            BanjoTexture(1, 8, 8, [BanjoPixel(0, 0, 0, 255)] * 64),
        ]
        texture_loads = [
            BanjoTextureLoad(0, "RGBA32", 4, 4, None, 0, 7, 0x8000, 0x8000),
            BanjoTextureLoad(1, "RGBA32", 8, 8, None, 0, 7, 0x8000, 0x8000),
        ]
        render_data = BanjoRenderData(
            vertices=vertices,
            triangles=[BanjoTriangle(0, 1, 2, material_index=0)],
            textures=textures,
            texture_loads=texture_loads,
            materials=[BanjoMaterial(texture_load_index=1)],
        )

        result = export_header(render_data)

        self.assertIn("    float u;\n", result)
        self.assertIn("    float v;\n", result)

    def test_exports_draw_for_triangle_material(self):
        from tools.banjo3ds.export_3ds_model import export_header
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoMaterial,
            BanjoPixel,
            BanjoRenderData,
            BanjoTexture,
            BanjoTriangle,
            BanjoTextureLoad,
        )

        render_data = BanjoRenderData(
            vertices=[
                BanjoVertex(0, 0, 0, 0, 0, 255, 255, 255, 255),
                BanjoVertex(1, 0, 0, 0, 0, 255, 255, 255, 255),
                BanjoVertex(0, 1, 0, 0, 0, 255, 255, 255, 255),
            ],
            triangles=[BanjoTriangle(0, 1, 2, material_index=0)],
            textures=[
                BanjoTexture(
                    texture_index=0,
                    width=8,
                    height=8,
                    pixels=[BanjoPixel(255, 255, 255, 255)] * 64,
                ),
            ],
            texture_loads=[
                BanjoTextureLoad(0, "RGBA32", 8, 8, None, 0, 7, 0x8000, 0x8000),
            ],
            materials=[BanjoMaterial(texture_load_index=0)],
        )

        result = export_header(render_data)

        self.assertIn(
            "    { 0, 3, 0 },\n",
            result,
        )

        self.assertIn("#define BANJO_DRAW_COUNT 1", result)

    def test_exports_multiple_texture_arrays(self):
        from tools.banjo3ds.export_3ds_model import export_header
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoPixel,
            BanjoRenderData,
            BanjoTexture,
        )

        textures = [
            BanjoTexture(
                texture_index=0,
                width=8,
                height=8,
                pixels=[BanjoPixel(255, 0, 0, 255)] * 64,
            ),
            BanjoTexture(
                texture_index=1,
                width=8,
                height=8,
                pixels=[BanjoPixel(0, 255, 0, 255)] * 64,
            ),
        ]
        render_data = BanjoRenderData(
            vertices=[],
            triangles=[],
            textures=textures,
            texture_loads=[],
        )

        result = export_header(render_data)

        self.assertIn(
            "static const unsigned char banjo_texture_0[] = {",
            result,
        )
        self.assertIn(
            "static const unsigned char banjo_texture_1[] = {",
            result,
        )
        self.assertIn(
            "typedef struct {\n"
            "    unsigned int width;\n"
            "    unsigned int height;\n"
            "    const unsigned char *data;\n"
            "} Banjo3DSTexture;\n",
            result,
        )
        self.assertIn(
            "    { 8, 8, banjo_texture_0 },\n"
            "    { 8, 8, banjo_texture_1 },\n",
            result,
        )

    def test_exports_material_texture_slot(self):
        textures = [
            BanjoTexture(
                texture_index=7,
                width=8,
                height=8,
                pixels=[BanjoPixel(255, 0, 0, 255)] * 64,
            ),
            BanjoTexture(
                texture_index=42,
                width=8,
                height=8,
                pixels=[BanjoPixel(0, 255, 0, 255)] * 64,
            ),
        ]
        texture_loads = [
            BanjoTextureLoad(
                texture_index=42,
                texture_type="RGBA32",
                width=8,
                height=8,
                palette_offset=None,
                texel_offset=0,
                load_tile=7,
                scale_s=1.0,
                scale_t=1.0,
            ),
        ]
        materials = [
            BanjoMaterial(texture_load_index=0),
        ]

        render_data = BanjoRenderData(
            vertices=[],
            triangles=[],
            textures=textures,
            texture_loads=texture_loads,
            materials=materials,
        )

        result = export_header(render_data)

        self.assertIn(
            "typedef struct {\n"
            "    unsigned int texture_slot;\n"
            "} Banjo3DSMaterial;\n",
            result,
        )
        self.assertIn(
            "    { 1 },\n",
            result,
        )
        self.assertIn("#define BANJO_MATERIAL_COUNT 1", result)


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
            "    { 0.0f, 18.0f, 0.0f, 0.482421875f, -0.410156250f, 254, 254, 254, 255 },",
            result,
        )
        self.assertIn(
            "    { -18.0f, -18.0f, 0.0f, 1.146484375f, 1.062500000f, 254, 254, 254, 255 },",
            result,
        )
        self.assertIn(
            "    { 18.0f, -18.0f, 0.0f, -0.285156250f, 1.062500000f, 254, 254, 254, 255 },",
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

        self.assertIn(
            "static const unsigned char banjo_texture_0[] = {",
            result,
        )
        self.assertIn(
            "    { 8, 8, banjo_texture_0 },",
            result,
        )
        self.assertIn("#define BANJO_TEXTURE_COUNT 1", result)

    def test_exports_real_08a1_sampler_state(self):
        from pathlib import Path
        from tools.banjo3ds.export_3ds_model import export_model

        result = export_model(Path("assets/model/08A1.model.bin"))

        self.assertIn(
            "#define BANJO_TEXTURE_WRAP_S BANJO_TEXTURE_WRAP_CLAMP",
            result,
        )
        self.assertIn(
            "#define BANJO_TEXTURE_WRAP_T BANJO_TEXTURE_WRAP_CLAMP",
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
        "    { 0.0f, 18.0f, 0.0f, 0.482421875f, -0.410156250f, 254, 254, 254, 255 },\n",
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
                "    { 0.0f, 18.0f, 0.0f, 0.482421875f, -0.410156250f, 254, 254, 254, 255 },\n"
                "    { -18.0f, -18.0f, 0.0f, 1.146484375f, 1.062500000f, 254, 254, 254, 255 },\n"
                "    { 18.0f, -18.0f, 0.0f, -0.285156250f, 1.062500000f, 254, 254, 254, 255 },\n"
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
        texture = BanjoTexture(
            texture_index=0,
            width=8,
            height=8,
            pixels=pixels,
        )

        result = encode_3ds_rgba8_texture(texture)

        self.assertEqual(len(result), 256)
        self.assertEqual(
            result[:32],
            bytes.fromhex(
                "ff000000 ff040004 ff200400 ff240404 "
                "ff080008 ff0c000c ff280408 ff2c040c"
            ),
        )

    def test_encodes_16x8_rgba_texture_as_two_3ds_tiles(self):
        from tools.banjo3ds.export_3ds_model import encode_3ds_rgba8_texture
        from tools.banjo3ds.n64_displaylist_decoder import BanjoPixel, BanjoTexture

        pixels = [
            BanjoPixel(
                r=255 if x < 8 else 0,
                g=0 if x < 8 else 255,
                b=0,
                a=255,
            )
            for y in range(8)
            for x in range(16)
        ]
        texture = BanjoTexture(
            texture_index=0,
            width=16,
            height=8,
            pixels=pixels,
        )

        result = encode_3ds_rgba8_texture(texture)

        self.assertEqual(len(result), 16 * 8 * 4)
        self.assertEqual(
            result[:8 * 8 * 4],
            bytes([255, 0, 0, 255]) * (8 * 8),
        )
        self.assertEqual(
            result[8 * 8 * 4:],
            bytes([255, 0, 255, 0]) * (8 * 8),
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
