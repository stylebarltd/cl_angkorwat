#!/usr/bin/env python3
"""
AssaultCube map files (.cgz, format version 10), read and write.

A map is a gzip stream: a 980-byte header, optional "header extras", the entity
list (16 bytes each), then the world grid run-length encoded. The grid is
ssize x ssize cells (ssize = 1 << sfactor, indexed [y][x]); every cell has a
type (SOLID, CORNER, FHF, CHF, SPACE), floor and ceiling height in cubes,
wall / floor / ceiling / upper-wall textures, a vertex delta for heightfields
and a tag. Light values are not stored (the client computes them on load).

Reference: AssaultCube source, source/src/world.h, worldio.cpp, entity.h.

    python3 acmap.py info <map.cgz>            # header, entities, cell statistics
    python3 acmap.py roundtrip <map.cgz>       # read, write, compare the decompressed bytes
"""
import gzip, os, struct, sys, tempfile, time
from dataclasses import dataclass, field

SOLID, CORNER, FHF, CHF, SPACE = 0, 1, 2, 3, 4
TYPES = {SOLID: "SOLID", CORNER: "CORNER", FHF: "FHF", CHF: "CHF", SPACE: "SPACE"}

ENT_TYPES = ["NOTUSED", "LIGHT", "PLAYERSTART", "I_CLIPS", "I_AMMO", "I_GRENADE", "I_HEALTH", "I_HELMET",
             "I_ARMOUR", "I_AKIMBO", "MAPMODEL", "CARROT", "LADDER", "CTF_FLAG", "SOUND", "CLIP", "PLCLIP", "DUMMYENT"]
ENT = {n: i for i, n in enumerate(ENT_TYPES)}

HEADER = struct.Struct("<4siii i 128s 768s i 4B i i i i 40s")   # 980 bytes
ENTITY = struct.Struct("<hhh h B BBB h b B")                     # 16 bytes
assert HEADER.size == 980 and ENTITY.size == 16

# default texture ids (world.h): sky 0, liquid 1, wall 2, floor 3, ceiling 4
DEFAULT_SKY, DEFAULT_LIQUID, DEFAULT_WALL, DEFAULT_FLOOR, DEFAULT_CEIL = 0, 1, 2, 3, 4


@dataclass
class Cell:
    type: int = SOLID
    floor: int = 0
    ceil: int = 16
    wtex: int = DEFAULT_WALL
    ftex: int = DEFAULT_FLOOR
    ctex: int = DEFAULT_CEIL
    vdelta: int = 0
    utex: int = DEFAULT_WALL
    tag: int = 0

    def key(self):
        return (self.type, self.floor, self.ceil, self.wtex, self.ftex, self.ctex, self.vdelta, self.utex, self.tag)


@dataclass
class Entity:
    type: int
    x: int
    y: int
    z: int
    attr1: int = 0
    attr2: int = 0
    attr3: int = 0
    attr4: int = 0
    attr5: int = 0
    attr6: int = 0
    attr7: int = 0

    @property
    def name(self):
        return ENT_TYPES[self.type] if self.type < len(ENT_TYPES) else str(self.type)


@dataclass
class Map:
    sfactor: int = 7
    title: str = ""
    waterlevel: int = -100000              # in tenths of a cube (version 10); -10 = water at -1 cube
    watercolor: tuple = (20, 25, 20, 150)
    maprevision: int = 1
    ambient: int = 0
    flags: int = 0
    timestamp: int = 0
    entities: list = field(default_factory=list)
    cells: list = field(default_factory=list)      # ssize * ssize Cells, row-major [y * ssize + x]
    extras: bytes = b""                            # header extras, kept verbatim

    @property
    def ssize(self):
        return 1 << self.sfactor

    def cell(self, x, y):
        return self.cells[y * self.ssize + x]

    @classmethod
    def blank(cls, sfactor=7, title=""):
        m = cls(sfactor=sfactor, title=title, timestamp=int(time.time()))
        m.cells = [Cell() for _ in range(m.ssize * m.ssize)]
        return m


