from dataclasses import dataclass
from pathlib import Path
import struct
import sys


VTX_SIZE = 16
VTX_HEADER_SIZE = 0x18
TEXTURE_INFO_SIZE = 16

TEXTURE_TYPES = {
    0x01: "CI4",
    0x02: "CI8",
    0x04: "RGBA16",
    0x08: "RGBA32",
}


@dataclass
class BanjoTextureLoad:
    texture_index: int
    texture_type: str
    width: int
    height: int
    palette_offset: int | None
    texel_offset: int
    load_tile: int


class BKModel:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()

        # BKModelBin
        self.gfx_offset = struct.unpack_from(">I", self.data, 0x0C)[0]
        self.vtx_offset = struct.unpack_from(">I", self.data, 0x10)[0]

        # BKTextureList
        self.texture_offset = struct.unpack_from(">H", self.data, 0x08)[0]
        self.texture_size = struct.unpack_from(">I", self.data, self.texture_offset)[0]
        self.texture_count = struct.unpack_from(">H", self.data, self.texture_offset + 4)[0]
        self.texture_infos_offset = self.texture_offset + 8

        self.vertex_count = struct.unpack_from(
            ">H", self.data, self.vtx_offset + 0x14
        )[0]

        self.vertices_offset = self.vtx_offset + VTX_HEADER_SIZE

    def read_texture(self, index):
        if not 0 <= index < self.texture_count:
            raise IndexError(f"Texture index out of range: {index}")

        offset = self.texture_infos_offset + index * TEXTURE_INFO_SIZE

        texture_data_offset = struct.unpack_from(">I", self.data, offset)[0]
        texture_type = struct.unpack_from(">H", self.data, offset + 4)[0]
        width = self.data[offset + 8]
        height = self.data[offset + 9]

        bit_depth = {
            0x01: 4,
            0x02: 8,
            0x04: 16,
            0x08: 32,
        }.get(texture_type, 0)

        palette_size = {
            0x01: 32,
            0x02: 512,
            0x04: 0,
            0x08: 0,
        }.get(texture_type, 0)

        texture_size = (
            bit_depth * width * height // 8
            + palette_size
        )

        return {
            "index": index,
            "offset": texture_data_offset,
            "type": texture_type,
            "type_name": TEXTURE_TYPES.get(texture_type, "UNKNOWN"),
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "palette_size": palette_size,
            "size": texture_size,
        }

    def find_texture_containing_offset(self, offset):
        for i in range(self.texture_count):
            texture = self.read_texture(i)
            start = texture["offset"]
            end = start + texture["size"]

            if start <= offset < end:
                return {
                    "texture": texture,
                    "relative_offset": offset - start,
                }

        return None

    def read_vertex(self, index):
        if not 0 <= index < self.vertex_count:
            raise IndexError(f"Vertex index out of range: {index}")

        offset = self.vertices_offset + index * VTX_SIZE

        x, y, z, flag, s, t, r, g, b, a = struct.unpack_from(
            ">hhhHhhBBBB",
            self.data,
            offset,
        )

        return {
            "index": index,
            "x": x,
            "y": y,
            "z": z,
            "s": s,
            "t": t,
            "r": r,
            "g": g,
            "b": b,
            "a": a,
        }


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <model.bin>")
        sys.exit(1)

    model = BKModel(sys.argv[1])

    print(f"Model: {model.path}")
    print(f"Gfx offset:      0x{model.gfx_offset:X}")
    print(f"Vertex list:     0x{model.vtx_offset:X}")
    print(f"Vertex data:     0x{model.vertices_offset:X}")
    print(f"Vertex count:    {model.vertex_count}")
    print(f"Texture list:    0x{model.texture_offset:X}")
    print(f"Texture count:   {model.texture_count}")
    print()

    print("Textures:")
    for i in range(model.texture_count):
        tex = model.read_texture(i)
        print(
            f"  [{i:2}] "
            f"offset=0x{tex['offset']:06X} "
            f"type={tex['type_name']:6} "
            f"{tex['width']:2}x{tex['height']:2} "
            f"size=0x{tex['size']:X}"
        )
    print()

    gfx_size = struct.unpack_from(">I", model.data, model.gfx_offset)[0]
    gfx_start = model.gfx_offset + 8
    gfx_end = gfx_start + gfx_size

    print()
    print(f"Gfx size:        {gfx_size} bytes")
    print(f"Gfx range:       0x{gfx_start:X} - 0x{gfx_end:X}")
    print()

    # Simulate the N64 vertex cache.
    # Each entry contains the actual Vtx index currently occupying that slot.
    vertex_cache = [None] * 32

    # Track the current N64 texture image state set by G_SETTIMG.
    current_texture_image = None

    # Track the palette most recently loaded into TMEM by G_LOADTLUT.
    # This will later let texel loads refer back to their palette source.
    current_palette = None

    # Track the eight N64 tile descriptors configured by G_SETTILE.
    # Later commands such as G_LOADBLOCK and G_SETTILESIZE refer back
    # to these descriptors by tile number.
    tile_state = [None] * 8

    offset = gfx_start

    while offset < gfx_end:
        w0, w1 = struct.unpack_from(">II", model.data, offset)
        opcode = w0 >> 24

        if opcode == 0xFD:
            address = w1

            current_texture_image = {
                "address": address,
                "texture": None,
                "relative_offset": None,
            }

            if (address & 0xFF000000) == 0x02000000:
                texture_offset = address & 0x00FFFFFF
                match = model.find_texture_containing_offset(texture_offset)

                if match is not None:
                    tex = match["texture"]
                    relative_offset = match["relative_offset"]

                    current_texture_image["texture"] = tex
                    current_texture_image["relative_offset"] = relative_offset

                    print(
                        f"0x{offset:08X}: "
                        f"G_SETTIMG "
                        f"address=0x{address:08X} "
                        f"-> Texture[{tex['index']}] "
                        f"{tex['type_name']} "
                        f"{tex['width']}x{tex['height']} "
                        f"+0x{relative_offset:X}"
                    )
                else:
                    print(
                        f"0x{offset:08X}: "
                        f"G_SETTIMG "
                        f"address=0x{address:08X} "
                        f"-> unknown texture offset 0x{texture_offset:X}"
                    )
            else:
                print(
                    f"0x{offset:08X}: "
                    f"G_SETTIMG address=0x{address:08X}"
                )

        elif opcode == 0xF5:
            fmt = (w0 >> 21) & 0x7
            siz = (w0 >> 19) & 0x3
            line = (w0 >> 9) & 0x1FF
            tmem = w0 & 0x1FF

            tile = (w1 >> 24) & 0x7
            palette = (w1 >> 20) & 0xF
            cmt = (w1 >> 18) & 0x3
            maskt = (w1 >> 14) & 0xF
            shiftt = (w1 >> 10) & 0xF
            cms = (w1 >> 8) & 0x3
            masks = (w1 >> 4) & 0xF
            shifts = w1 & 0xF

            tile_state[tile] = {
                "fmt": fmt,
                "siz": siz,
                "line": line,
                "tmem": tmem,
                "palette": palette,
                "cmt": cmt,
                "maskt": maskt,
                "shiftt": shiftt,
                "cms": cms,
                "masks": masks,
                "shifts": shifts,
            }

            format_names = {
                0: "RGBA",
                1: "YUV",
                2: "CI",
                3: "IA",
                4: "I",
            }

            size_names = {
                0: "4b",
                1: "8b",
                2: "16b",
                3: "32b",
            }

            print(
                f"0x{offset:08X}: "
                f"G_SETTILE "
                f"fmt={format_names.get(fmt, str(fmt))} "
                f"siz={size_names.get(siz, str(siz))} "
                f"line={line} "
                f"tmem=0x{tmem:X} "
                f"tile={tile} "
                f"palette={palette} "
                f"cms={cms} masks={masks} shifts={shifts} "
                f"cmt={cmt} maskt={maskt} shiftt={shiftt}"
            )

        elif opcode == 0xF2:
            uls = (w0 >> 12) & 0xFFF
            ult = w0 & 0xFFF
            tile = (w1 >> 24) & 0x7
            lrs = (w1 >> 12) & 0xFFF
            lrt = w1 & 0xFFF

            width = ((lrs - uls) >> 2) + 1
            height = ((lrt - ult) >> 2) + 1

            print(
                f"0x{offset:08X}: "
                f"G_SETTILESIZE "
                f"tile={tile} "
                f"uls={uls} "
                f"ult={ult} "
                f"lrs={lrs} "
                f"lrt={lrt} "
                f"-> {width}x{height}"
            )

        elif opcode == 0xF3:
            uls = (w0 >> 12) & 0xFFF
            ult = w0 & 0xFFF
            tile = (w1 >> 24) & 0x7
            lrs = (w1 >> 12) & 0xFFF
            dxt = w1 & 0xFFF

            load_tile = tile_state[tile]

            if load_tile is not None:
                load_format = {
                    0: "RGBA",
                    1: "YUV",
                    2: "CI",
                    3: "IA",
                    4: "I",
                }.get(load_tile["fmt"], str(load_tile["fmt"]))

                load_size = {
                    0: "4b",
                    1: "8b",
                    2: "16b",
                    3: "32b",
                }.get(load_tile["siz"], str(load_tile["siz"]))

                tile_description = (
                    f"{load_format}/{load_size} "
                    f"tmem=0x{load_tile['tmem']:X}"
                )
            else:
                tile_description = "unknown"

            if current_texture_image is not None:
                load_source = f"0x{current_texture_image['address']:08X}"

                source_texture = current_texture_image["texture"]
                if source_texture is not None:
                    load_source += f" Texture[{source_texture['index']}]"
            else:
                load_source = "unknown"

            if current_palette is not None:
                palette_image = current_palette["image"]
                palette_source = f"0x{palette_image['address']:08X}"

                palette_texture = palette_image["texture"]
                if palette_texture is not None:
                    palette_source += (
                        f" Texture[{palette_texture['index']}]"
                        f"+0x{palette_image['relative_offset']:X}"
                    )
            else:
                palette_source = "none"

            texture_load = None

            if (
                current_texture_image is not None
                and current_texture_image["texture"] is not None
                and current_palette is not None
                and current_palette["image"]["texture"] is not None
                and current_texture_image["texture"]["index"]
                == current_palette["image"]["texture"]["index"]
            ):
                texture = current_texture_image["texture"]

                texture_load = BanjoTextureLoad(
                    texture_index=texture["index"],
                    texture_type=texture["type_name"],
                    width=texture["width"],
                    height=texture["height"],
                    palette_offset=current_palette["image"]["relative_offset"],
                    texel_offset=current_texture_image["relative_offset"],
                    load_tile=tile,
                )

            print(
                f"0x{offset:08X}: "
                f"G_LOADBLOCK "
                f"tile={tile} "
                f"uls={uls} "
                f"ult={ult} "
                f"lrs={lrs} "
                f"dxt={dxt} "
                f"source={load_source} "
                f"palette={palette_source} "
                f"state={tile_description}"
            )

        elif opcode == 0xF0:
            tile = (w1 >> 24) & 0x7
            count = (w1 >> 14) & 0x3FF

            if current_texture_image is not None:
                current_palette = {
                    "image": current_texture_image.copy(),
                    "tile": tile,
                    "entries": count + 1,
                }
            else:
                current_palette = None

            if current_texture_image is not None:
                source = f"0x{current_texture_image['address']:08X}"

                source_texture = current_texture_image["texture"]
                if source_texture is not None:
                    source += f" Texture[{source_texture['index']}]"
            else:
                source = "unknown"

            print(
                f"0x{offset:08X}: "
                f"G_LOADTLUT "
                f"tile={tile} "
                f"count={count} "
                f"entries={count + 1} "
                f"source={source}"
            )

        elif opcode == 0x04:
            n = (w0 & 0xFFFF) >> 10
            v0 = (w0 >> 16) & 0xFF
            address = w1

            if address >= 0x01000000 and address < 0x01000000 + model.vertex_count * VTX_SIZE:
                vertex_index = (address - 0x01000000) // VTX_SIZE

                for i in range(n):
                    if v0 + i < len(vertex_cache):
                        vertex_cache[v0 + i] = vertex_index + i

                print(
                    f"0x{offset:08X}: "
                    f"gsSPVertex n={n:2d} "
                    f"v0={v0:2d} "
                    f"address=0x{address:08X} "
                    f"-> Vtx[{vertex_index}]"
                )
            else:
                print(
                    f"0x{offset:08X}: "
                    f"gsSPVertex n={n:2d} "
                    f"v0={v0:2d} "
                    f"address=0x{address:08X}"
                )

        elif opcode == 0xB1:
            a = ((w0 >> 16) & 0xFF) // 2
            b = ((w0 >> 8) & 0xFF) // 2
            c = (w0 & 0xFF) // 2

            d = ((w1 >> 16) & 0xFF) // 2
            e = ((w1 >> 8) & 0xFF) // 2
            f = (w1 & 0xFF) // 2

            def resolve(slot):
                if 0 <= slot < len(vertex_cache):
                    return vertex_cache[slot]
                return None

            ra, rb, rc = resolve(a), resolve(b), resolve(c)
            rd, re, rf = resolve(d), resolve(e), resolve(f)

            def describe_triangle(indices):
                result = []
                for index in indices:
                    if index is None:
                        result.append("Vtx[?]")
                    else:
                        v = model.read_vertex(index)
                        result.append(
                            f"Vtx[{index}]"
                            f"=({v['x']},{v['y']},{v['z']})"
                        )
                return "[" + ", ".join(result) + "]"

            print(
                f"0x{offset:08X}: "
                f"G_TRI2 [{a}, {b}, {c}] [{d}, {e}, {f}]"
            )
            print(
                f"    -> {describe_triangle((ra, rb, rc))}"
            )
            print(
                f"    -> {describe_triangle((rd, re, rf))}"
            )

        offset += 8


if __name__ == "__main__":
    main()
