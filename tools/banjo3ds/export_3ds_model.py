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


def texture_wrap_to_c_constant(wrap):
    return {
        "wrap": "BANJO_TEXTURE_WRAP_WRAP",
        "mirror": "BANJO_TEXTURE_WRAP_MIRROR",
        "clamp": "BANJO_TEXTURE_WRAP_CLAMP",
        "mirror_clamp": "BANJO_TEXTURE_WRAP_MIRROR_CLAMP",
    }[wrap]


def export_textured_vertex(
    vertex,
    scale_s,
    scale_t,
    texture_width,
    texture_height,
):
    u = n64_texture_coordinate_to_uv(vertex.s, scale_s, texture_width)
    v = 1.0 - n64_texture_coordinate_to_uv(vertex.t, scale_t, texture_height)

    return (
        f"    {{ {float(vertex.x):.1f}f, "
        f"{float(vertex.y):.1f}f, "
        f"{float(vertex.z):.1f}f, "
        f"{u:.9f}f, "
        f"{v:.9f}f, {vertex.r}, {vertex.g}, {vertex.b}, {vertex.a} }},\n"
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
    if texture.width % 8 != 0 or texture.height % 8 != 0:
        raise ValueError("RGBA8 texture dimensions must be multiples of 8")

    result = bytearray(texture.width * texture.height * 4)
    tiles_per_row = texture.width // 8

    for y in range(texture.height):
        for x in range(texture.width):
            source_index = y * texture.width + x

            tile_x = x // 8
            tile_y = y // 8
            tile_index = tile_y * tiles_per_row + tile_x

            local_x = x % 8
            local_y = y % 8
            swizzle_index = texture_3ds_swizzle_index(local_x, local_y)
            destination_index = tile_index * 64 + swizzle_index

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
        f"{float(vertex.z):.1f}f, {vertex.r}, {vertex.g}, {vertex.b}, {vertex.a} }},\n"
        for vertex in vertices
    )