def sqrdefault():
    # sqrdefault() in world.cpp: SOLID cube, floor 0, ceil 16, default textures, vdelta 0, tag 0
    return Cell()


def read(path):
    data = gzip.open(path, "rb").read()
    head, version, headersize, sfactor, numents, title, texlists, waterlevel, wr, wg, wb, wa, maprevision, ambient, flags, timestamp, _res = HEADER.unpack_from(data, 0)
    if head not in (b"ACMP", b"CUBE"):
        raise ValueError(f"not an AssaultCube map: {head!r}")
    if version < 6:
        raise ValueError(f"map version {version} is older than this reader supports")
    m = Map(sfactor=sfactor, title=title.split(b"\0")[0].decode("latin-1"), waterlevel=waterlevel,
            watercolor=(wr, wg, wb, wa), maprevision=maprevision, ambient=ambient, flags=flags, timestamp=timestamp)
    m.texlists = texlists
    pos = HEADER.size
    extra = headersize - HEADER.size
    if extra > 0 and version >= 10:        # fixmapheadersize(): the header size of files older than 10 is not trusted
        m.extras = data[pos:pos + extra]
        pos += extra
    # version < 10: 12-byte entities (no attr5..7), attributes unscaled (angles in degrees, not tenths),
    # water level in whole cubes (version 10 stores tenths)
    old = version < 10
    for _ in range(numents):
        if old:
            x, y, z, attr1, typ, a2, a3, a4 = struct.unpack_from("<hhhhBBBB", data, pos)
            pos += 12
            a5 = a6 = a7 = 0
        else:
            x, y, z, attr1, typ, a2, a3, a4, a5, a6, a7 = ENTITY.unpack_from(data, pos)
            pos += ENTITY.size
        m.entities.append(Entity(typ, x, y, z, attr1, a2, a3, a4, a5, a6, a7))
    if old:
        m.waterlevel *= 10
        m.extras = b""   # version 9 may carry a mediareq block in the header; not an extras packet
    # run-length decoding (rldecodecubes)
    n = m.ssize * m.ssize
    cells = []
    prev = None
    while len(cells) < n:
        t = data[pos]; pos += 1
        if t == 255:
            cnt = data[pos]; pos += 1
            for _ in range(cnt):
                cells.append(Cell(*prev.key()))
        elif t == 254:
            cells.append(Cell(*prev.key())); pos += 2
        elif t == SOLID:
            c = sqrdefault(); c.type = SOLID
            c.utex = c.wtex = data[pos]; c.vdelta = data[pos + 1]; pos += 2
            cells.append(c)
        else:
            if t == 253:
                t = SOLID
            if t >= 5:
                raise ValueError(f"cell type {t} out of range at {len(cells)}")
            c = sqrdefault(); c.type = t
            c.floor = struct.unpack("b", data[pos:pos + 1])[0]
            c.ceil = struct.unpack("b", data[pos + 1:pos + 2])[0]
            if c.floor >= c.ceil:
                c.floor = c.ceil - 1
            c.wtex, c.ftex, c.ctex, c.vdelta, c.utex, c.tag = data[pos + 2:pos + 8]
            pos += 8
            cells.append(c)
        prev = cells[-1]
    if len(cells) != n:
        raise ValueError(f"cell count {len(cells)} != {n}")
    m.cells = cells
    m.trailing = data[pos:]
    return m


