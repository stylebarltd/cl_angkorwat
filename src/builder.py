#!/usr/bin/env python3
"""
Builder: carve an AssaultCube map in code. Shared by the gen_*.py map generators.

Conventions (see the README for the engine facts behind them):
  - boxes are inclusive cell ranges (x1, y1, x2, y2); sym=True also carves the point-mirrored box,
    so a CTF map only describes the red half
  - keep ONE sky height over everything that sees each other. A face textured with sky (utex 0 at a
    ceiling step) is a sky portal: it paints the skybox and hides whatever is behind it. Any roofed
    area shows a facade from its roof up to the sky height, so roofs belong at the map's edge
  - a solid cell always rises to the ceiling of its open neighbours. Low walls, parapets and
    plinths are open cells with a raised floor (wall()) so the sky stays open above them
  - open() resets vdelta: carve ramps LAST in their section
"""
import acmap
from acmap import Cell, Entity, ENT, SOLID, SPACE, FHF

T_SKY = 0


class Builder:
    def __init__(self, sfactor, title, sky=16):
        self.m = acmap.Map.blank(sfactor, title)
        self.n = self.m.ssize
        self.sky = sky
        self.ents = []
        # per-map default textures: ground / wall / pillar / ramp
        self.ftex, self.wtex, self.ptex, self.rtex = 3, 2, 2, 3

    # ── geometry ────────────────────────────────────────────────────────────────────────
    def mirror(self, x, y):
        return self.n - 1 - x, self.n - 1 - y

    def cell(self, x, y):
        return self.m.cell(x, y)

    def _both(self, x1, y1, x2, y2, sym):
        boxes = [(x1, y1, x2, y2)]
        if sym:
            mx1, my1 = self.mirror(x2, y2); mx2, my2 = self.mirror(x1, y1)
            if (mx1, my1, mx2, my2) != (x1, y1, x2, y2):
                boxes.append((mx1, my1, mx2, my2))
        return boxes

    def open(self, x1, y1, x2, y2, floor=0, ceil=None, ftex=None, ctex=T_SKY, wtex=None, utex=None, sym=True):
        """Carve an open box. ceil None = the builder's sky height. utex (the face above a lower
        neighbouring ceiling) defaults to wtex."""
        c_ = self.sky if ceil is None else ceil
        ftex = self.ftex if ftex is None else ftex; wtex = self.wtex if wtex is None else wtex
        u = utex if utex is not None else wtex
        for (ax, ay, bx, by) in self._both(x1, y1, x2, y2, sym):
            for y in range(ay, by + 1):
                for x in range(ax, bx + 1):
                    c = self.cell(x, y)
                    c.type = SPACE; c.floor = floor; c.ceil = c_
                    c.ftex = ftex; c.ctex = ctex; c.wtex = wtex; c.utex = u; c.vdelta = 0; c.tag = 0

    def wall(self, x1, y1, x2, y2, height, wtex, ftex=None, ceil=None, sym=True):
        """A low wall / parapet / plinth: open cells with a raised floor, sky above."""
        self.open(x1, y1, x2, y2, floor=height, ceil=ceil, ftex=ftex if ftex is not None else wtex, wtex=wtex, sym=sym)

    def solid(self, x1, y1, x2, y2, wtex=None, sym=True):
        wtex = self.wtex if wtex is None else wtex
        for (ax, ay, bx, by) in self._both(x1, y1, x2, y2, sym):
            for y in range(ay, by + 1):
                for x in range(ax, bx + 1):
                    c = self.cell(x, y)
                    c.type = SOLID; c.wtex = c.utex = wtex; c.floor = 0; c.ceil = 16; c.vdelta = 0

    def roof(self, x1, y1, x2, y2, ceil, ctex, utex=None, sym=True):
        """Put a ceiling over open cells (utex = the facade shown above the roof edge)."""
        for (ax, ay, bx, by) in self._both(x1, y1, x2, y2, sym):
            for y in range(ay, by + 1):
                for x in range(ax, bx + 1):
                    c = self.cell(x, y)
                    if c.type != SOLID:
                        c.ceil = ceil; c.ctex = ctex
                        if utex is not None: c.utex = utex

    def ring(self, x1, y1, x2, y2, inset, fn, **kw):
        """Apply fn (open / wall / solid) to the 1-cell border of the box shrunk by `inset`."""
        ax, ay, bx, by = x1 + inset, y1 + inset, x2 - inset, y2 - inset
        fn(ax, ay, bx, ay, **kw); fn(ax, by, bx, by, **kw)
        if by - ay >= 2:
            fn(ax, ay + 1, ax, by - 1, **kw); fn(bx, ay + 1, bx, by - 1, **kw)

    def ramp(self, x1, y1, x2, y2, lo, hi, direction, ftex=None, sym=True):
        """Floor heightfield from height lo at the `direction` edge ('n','s','w','e' = the low edge)
        up to hi at the opposite edge. Vertex heights = floor - vdelta/4; the vertex of cell
        (x, y) is its north-west corner, so the row/column beyond the high edge keeps vdelta 0."""
        ftex = self.rtex if ftex is None else ftex
        boxes = self._both(x1, y1, x2, y2, sym)
        dirs = [direction, {"n": "s", "s": "n", "w": "e", "e": "w"}[direction]] if len(boxes) == 2 else [direction]
        for (ax, ay, bx, by), d in zip(boxes, dirs):
            span = (bx - ax + 1) if d in "we" else (by - ay + 1)
            for y in range(ay, by + 1):
                for x in range(ax, bx + 1):
                    c = self.cell(x, y)
                    c.type = FHF; c.floor = hi; c.ftex = ftex
                    if c.ceil <= hi + 5: c.ceil = self.sky
            for y in range(ay, by + 2):
                for x in range(ax, bx + 2):
                    if d == "w": t = (x - ax) / span
                    elif d == "e": t = (bx + 1 - x) / span
                    elif d == "n": t = (y - ay) / span
                    else: t = (by + 1 - y) / span
                    drop = (hi - lo) * (1 - t)
                    self.cell(x, y).vdelta = max(0, min(255, int(round(drop * 4))))

    def mound(self, x1, y1, x2, y2, top, height, ftex=None, sym=True):
        """A floor heightfield shaped by height(vx, vy) at the cell corners (vertex (vx, vy) is the
        north-west corner of cell (vx, vy)); every cell gets floor = top, so height must stay within
        top - 63 .. top. Used for chedi bells, mounds and domes."""
        ftex = self.rtex if ftex is None else ftex
        for k, (ax, ay, bx, by) in enumerate(self._both(x1, y1, x2, y2, sym)):
            for y in range(ay, by + 1):
                for x in range(ax, bx + 1):
                    c = self.cell(x, y)
                    c.type = FHF; c.floor = top; c.ftex = ftex
                    if c.ceil < top + 5: c.ceil = self.sky
            for vy in range(ay, by + 2):
                for vx in range(ax, bx + 2):
                    h = height(vx, vy) if k == 0 else height(self.n - vx, self.n - vy)
                    self.cell(vx, vy).vdelta = max(0, min(255, int(round((top - h) * 4))))

    def pillar(self, x, y, wtex=None, sym=True):
        self.solid(x, y, x, y, self.ptex if wtex is None else wtex, sym)

    # ── entities ─────────────────────────────────────────────────────────────────────────
    def ent(self, typ, x, y, dz=4, attr1=0, attr2=0, attr3=0, attr4=0, sym=True, team_pair=None):
        """An entity dz above the cell floor; sym adds the mirrored one (angle + 180, team swapped)."""
        c = self.cell(x, y)
        self.ents.append(Entity(ENT[typ], x, y, c.floor + dz, attr1, attr2, attr3, attr4))
        if sym:
            mx, my = self.mirror(x, y)
            a2 = team_pair.get(attr2, attr2) if team_pair else attr2
            a1 = (attr1 + 1800) % 3600 if typ in ("PLAYERSTART", "CTF_FLAG", "MAPMODEL") else attr1
            self.ents.append(Entity(ENT[typ], mx, my, self.cell(mx, my).floor + dz, a1, a2, attr3, attr4))

    def light(self, x, y, radius=12, intensity=120, rgb=None, dz=6, sym=True):
        if rgb: self.ent("LIGHT", x, y, dz, radius, rgb[0], rgb[1], rgb[2], sym)
        else: self.ent("LIGHT", x, y, dz, radius, intensity, 0, 0, sym)

    def lightgrid(self, step, radius, rgb, x1=0, y1=0, x2=None, y2=None):
        """A light over every open cell of a grid, lower under roofs. Returns the count."""
        x2 = self.n - 1 if x2 is None else x2; y2 = self.n - 1 if y2 is None else y2
        n = 0
        for y in range(y1 + step // 2, y2, step):
            for x in range(x1 + step // 2, x2, step):
                c = self.cell(x, y)
                if c.type != SOLID and c.ceil - c.floor >= 5:
                    self.light(x, y, radius=radius, rgb=rgb, dz=min(8, c.ceil - c.floor - 2), sym=False); n += 1
        return n

    def spawn(self, x, y, angle, team):
        self.ent("PLAYERSTART", x, y, 5, angle, team, sym=True, team_pair={0: 1, 1: 0})

    def model(self, x, y, idx, angle=0, dz=0.0, sym=True):
        """A mapmodel at cell floor + dz cubes (the engine reads the height from attr3 in fifths of a
        cube; the entity's own z is ignored for mapmodels)."""
        self.ent("MAPMODEL", x, y, 0, angle, idx, int(round(dz * 5)), 0, sym)

    def clip(self, x, y, hx, hy, h, dz=0.0, sym=True):
        """A CLIP box centred on (x, y): half sizes hx, hy and height h in cubes, bottom at floor + dz.
        Blocks players and grenades (attr1 elevation in tenths, attr2..4 in fifths)."""
        self.ent("CLIP", x, y, 0, int(round(dz * 10)), int(round(hx * 5)), int(round(hy * 5)), int(round(h * 5)), sym)

    def finish(self):
        self.m.entities = self.ents
        return self.m


# ── header extras: vantage point, map info, embedded config ─────────────────────────────
def _putint(buf, n):
    if -128 <= n <= 127: buf.append(n & 255)
    elif -32768 <= n <= 32767: buf += bytes((0x80,)) + (n & 0xffff).to_bytes(2, "little")
    else: buf += bytes((0x81,)) + (n & 0xffffffff).to_bytes(4, "little")


def _putuint(buf, n):
    while True:
        byte = n & 0x7f; n >>= 7
        if n: buf.append(byte | 0x80)
        else: buf.append(byte); break


def make_extras(vantage, license, comment, config):
    """vantage = (x, y, z, yaw, pitch) in cubes / degrees (yaw 0 = -y north, 90 = +x east);
    config = cubescript text (fog, loadsky, watercolour ...)."""
    DMF = 16
    vp = bytearray()
    for v in (vantage[0] * DMF, vantage[1] * DMF, vantage[2] * DMF, vantage[3], vantage[4]): _putint(vp, v)
    out = bytearray()
    for data, flags in ((bytes(vp), 0x46), (license.encode() + b"\0" + comment.encode() + b"\0", 0x41),
                        (config.encode() + b"\0", 0x45)):
        _putuint(out, len(data)); _putuint(out, flags); out += data
    return bytes(out)