def export_header(render_data):
    vertex_data = export_triangle_vertices(render_data)
    vertex_count = len(render_data.triangles) * 3
    texture_fields = ""
    texture_data = ""
    material_data = ""
    sampler_data = ""
    draw_data = ""

    if render_data.sampler is not None:
        wrap_s = texture_wrap_to_c_constant(render_data.sampler.wrap_s)
        wrap_t = texture_wrap_to_c_constant(render_data.sampler.wrap_t)

        sampler_data = (
            "#define BANJO_TEXTURE_WRAP_WRAP 0\n"
            "#define BANJO_TEXTURE_WRAP_MIRROR 1\n"
            "#define BANJO_TEXTURE_WRAP_CLAMP 2\n"
            "#define BANJO_TEXTURE_WRAP_MIRROR_CLAMP 3\n"
            f"#define BANJO_TEXTURE_WRAP_S {wrap_s}\n"
            f"#define BANJO_TEXTURE_WRAP_T {wrap_t}\n"
            "\n"
        )

    for texture_slot, texture in enumerate(render_data.textures):
        texture_bytes = export_3ds_texture_data(texture)

        texture_data += (
            f"static const unsigned char banjo_texture_{texture_slot}[] = {{\n"
            f"{texture_bytes}"
            "};\n"
            "\n"
        )

    if render_data.textures:
        texture_descriptors = "".join(
            f"    {{ {texture.width}, {texture.height}, banjo_texture_{texture_slot} }},\n"
            for texture_slot, texture in enumerate(render_data.textures)
        )

        texture_data += (
            "typedef struct {\n"
            "    unsigned int width;\n"
            "    unsigned int height;\n"
            "    const unsigned char *data;\n"
            "} Banjo3DSTexture;\n"
            "\n"
            "static const Banjo3DSTexture banjo_textures[] = {\n"
            f"{texture_descriptors}"
            "};\n"
            "\n"
            f"#define BANJO_TEXTURE_COUNT {len(render_data.textures)}\n"
            "\n"
        )

    material_texture_slots = []

    for material in render_data.materials:
        texture_load = render_data.texture_loads[material.texture_load_index]
        texture_slot = find_texture_slot_for_load(render_data, texture_load)
        if texture_slot is None:
            raise ValueError("Material references a texture that was not exported")
        material_texture_slots.append(texture_slot)

    if material_texture_slots:
        material_descriptors = "".join(
            f"    {{ {texture_slot} }},\n"
            for texture_slot in material_texture_slots
        )
        material_data = (
            "typedef struct {\n"
            "    unsigned int texture_slot;\n"
            "} Banjo3DSMaterial;\n"
            "\n"
            "static const Banjo3DSMaterial banjo_materials[] = {\n"
            f"{material_descriptors}"
            "};\n"
            "\n"
            f"#define BANJO_MATERIAL_COUNT {len(material_texture_slots)}\n"
            "\n"
        )

    has_textured_triangle = any(
        triangle.material_index is not None
        for triangle in render_data.triangles
    )

    if has_textured_triangle:
        texture_fields = (
            "    float u;\n"
            "    float v;\n"
        )
    draws = "".join(
        f"    {{ {triangle_index * 3}, 3, {triangle.material_index} }},\n"
        for triangle_index, triangle in enumerate(render_data.triangles)
        if triangle.material_index is not None
    )

    draw_count = sum(
        1
        for triangle in render_data.triangles
        if triangle.material_index is not None
    )

    if draws:
        draw_data = (
            "typedef struct {\n"
            "    unsigned int first_vertex;\n"
            "    unsigned int vertex_count;\n"
            "    unsigned int material_index;\n"
            "} Banjo3DSDraw;\n"
            "\n"
            "static const Banjo3DSDraw banjo_draws[] = {\n"
            f"{draws}"
            "};\n"
            "\n"
            f"#define BANJO_DRAW_COUNT {draw_count}\n"
            "\n"
        )

    return (
        "#pragma once\n"
        "\n"
        "typedef struct {\n"
        "    float x;\n"
        "    float y;\n"
        "    float z;\n"
        f"{texture_fields}"
        "    unsigned char r;\n"
        "    unsigned char g;\n"
        "    unsigned char b;\n"
        "    unsigned char a;\n"
        "} Banjo3DSVertex;\n"
        "\n"
        "static const Banjo3DSVertex banjo_vertices[] = {\n"
        f"{vertex_data}"
        "};\n"
        "\n"
        f"#define BANJO_VERTEX_COUNT {vertex_count}\n"
        "\n"
        f"{sampler_data}"
        f"{texture_data}"
        f"{material_data}"
        f"{draw_data}"
    )


def find_texture_for_load(render_data, texture_load):
    for texture in render_data.textures:
        if texture.texture_index == texture_load.texture_index:
            return texture

    return None


def find_texture_slot_for_load(render_data, texture_load):
    for texture_slot, texture in enumerate(render_data.textures):
        if texture.texture_index == texture_load.texture_index:
            return texture_slot

    return None


def export_triangle_vertices(render_data):
    output = ""

    for triangle in render_data.triangles:
        vertices = [
            render_data.vertices[triangle.v0],
            render_data.vertices[triangle.v1],
            render_data.vertices[triangle.v2],
        ]

        if triangle.material_index is not None:
            material = render_data.materials[triangle.material_index]
            texture_load = render_data.texture_loads[material.texture_load_index]
            texture = find_texture_for_load(render_data, texture_load)

            if texture is not None:
                output += export_textured_vertex_data(
                    vertices,
                    scale_s=texture_load.scale_s,
                    scale_t=texture_load.scale_t,
                    texture_width=texture.width,
                    texture_height=texture.height,
                )
                continue

        output += export_vertex_data(vertices)

    return output


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
