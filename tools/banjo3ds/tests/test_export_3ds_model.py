import unittest

from tools.banjo3ds.export_3ds_model import export_header, export_vertex_data
from tools.banjo3ds.n64_displaylist_decoder import BanjoCombine, BanjoMaterial, BanjoPixel, BanjoRenderData, BanjoTexture, BanjoTextureLoad, BanjoVertex


class TestExport3DSModel(unittest.TestCase):
    def test_culling_batch_boundaries_and_round_trip(self):
        from dataclasses import replace
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle, BanjoCullMode as C
        base = BanjoTriangle(0, 1, 2)
        states = [C.BACK, C.BACK, C.NONE, C.FRONT, C.BOTH, C.BACK]
        batches = build_draw_batches([replace(base, cull_mode=c) for c in states])
        self.assertEqual([(b[0], b[1]) for b in batches],
                         [(0, 6), (6, 3), (9, 3), (12, 3), (15, 3)])
        self.assertEqual([b[-1] for b in batches for _ in range(b[1] // 3)], states)

    def test_batches_adjacent_compatible_triangles(self):
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle

        triangles = [BanjoTriangle(0, 1, 2, 0, None, 1)] * 2
        self.assertEqual(build_draw_batches(triangles), [(0, 6, 0, 1, (0,) * 16, 0)])

    def test_batch_state_boundaries(self):
        from dataclasses import replace
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle

        combine = BanjoCombine(*range(16))
        first = BanjoTriangle(0, 1, 2, 0, combine, 1)
        variants = [replace(first, material_index=1), replace(first, render_mode_index=2)]
        # Every exported selector must participate, not just the RGB selectors.
        for field in combine.__dataclass_fields__:
            variants.append(replace(first, combine=replace(combine, **{field: 99})))
        for second in variants:
            with self.subTest(second=second):
                batches = build_draw_batches([first, second, first])
                self.assertEqual([(b[0], b[1]) for b in batches], [(0, 3), (3, 3), (6, 3)])
                self.assertEqual(batches[0][2:], batches[2][2:])
                self.assertNotEqual(batches[0][2:], batches[1][2:])

    def test_batch_ranges_and_state_round_trip(self):
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle

        a = BanjoTriangle(2, 0, 1, 0, BanjoCombine(*range(16)), 1)
        b = BanjoTriangle(1, 2, 0, 1, None, 2)
        triangles = [a, a, b, b, b, a]
        batches = build_draw_batches(triangles)
        self.assertEqual([(b[0], b[1]) for b in batches], [(0, 6), (6, 9), (15, 3)])
        expanded = []
        end = 0
        for first, count, material, mode, combine, cull in batches:
            self.assertEqual(first, end)
            self.assertEqual(count % 3, 0)
            expanded.extend((i, material, mode, combine, cull) for i in range(first, first + count, 3))
            end = first + count
        expected = [(i * 3, t.material_index, t.render_mode_index,
                     tuple(range(16)) if t is a else (0,) * 16, t.cull_mode)
                    for i, t in enumerate(triangles)]
        self.assertEqual(expanded, expected)
        self.assertEqual(end, 3 * len(triangles))

    def test_empty_and_normalized_combine_batches(self):
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle

        self.assertEqual(build_draw_batches([]), [])
        triangles = [BanjoTriangle(0, 1, 2), BanjoTriangle(0, 1, 2, combine=BanjoCombine(*([0] * 16)))]
        self.assertEqual(build_draw_batches(triangles), [(0, 6, -1, -1, (0,) * 16, 0)])
        data = BanjoRenderData(
            vertices=[BanjoVertex(0, 0, 0, 0, 0, 255, 255, 255, 255)] * 3,
            triangles=triangles, textures=[], texture_loads=[],
        )
        header = export_header(data)
        self.assertIn("#define BANJO_DRAW_COUNT 1", header)
        self.assertIn("    { 0, 6, -1, -1, 0, {", header)
        self.assertIn("#define BANJO_VERTEX_COUNT 6", header)

    def test_real_14cf_batches_preserve_triangle_state(self):
        from dataclasses import astuple
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        from tools.banjo3ds.n64_displaylist_decoder import BKModel, interpret_display_list

        data = interpret_display_list(BKModel("assets/model/14CF.model.bin"))
        batches = build_draw_batches(data.triangles)
        self.assertEqual(len(data.triangles), 3136)
        self.assertEqual(len(data.materials), 417)
        self.assertEqual(len(data.textures), 77)
        self.assertEqual(len(batches), 436)
        self.assertEqual(max(b[1] for b in batches), 576)
        self.assertEqual(sum(b[1] for b in batches), 9408)
        expanded = [(vertex // 3, material, mode, combine, cull)
                    for first, count, material, mode, combine, cull in batches
                    for vertex in range(first, first + count, 3)]
        expected = [(i, t.material_index if t.material_index is not None else -1,
                     t.render_mode_index if t.render_mode_index is not None else -1,
                     astuple(t.combine) if t.combine is not None else (0,) * 16, t.cull_mode)
                    for i, t in enumerate(data.triangles)]
        self.assertEqual(expanded, expected)

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
                "    { 0.0f, 18.0f, 0.0f, 0.0f, 0.0f, 254, 254, 254, 255 },\n"
                "    { -18.0f, -18.0f, 0.0f, 0.0f, 0.0f, 254, 254, 254, 255 },\n"
                "    { 18.0f, -18.0f, 0.0f, 0.0f, 0.0f, 254, 254, 254, 255 },\n"
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
            "    { 0.0f, 18.0f, 0.0f, 0.0f, 0.0f, 254, 254, 254, 255 },",
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
                "    { 30.0f, 0.0f, 0.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
                "    { 10.0f, 0.0f, 0.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
                "    { 20.0f, 0.0f, 0.0f, 0.0f, 0.0f, 255, 255, 255, 255 },\n"
            ),
        )

    def test_exports_draw_for_untextured_triangle(self):
        from tools.banjo3ds.export_3ds_model import export_header
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoRenderData,
            BanjoTriangle,
        )

        vertices = [
            BanjoVertex(0, 0, 0, 0, 0, 255, 255, 255, 255),
            BanjoVertex(1, 0, 0, 0, 0, 255, 255, 255, 255),
            BanjoVertex(0, 1, 0, 0, 0, 255, 255, 255, 255),
        ]
        render_data = BanjoRenderData(
            vertices=vertices,
            triangles=[BanjoTriangle(0, 1, 2)],
            textures=[],
            texture_loads=[],
        )

        result = export_header(render_data)

        self.assertIn(
            "    { 0, 3, -1, -1, 0, { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 } },",
            result,
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
            triangles=[
                BanjoTriangle(
                    0,
                    1,
                    2,
                    material_index=0,
                    render_mode_index=2,
                    combine=BanjoCombine(
                        1, 3, 5, 3,
                        1, 7, 4, 7,
                        0, 15, 4, 7,
                        0, 7, 5, 7,
                    ),
                ),
            ],
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
            "    { 0, 3, 0, 2, 0, { 1, 3, 5, 3, 1, 7, 4, 7, 0, 15, 4, 7, 0, 7, 5, 7 } },\n",
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
            "    unsigned int mipmap_count;\n"
            "    const unsigned char *data;\n"
            "    const unsigned char *const *mipmaps;\n"
            "} Banjo3DSTexture;\n",
            result,
        )
        self.assertIn(
            "    { 8, 8, 0, banjo_texture_0, 0 },\n"
            "    { 8, 8, 0, banjo_texture_1, 0 },\n",
            result,
        )

    def test_exports_texture_mipmap_arrays(self):
        from tools.banjo3ds.export_3ds_model import export_header
        from tools.banjo3ds.n64_displaylist_decoder import (
            BanjoPixel,
            BanjoRenderData,
            BanjoTexture,
        )

        texture = BanjoTexture(
            texture_index=0,
            width=32,
            height=32,
            pixels=[BanjoPixel(255, 0, 0, 255)] * (32 * 32),
            mipmaps=[
                [BanjoPixel(0, 255, 0, 255)] * (16 * 16),
                [BanjoPixel(0, 0, 255, 255)] * (8 * 8),
            ],
        )
        render_data = BanjoRenderData(
            vertices=[],
            triangles=[],
            textures=[texture],
            texture_loads=[],
        )

        result = export_header(render_data)

        self.assertIn(
            "static const unsigned char banjo_texture_0[] = {",
            result,
        )
        self.assertIn(
            "static const unsigned char banjo_texture_0_mip_1[] = {",
            result,
        )
        self.assertIn(
            "static const unsigned char banjo_texture_0_mip_2[] = {",
            result,
        )
        self.assertIn(
            "static const unsigned char *const "
            "banjo_texture_0_mipmaps[] = {\n"
            "    banjo_texture_0_mip_1,\n"
            "    banjo_texture_0_mip_2,\n"
            "};\n",
            result,
        )
        self.assertIn(
            "typedef struct {\n"
            "    unsigned int width;\n"
            "    unsigned int height;\n"
            "    unsigned int mipmap_count;\n"
            "    const unsigned char *data;\n"
            "    const unsigned char *const *mipmaps;\n"
            "} Banjo3DSTexture;\n",
            result,
        )
        self.assertIn(
            "    { 32, 32, 2, banjo_texture_0, "
            "banjo_texture_0_mipmaps },\n",
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
            "    { 8, 8, 0, banjo_texture_0, 0 },",
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


class TestCombinedPassExport(unittest.TestCase):
    def test_real_spiral_mountain_offsets_and_passes(self):
        import re
        from dataclasses import astuple
        from tools.banjo3ds.export_3ds_model import (
            combine_render_passes, build_draw_batches, export_triangle_vertices,
            find_texture_slot_for_load,
        )
        from tools.banjo3ds.n64_displaylist_decoder import BKModel, interpret_display_list

        opa = interpret_display_list(BKModel("assets/model/14CF.model.bin"))
        xlu = interpret_display_list(BKModel("assets/model/14D0.model.bin"))
        data, boundary = combine_render_passes(opa, xlu)
        self.assertEqual(boundary, 3136)
        self.assertEqual(len(data.textures), 86)
        self.assertEqual(len(data.materials), 453)
        self.assertEqual(len(data.triangles) * 3, 10515)
        self.assertEqual(export_triangle_vertices(data),
                         export_triangle_vertices(opa) + export_triangle_vertices(xlu))
        for source, vo, mo, lo, to in (
            (opa, 0, 0, 0, 0),
            (xlu, len(opa.vertices), len(opa.materials), len(opa.texture_loads), 77),
        ):
            start = 0 if source is opa else boundary
            for original, merged in zip(source.triangles, data.triangles[start:]):
                self.assertEqual((merged.v0, merged.v1, merged.v2),
                                 (original.v0 + vo, original.v1 + vo, original.v2 + vo))
                self.assertEqual(merged.material_index, original.material_index + mo)
                self.assertEqual(merged.combine, original.combine)
                self.assertEqual(merged.cull_mode, original.cull_mode)
                self.assertEqual(merged.render_mode_index, original.render_mode_index)
            for i, material in enumerate(source.materials):
                merged = data.materials[mo + i]
                self.assertEqual(merged.texture_load_index, material.texture_load_index + lo)
                original_slot = find_texture_slot_for_load(source, source.texture_loads[material.texture_load_index])
                merged_slot = find_texture_slot_for_load(data, data.texture_loads[merged.texture_load_index])
                self.assertEqual(merged_slot, original_slot + to)
            for i, texture in enumerate(source.textures):
                merged = data.textures[to + i]
                self.assertEqual(merged.texture_index, to + i)
                self.assertEqual(merged.pixels, texture.pixels)
                self.assertEqual(merged.mipmaps, texture.mipmaps)

        header = export_header(data, boundary)
        for name, count in [('VERTEX', 10515), ('TEXTURE', 86), ('MATERIAL', 453),
                            ('DRAW', 482), ('OPA_DRAW', 436), ('XLU_DRAW', 46)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {count}\n', header)
        draw_text = header.split('static const Banjo3DSDraw banjo_draws[] = {')[1].split('};')[0]
        rows = [tuple(map(int, re.findall(r'-?\d+', line)))
                for line in draw_text.splitlines() if '{' in line]
        expected = [(first, count, material, mode, int(cull), *combine)
                    for first, count, material, mode, combine, cull in build_draw_batches(opa.triangles)]
        expected += [(first + 9408, count, material + 417, mode, int(cull), *combine)
                     for first, count, material, mode, combine, cull in build_draw_batches(xlu.triangles)]
        self.assertEqual(rows, expected)
        self.assertEqual(rows[436][0], 9408)
        self.assertEqual(sum(row[1] for row in rows), 10515)
        self.assertEqual(rows[-1][0] + rows[-1][1], 10515)

    def test_pass_boundary_prevents_cross_pass_batching(self):
        from tools.banjo3ds.n64_displaylist_decoder import BanjoTriangle
        data = BanjoRenderData(
            [BanjoVertex(0, 0, 0, 0, 0, 255, 255, 255, 255)] * 3,
            [BanjoTriangle(0, 1, 2)] * 2, [], [],
        )
        header = export_header(data, 1)
        self.assertIn('#define BANJO_DRAW_COUNT 2\n', header)
        self.assertIn('#define BANJO_OPA_DRAW_COUNT 1\n', header)
        self.assertIn('#define BANJO_XLU_DRAW_COUNT 1\n', header)
        self.assertIn('    { 0, 3, -1, -1, 0, {', header)
        self.assertIn('    { 3, 3, -1, -1, 0, {', header)
        single = export_header(data)
        self.assertIn('#define BANJO_OPA_DRAW_COUNT 1\n', single)
        self.assertIn('#define BANJO_XLU_DRAW_COUNT 0\n', single)

    def test_rejects_incompatible_global_samplers(self):
        from tools.banjo3ds.export_3ds_model import combine_render_passes
        from tools.banjo3ds.n64_displaylist_decoder import BanjoSampler
        opa = BanjoRenderData([], [], [], [], sampler=BanjoSampler('wrap', 'wrap'))
        xlu = BanjoRenderData([], [], [], [], sampler=BanjoSampler('clamp', 'wrap'))
        with self.assertRaisesRegex(ValueError, 'sampler'):
            combine_render_passes(opa, xlu)
