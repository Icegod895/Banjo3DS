def s10_5_to_texel(value):
    return value / 32.0


def apply_texture_scale(texel_coordinate, scale):
    return texel_coordinate * (scale / 65536.0)


def normalize_texel_coordinate(texel_coordinate, texture_size):
    return texel_coordinate / texture_size


def clamp_texel_coordinate(texel_coordinate, texture_size):
    return min(max(texel_coordinate, 0.0), texture_size - 1.0)


def n64_texture_coordinate_to_uv(value, scale, texture_size):
    texel_coordinate = s10_5_to_texel(value)
    scaled_coordinate = apply_texture_scale(texel_coordinate, scale)
    return normalize_texel_coordinate(scaled_coordinate, texture_size)


def export_textured_vertex(
    vertex,
    scale_s,
    scale_t,
    texture_width,
    texture_height,
):
    u = n64_texture_coordinate_to_uv(vertex.s, scale_s, texture_width)
    v = n64_texture_coordinate_to_uv(vertex.t, scale_t, texture_height)

    return (
        f"    {{ {float(vertex.x):.1f}f, "
        f"{float(vertex.y):.1f}f, "
        f"{float(vertex.z):.1f}f, "
        f"{u:.9f}f, "
        f"{v:.9f}f }},\n"
    )

def texture_3ds_swizzle_index(x, y):
    return (
        ((x >> 0) & 1) << 0
        | ((y >> 0) & 1) << 1
        | ((x >> 1) & 1) << 2
        | ((y >> 1) & 1) << 3
        | ((x >> 2) & 1) << 4
        | ((y >> 2) & 1) << 5
    )

def rgba_pixel_to_3ds_bytes(pixel):
    return bytes([
        pixel.a,
        pixel.b,
        pixel.g,
        pixel.r,
    ])

def encode_3ds_rgba8_texture(texture):
    if texture.width != 8 or texture.height != 8:
        raise ValueError("Only 8x8 RGBA8 textures are supported")

    result = bytearray(8 * 8 * 4)

    for y in range(8):
        for x in range(8):
            source_index = y * 8 + x
            destination_index = texture_3ds_swizzle_index(x, y)

            pixel = texture.pixels[source_index]
            pixel_bytes = rgba_pixel_to_3ds_bytes(pixel)

            offset = destination_index * 4
            result[offset:offset + 4] = pixel_bytes

    return bytes(result)


def export_3ds_texture_data(texture):
    data = encode_3ds_rgba8_texture(texture)
    lines = []

    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        values = ", ".join(f"0x{value:02X}" for value in chunk)
        lines.append(f"    {values},\n")

    return "".join(lines)


def export_textured_vertex_data(
    vertices,
    scale_s,
    scale_t,
    texture_width,
    texture_height,
):
    return "".join(
        export_textured_vertex(
            vertex,
            scale_s,
            scale_t,
            texture_width,
            texture_height,
        )
        for vertex in vertices
    )

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
    texture_fields = ""
    texture_data = ""

    if len(render_data.texture_loads) == 1 and len(render_data.textures) == 1:
        texture = render_data.textures[0]
        texture_bytes = export_3ds_texture_data(texture)

        texture_data = (
            f"#define BANJO_TEXTURE_WIDTH {texture.width}\n"
            f"#define BANJO_TEXTURE_HEIGHT {texture.height}\n"
            "\n"
            "static const unsigned char banjo_texture[] = {\n"
            f"{texture_bytes}"
            "};\n"
            "\n"
        )

    if len(render_data.texture_loads) == 1 and len(render_data.textures) == 1:
        texture_fields = (
            "    float u;\n"
            "    float v;\n"
        )

    return (
        "#pragma once\n"
        "\n"
        "typedef struct {\n"
        "    float x;\n"
        "    float y;\n"
        "    float z;\n"
        f"{texture_fields}"
        "} Banjo3DSVertex;\n"
        "\n"
        "static const Banjo3DSVertex banjo_vertices[] = {\n"
        f"{vertex_data}"
        "};\n"
        "\n"
        f"#define BANJO_VERTEX_COUNT {vertex_count}\n"
        "\n"
        f"{texture_data}"
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

    if len(render_data.texture_loads) == 1 and len(render_data.textures) == 1:
        texture_load = render_data.texture_loads[0]
        texture = render_data.textures[0]

        return export_textured_vertex_data(
            vertices,
            scale_s=texture_load.scale_s,
            scale_t=texture_load.scale_t,
            texture_width=texture.width,
            texture_height=texture.height,
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
