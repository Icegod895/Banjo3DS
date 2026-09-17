def export_vertex_data(vertices):
    return "".join(
        f"    {{ {float(vertex.x):.1f}f, "
        f"{float(vertex.y):.1f}f, "
        f"{float(vertex.z):.1f}f }},\n"
        for vertex in vertices
    )


def export_header(render_data):
    vertex_data = export_triangle_vertices(render_data)
    vertex_count = len(render_data.triangles) * 3

    return (
        "#pragma once\n"
        "\n"
        "typedef struct {\n"
        "    float x;\n"
        "    float y;\n"
        "    float z;\n"
        "} Banjo3DSVertex;\n"
        "\n"
        "static const Banjo3DSVertex banjo_vertices[] = {\n"
        f"{vertex_data}"
        "};\n"
        "\n"
        f"#define BANJO_VERTEX_COUNT {vertex_count}\n"
    )


def export_triangle_vertices(render_data):
    vertices = []

    for triangle in render_data.triangles:
        vertices.extend(
            [
                render_data.vertices[triangle.v0],
                render_data.vertices[triangle.v1],
                render_data.vertices[triangle.v2],
            ]
        )

    return export_vertex_data(vertices)


def export_model(model_path):
    from tools.banjo3ds.n64_displaylist_decoder import (
        BKModel,
        interpret_display_list,
    )

    model = BKModel(model_path)
    render_data = interpret_display_list(model)

    return export_header(render_data)


def main(argv):
    from pathlib import Path

    if len(argv) != 2:
        raise SystemExit("usage: export_3ds_model.py MODEL OUTPUT")

    model_path = Path(argv[0])
    output_path = Path(argv[1])

    output_path.write_text(export_model(model_path))

    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