def encode_cells(cells, preserve_solids=False):
    """rlencodecubes(): runs of identical cells become 255 + count (max 255 per chunk)."""
    out = bytearray()
    prev = None
    sc = 0

    def spurge():
        nonlocal sc
        while sc:
            out.append(255)
            if sc > 255:
                out.append(255); sc -= 255
            else:
                out.append(sc); sc = 0

    for c in cells:
        if c.type == SOLID and not preserve_solids:
            if prev is not None and prev.type == c.type and prev.wtex == c.wtex and prev.vdelta == c.vdelta:
                sc += 1
            else:
                spurge()
                out += bytes((c.type, c.wtex & 255, c.vdelta & 255))
        else:
            if prev is not None and prev.key() == c.key():
                sc += 1
            else:
                spurge()
                out.append(253 if c.type == SOLID else c.type)
                out += struct.pack("bb", c.floor, c.ceil)
                out += bytes((c.wtex & 255, c.ftex & 255, c.ctex & 255, c.vdelta & 255, c.utex & 255, c.tag & 255))
        prev = c
    spurge()
    return bytes(out)


def write(m, path, preserve_solids=False):
    texlists = getattr(m, "texlists", None) or bytes(range(256)) * 3
    title = m.title.encode("latin-1")[:127].ljust(128, b"\0")
    hdr = HEADER.pack(b"ACMP", 10, HEADER.size + len(m.extras), m.sfactor, len(m.entities), title, texlists,
                      m.waterlevel, *m.watercolor, m.maprevision, m.ambient, m.flags, m.timestamp or int(time.time()), b"\0" * 40)
    body = bytearray(hdr)
    body += m.extras
    for e in m.entities:
        body += ENTITY.pack(e.x, e.y, e.z, e.attr1, e.type, e.attr2 & 255, e.attr3 & 255, e.attr4 & 255, e.attr5, e.attr6, e.attr7 & 255)
    body += encode_cells(m.cells, preserve_solids)
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(bytes(body))
    return bytes(body)


def info(m):
    from collections import Counter
    print(f"title {m.title!r}  sfactor {m.sfactor} ({m.ssize}x{m.ssize})  entities {len(m.entities)}  waterlevel {m.waterlevel}  ambient {m.ambient}  flags {m.flags}  extras {len(m.extras)} B")
    types = Counter(TYPES.get(c.type, c.type) for c in m.cells)
    print("cells:", dict(types))
    open_cells = [c for c in m.cells if c.type != SOLID]
    if open_cells:
        print(f"floor {min(c.floor for c in open_cells)}..{max(c.floor for c in open_cells)}  ceil {min(c.ceil for c in open_cells)}..{max(c.ceil for c in open_cells)}")
        print("floor textures:", Counter(c.ftex for c in open_cells).most_common(6))
        print("wall textures:", Counter(c.wtex for c in open_cells).most_common(6))
        print("ceil textures:", Counter(c.ctex for c in open_cells).most_common(6))
    ents = Counter(e.name for e in m.entities)
    print("entities:", dict(ents))
    for e in m.entities:
        if e.name in ("PLAYERSTART", "CTF_FLAG"):
            print(f"  {e.name} x={e.x} y={e.y} z={e.z} attr1={e.attr1} attr2={e.attr2}")
    lights = [e for e in m.entities if e.name == "LIGHT"]
    if lights:
        print(f"  lights: {len(lights)}, e.g. {[(e.x, e.y, e.z, e.attr1, e.attr2, e.attr3, e.attr4) for e in lights[:3]]}")


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    m = read(path)
    if cmd == "info":
        info(m)
    elif cmd == "roundtrip":
        original = gzip.open(path, "rb").read()
        out = os.path.join(tempfile.gettempdir(), "roundtrip.cgz")
        body = write(m, out)
        same = original[:len(body)] == body and len(original) == len(body) + len(m.trailing)
        print(f"original {len(original)} B, rewritten {len(body)} B, trailing {len(m.trailing)} B, identical: {same}")
        if not same:
            i = next((i for i in range(min(len(original), len(body))) if original[i] != body[i]), None)
            print("first difference at byte", i, "header ends at", HEADER.size, "entities end at", HEADER.size + len(m.extras) + 16 * len(m.entities))
