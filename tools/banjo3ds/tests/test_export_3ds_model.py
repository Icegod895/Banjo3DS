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
            "    { 0.0f, 18.0f, 0.0f },",
            result,
        )
        self.assertIn(
            "    { -18.0f, -18.0f, 0.0f },",
            result,
        )
        self.assertIn(
            "    { 18.0f, -18.0f, 0.0f },",
            result,
        )
        self.assertIn(
            "#define BANJO_VERTEX_COUNT 3",
            result,
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
