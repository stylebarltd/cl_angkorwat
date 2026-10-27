#!/usr/bin/env python3
"""
Custom AssaultCube map models (MD3), built in code: a mesh toolkit, a painted texture atlas,
an MD3 writer and an offline preview renderer.

    python3 models.py build [outdir]     # writes <outdir>/stylebar/thai/<model>/{tris.md3,md3.cfg}
                                         # + thai_atlas.png; default outdir: models/
    python3 models.py preview out.png    # flat-shaded contact sheet of all models
    python3 models.py install            # build into ~/.assaultcube/v1.3/packages/models/mapmodels

Engine facts (md3.h / vertmodel.h / entities.cpp, AC 1.3):
  - md3 vertex shorts / 64 = model units; units / 16 = cubes (mdlscale 100). The loader swaps x/y,
    so the file stores (y, x, z) for an engine-space (x, y, z). Engine space: x east, y south, z up.
  - a front face is counter-clockwise seen from outside in engine space ((B-A) x (C-A) points out);
    the toolkit orients every closed part by its centroid, flat cards get both sides
  - a mapmodel sits at cell floor + zoff + attr3/5 at the entity's x/y, yaw = attr1/10
  - a mapmodel collides only if its slot has h > 0 (`mapmodel rad h ...`); ours use 0 0 and CLIP boxes
  - UV: (0,0) is the top-left of the skin image
Models live under mapmodels/stylebar/thai/ and are appended to the default list by the map's
embedded config (indices 202 and up). Every player needs the folder; without it the model is
simply not drawn.
"""
import math, os, struct, sys
from PIL import Image, ImageDraw, ImageFilter

# an AssaultCube 1.3 install (its packages/textures): set AC_DIR, default ~/assaultcube
AC_TEXDIR = os.path.join(os.path.expanduser(os.environ.get("AC_DIR", "~/assaultcube")), "packages", "textures")
AC_TEXTURES = {12: "boeck/stone_022.jpg", 50: "makke/platten.jpg", 45: "makke/stein.jpg", 23: "makke/mauer1.jpg",
               111: "boeck/wood_010.jpg"}
ATLAS = 1024
TILE = 128
GRID = ATLAS // TILE
PAD = 10                 # px inset of the UVs inside each tile (mipmap bleeding)

# ── texture atlas ────────────────────────────────────────────────────────────────────────
MATERIALS = {}           # name -> tile index


def _noise(d, box, base, amount, n=900, seed=1, size=2):
    import random
    r = random.Random(seed)
    x0, y0, x1, y1 = box
    for _ in range(n):
        x, y = r.randint(x0, x1 - 1), r.randint(y0, y1 - 1)
        k = r.randint(-amount, amount)
        c = tuple(max(0, min(255, v + k)) for v in base)
        d.rectangle((x, y, x + size - 1, y + size - 1), fill=c)


def paint_atlas():
    im = Image.new("RGB", (ATLAS, ATLAS), (128, 128, 128))
    d = ImageDraw.Draw(im)
    tiles = []

    def tile(name):
        i = len(tiles); tiles.append(name); MATERIALS[name] = i
        x, y = (i % GRID) * TILE, (i // GRID) * TILE
        return x, y, x + TILE, y + TILE

    def flat(name, rgb, noise=8, seed=1):
        b = tile(name); d.rectangle(b, fill=rgb); _noise(d, b, rgb, noise, seed=seed)
        return b

    flat("red_paint", (178, 32, 28), 10)
    flat("red_dark", (120, 20, 18), 8)
    flat("black", (28, 28, 30), 6)
    b = tile("rubber"); d.rectangle(b, fill=(30, 30, 32))
    for k in range(0, TILE, 12): d.line((b[0] + k, b[1], b[0] + k, b[3]), fill=(48, 48, 50), width=3)
    b = tile("chrome");
    for k in range(TILE): d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(int(150 + 90 * math.sin(k / 18)),) * 3)
    b = tile("glass")
    for k in range(TILE): d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(60 + k // 3, 80 + k // 3, 100 + k // 3))
    d.line((b[0] + 20, b[1] + 100, b[0] + 90, b[1] + 20), fill=(170, 190, 205), width=6)
    b = tile("headlight"); d.rectangle(b, fill=(60, 60, 60)); d.ellipse((b[0] + 14, b[1] + 14, b[2] - 14, b[3] - 14), fill=(255, 245, 200))
    b = tile("wood"); d.rectangle(b, fill=(122, 82, 46))
    for k in range(0, TILE, 16):
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(80, 52, 28), width=2)
        _noise(d, (b[0], b[1] + k, b[2], b[1] + k + 15), (122, 82, 46), 14, n=120, seed=k, size=3)
    b = tile("wood_dark"); d.rectangle(b, fill=(78, 50, 30)); _noise(d, b, (78, 50, 30), 12, seed=3, size=3)
    flat("white", (232, 228, 214), 6)
    b = tile("gold"); d.rectangle(b, fill=(212, 160, 40))
    for k in range(0, TILE, 16):
        for j in range(0, TILE, 16): d.ellipse((b[0] + k + 3, b[1] + j + 3, b[0] + k + 13, b[1] + j + 13), outline=(250, 210, 90), width=2)
    b = tile("roof_orange"); d.rectangle(b, fill=(196, 92, 34))
    for k in range(0, TILE, 10): d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(140, 58, 20), width=2)
    for k in range(0, TILE, 16): d.line((b[0] + k, b[1], b[0] + k, b[3]), fill=(170, 74, 26), width=1)
    b = tile("roof_green"); d.rectangle(b, fill=(40, 110, 70))
    for k in range(0, TILE, 10): d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(24, 70, 44), width=2)
    for name, c1, c2 in (("canvas_red", (196, 36, 36), (238, 232, 220)), ("canvas_green", (40, 120, 90), (232, 226, 200)),
                         ("canvas_blue", (40, 80, 160), (230, 230, 230))):
        b = tile(name)
        for k in range(8): d.rectangle((b[0] + k * 16, b[1], b[0] + k * 16 + 15, b[3]), fill=c1 if k % 2 == 0 else c2)
    b = tile("lantern_red"); d.rectangle(b, fill=(214, 52, 30))
    for k in range(0, TILE, 16): d.line((b[0] + k, b[1], b[0] + k, b[3]), fill=(170, 30, 20), width=3)
    d.rectangle((b[0], b[1] + 54, b[2], b[1] + 74), fill=(240, 190, 60))
    b = tile("lantern_orange"); d.rectangle(b, fill=(240, 140, 40))
    for k in range(0, TILE, 16): d.line((b[0] + k, b[1], b[0] + k, b[3]), fill=(200, 100, 20), width=3)
    d.rectangle((b[0], b[1] + 54, b[2], b[1] + 74), fill=(250, 230, 150))
    flat("rope", (70, 56, 40), 10)
    b = tile("tung")                                    # Lanna prayer banner: bands and fringes
    cols = [(220, 40, 40), (250, 200, 40), (40, 140, 70), (240, 240, 230), (60, 90, 190), (230, 110, 40)]
    for k in range(8): d.rectangle((b[0], b[1] + k * 16, b[2], b[1] + k * 16 + 15), fill=cols[k % len(cols)])
    for k in range(8): d.line((b[0], b[1] + k * 16, b[2], b[1] + k * 16), fill=(250, 220, 120), width=2)
    b = tile("thai_flag")                               # red / white / blue (double) / white / red, 1:1:2:1:1
    for (a, z, c) in ((0, 21, (165, 25, 50)), (21, 43, (244, 245, 248)), (43, 85, (45, 42, 74)), (85, 107, (244, 245, 248)), (107, 128, (165, 25, 50))):
        d.rectangle((b[0], b[1] + a, b[2], b[1] + z), fill=c)
    flat("steel", (170, 172, 176), 10)
    flat("plastic_red", (210, 40, 40), 5)
    flat("plastic_blue", (40, 90, 200), 5)
    flat("tarp_blue", (40, 70, 150), 8)
    flat("vinyl", (60, 40, 30), 6)
    flat("engine", (90, 92, 96), 12)
    b = tile("garland"); d.rectangle(b, fill=(250, 250, 240))
    import random
    r = random.Random(5)
    for _ in range(140):
        x, y = r.randint(b[0], b[2] - 10), r.randint(b[1], b[3] - 10)
        d.ellipse((x, y, x + 10, y + 10), fill=r.choice([(250, 160, 30), (240, 70, 120), (250, 250, 250), (230, 40, 40)]))
    b = tile("plate"); d.rectangle(b, fill=(240, 240, 240)); d.rectangle((b[0] + 6, b[1] + 40, b[2] - 6, b[3] - 40), outline=(20, 20, 20), width=4)
    flat("yellow_paint", (230, 180, 30), 8)
    flat("green_paint", (30, 120, 90), 8)
    flat("blue_paint", (40, 90, 170), 8)
    b = tile("white_trim"); d.rectangle(b, fill=(235, 232, 220))
    for k in range(0, TILE, 32): d.rectangle((b[0] + k, b[1] + 50, b[0] + k + 16, b[1] + 78), fill=(212, 160, 40))
    b = tile("mango"); d.rectangle(b, fill=(96, 70, 36))
    for _ in range(700):
        x, y = r.randint(b[0], b[2] - 7), r.randint(b[1], b[3] - 5)
        c = r.choice([(240, 190, 40), (230, 150, 30), (130, 170, 50), (200, 60, 40), (250, 220, 90)])
        d.ellipse((x, y, x + 7, y + 5), fill=c); d.point((x + 2, y + 1), fill=tuple(min(255, v + 40) for v in c))
    b = tile("basket"); d.rectangle(b, fill=(176, 136, 80))
    for k in range(0, TILE, 8):
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(130, 96, 52), width=2)
        d.line((b[0] + k, b[1], b[0] + k, b[3]), fill=(150, 112, 64), width=1)
    flat("terracotta", (170, 90, 60), 10)

    # copies of AC world textures (so model surfaces can continue the floors and walls around them)
    import os as _os
    for tid, path in AC_TEXTURES.items():
        b = tile(f"ac{tid}")
        src = _os.path.join(AC_TEXDIR, path)
        try:
            t = Image.open(src).convert("RGB").resize((TILE - 2 * PAD, TILE - 2 * PAD), Image.LANCZOS)
        except Exception:
            t = Image.new("RGB", (TILE - 2 * PAD, TILE - 2 * PAD), (150, 130, 110))
        s_ = TILE - 2 * PAD
        big = Image.new("RGB", (3 * s_, 3 * s_))
        for i in range(3):
            for j in range(3): big.paste(t, (i * s_, j * s_))
        im.paste(big.crop((s_ - PAD, s_ - PAD, s_ - PAD + TILE, s_ - PAD + TILE)), (b[0], b[1]))   # wrapped border
    # Khmer stonework
    b = tile("khmer_roof"); d.rectangle(b, fill=(58, 56, 52))
    for k in range(0, TILE, 9):
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(62, 55, 48), width=2)
        off = 6 if (k // 9) % 2 else 0
        for j in range(off, TILE, 12): d.line((b[0] + j, b[1] + k, b[0] + j, b[1] + k + 8), fill=(70, 62, 54), width=1)
    _noise(d, b, (58, 56, 52), 9, n=1200, seed=11)
    b = tile("khmer_gable"); d.rectangle(b, fill=(92, 82, 68)); _noise(d, b, (92, 82, 68), 12, n=900, seed=12)
    for k in range(3):
        d.arc((b[0] + 10 + k * 12, b[1] + 30 + k * 8, b[2] - 10 - k * 12, b[3] + 60 - k * 8), 180, 360, fill=(92, 80, 64), width=2)
    for j in range(0, TILE, 20): d.ellipse((b[0] + j + 4, b[3] - 22, b[0] + j + 16, b[3] - 10), outline=(110, 92, 70), width=2)
    b = tile("khmer_ceiling"); d.rectangle(b, fill=(58, 50, 42))
    for k in range(0, TILE, 32):
        d.rectangle((b[0] + k + 4, b[1] + 4, b[0] + k + 28, b[3] - 4), outline=(44, 38, 32), width=3)
    b = tile("naga_stone"); d.rectangle(b, fill=(128, 118, 96))
    for j in range(0, TILE, 10):
        for k in range(0, TILE, 10): d.arc((b[0] + k - (5 if (j // 10) % 2 else 0), b[1] + j, b[0] + k + 10, b[1] + j + 12), 0, 180, fill=(96, 88, 70), width=2)
    b = tile("lotus_stone"); d.rectangle(b, fill=(78, 75, 68))
    for k in range(0, TILE, 16): d.polygon([(b[0] + k, b[3]), (b[0] + k + 8, b[1] + 40), (b[0] + k + 16, b[3])], outline=(100, 84, 64))
    _noise(d, b, (78, 75, 68), 9, n=500, seed=13)
    import random as _r
    rnd = _r.Random(7)
    def moss(b, n):
        for _ in range(n):
            cx, cy, rr = rnd.randint(b[0], b[2]), rnd.randint(b[1], b[3]), rnd.randint(4, 18)
            g = (rnd.randint(52, 70), rnd.randint(68, 86), rnd.randint(36, 46))
            d.ellipse((max(b[0], cx - rr), max(b[1], cy - rr), min(b[2], cx + rr), min(b[3], cy + rr)), fill=g)
    b = tile("moss_roof"); d.rectangle(b, fill=(62, 62, 52))
    for k in range(0, TILE, 9):
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(44, 46, 38), width=2)
    moss(b, 45); _noise(d, b, (62, 70, 50), 10, n=1400, seed=14)
    b = tile("moss_stone"); d.rectangle(b, fill=(88, 82, 70)); _noise(d, b, (88, 82, 70), 12, n=900, seed=15)
    for k in range(0, TILE, 24): d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(64, 58, 48), width=2)
    moss(b, 25)
    b = tile("ac12_moss")
    src = Image.open(_os.path.join(AC_TEXDIR, AC_TEXTURES[12])).convert("RGB").resize((TILE, TILE), Image.LANCZOS)
    im.paste(src, (b[0], b[1])); moss(b, 55)
    b = tile("fig_bark"); d.rectangle(b, fill=(86, 80, 70))
    for k in range(0, TILE, 5): d.line((b[0] + k, b[1], b[0] + k + rnd.randint(-3, 3), b[3]), fill=(64, 60, 52), width=1)
    _noise(d, b, (86, 80, 70), 10, n=700, seed=16)
    moss(b, 10)
    b = tile("murky_water"); d.rectangle(b, fill=(46, 58, 40))
    for _ in range(260):                                                 # ripples and scum
        cx, cy = rnd.randint(b[0], b[2]), rnd.randint(b[1], b[3])
        g = rnd.choice(((58, 72, 50), (38, 48, 34), (66, 80, 52), (52, 64, 44)))
        d.ellipse((cx - rnd.randint(3, 9), cy - 1, cx + rnd.randint(3, 9), cy + 1), fill=g)
    b = tile("pool_water"); d.rectangle(b, fill=(44, 58, 62))           # dark water, the sunset sky in it
    for k in range(0, TILE, 2):
        t = k / TILE
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(int(44 + 30 * t), int(58 + 10 * t), int(62 - 6 * t)))
    for _ in range(220):
        cx, cy = rnd.randint(b[0], b[2]), rnd.randint(b[1], b[3])
        g = rnd.choice(((92, 96, 92), (130, 112, 88), (34, 46, 52), (70, 84, 86)))
        d.line((cx - rnd.randint(4, 12), cy, cx + rnd.randint(4, 12), cy), fill=g, width=1)
    b = tile("plank"); d.rectangle(b, fill=(72, 52, 34))
    for k in range(0, TILE, 3):
        d.line((b[0], b[1] + k, b[2], b[1] + k + rnd.randint(-2, 2)), fill=rnd.choice(((60, 43, 28), (82, 60, 38), (68, 49, 32))), width=1)
    for _ in range(6):
        cx, cy = rnd.randint(b[0] + 8, b[2] - 8), rnd.randint(b[1] + 8, b[3] - 8)
        d.ellipse((cx - 5, cy - 2, cx + 5, cy + 2), outline=(62, 44, 28))
    b = tile("leaves"); d.rectangle(b, fill=(28, 44, 22))
    for _ in range(500):
        cx, cy = rnd.randint(b[0], b[2]), rnd.randint(b[1], b[3])
        g = rnd.choice(((42, 64, 30), (22, 36, 18), (52, 74, 36), (34, 54, 26)))
        d.ellipse((cx - 4, cy - 2, cx + 4, cy + 2), fill=g)
    # the cubeLadder trophy: white cube, its sides with blue paint dripping down, logo blue, gold
    flat("cl_white", (236, 236, 230), 6, seed=31)
    b = tile("cl_drips"); d.rectangle(b, fill=(236, 236, 230)); _noise(d, b, (236, 236, 230), 6, seed=32)
    blue = (38, 96, 245)
    d.rectangle((b[0], b[1], b[2], b[1] + 16), fill=blue)
    for k in range(9):
        x = b[0] + 8 + k * 13 + rnd.randint(-3, 3)
        ln, w_ = rnd.randint(20, 90), rnd.randint(4, 8)
        d.rectangle((x, b[1] + 10, x + w_, b[1] + ln), fill=blue)
        d.ellipse((x - 2, b[1] + ln - 4, x + w_ + 2, b[1] + ln + w_), fill=blue)
    flat("cl_blue", blue, 12, seed=33)
    flat("cl_edge", (16, 24, 58), 6, seed=34)                         # the logo's dark outlines
    b = tile("gold")
    for k in range(TILE):
        t = 0.5 + 0.5 * math.sin(k / 9.0)
        d.line((b[0], b[1] + k, b[2], b[1] + k), fill=(int(170 + 70 * t), int(130 + 60 * t), int(40 + 30 * t)))
    # a QR code to https://cubeladder.ovh on the logo cube's top (assets/cubeladder-qr.png, 1 px per module)
    b = tile("cl_qr"); d.rectangle(b, fill=(255, 255, 255))
    qr = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "cubeladder-qr.png")
    if _os.path.exists(qr):
        from PIL import ImageOps
        # pre-mirrored: the engine draws our meshes mirrored, and an unmirrored code came out mirrored in game
        # (screenshot matched the asset mirrored + turned 90 degrees); phone cameras often reject mirrored codes
        q = ImageOps.mirror(Image.open(qr).convert("RGB"))
        k = (TILE - 2 * PAD) // q.size[0]                                # whole pixels per module
        q = q.resize((q.size[0] * k, q.size[1] * k), Image.NEAREST)
        im.paste(q, (b[0] + (TILE - q.size[0]) // 2, b[1] + (TILE - q.size[1]) // 2))
    # the cubeLadder icon on stone
    b = tile("cl_logo")
    im.paste(Image.open(_os.path.join(AC_TEXDIR, AC_TEXTURES[12])).convert("RGB").resize((TILE, TILE)), (b[0], b[1]))
    logo = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "cubeladder-icon.png")
    if _os.path.exists(logo):
        from PIL import ImageOps                                        # mirrored: the engine mirrors our meshes in x
        ic = ImageOps.mirror(Image.open(logo).convert("RGBA").resize((TILE - 2 * PAD, TILE - 2 * PAD), Image.LANCZOS))
        im.paste(ic, (b[0] + PAD, b[1] + PAD), ic)
    return im


# ── meshes ───────────────────────────────────────────────────────────────────────────────
class Mesh:
    """Triangles with per-corner UVs. Coordinates in cubes, engine space (x east, y south, z up)."""

    def __init__(self):
        self.tris = []       # [((x,y,z),(u,v)) x 3]

    def add(self, other):
        self.tris += other.tris
        return self

    # parts are built closed and oriented outward by their own centroid
    def _orient(self, tris, centre=None, both=False):
        if centre is None:
            pts = [p for t in tris for p, _ in t]
            centre = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
        for t in tris:
            (a, _), (b, _), (c, _) = t
            n = _cross(_sub(b, a), _sub(c, a))
            m = tuple((a[i] + b[i] + c[i]) / 3 - centre[i] for i in range(3))
            if both:
                self.tris.append(t); self.tris.append((t[0], t[2], t[1]))
            elif _dot(n, m) >= 0:
                self.tris.append(t)
            else:
                self.tris.append((t[0], t[2], t[1]))
        return self

    def transformed(self, fn):
        out = Mesh()
        out.tris = [tuple((fn(p), uv) for p, uv in t) for t in self.tris]
        return out


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _cross(u, w): return (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
def _dot(u, w): return u[0] * w[0] + u[1] * w[1] + u[2] * w[2]


def uvbox(mat, u0=0.0, v0=0.0, u1=1.0, v1=1.0):
    """Map unit square sub-rect (u0..u1, v0..v1) of a material tile to atlas UVs."""
    i = MATERIALS[mat]
    tx, ty = (i % GRID) * TILE + PAD, (i // GRID) * TILE + PAD
    s = TILE - 2 * PAD
    return lambda u, v: ((tx + (u0 + (u1 - u0) * u) * s) / ATLAS, (ty + (v0 + (v1 - v0) * v) * s) / ATLAS)


def quad_tris(p, mat, uv=None):
    """p = 4 corners in order around the quad; uv = 4 (u,v) in tile space."""
    f = uvbox(mat)
    uv = uv or ((0, 1), (1, 1), (1, 0), (0, 0))
    q = [(p[i], f(*uv[i])) for i in range(4)]
    return [(q[0], q[1], q[2]), (q[0], q[2], q[3])]


def box(x0, y0, z0, x1, y1, z1, mat, mats=None):
    """Axis-aligned box. mats: optional dict per face 'top','bottom','n','s','e','w'."""
    mats = mats or {}
    P = lambda x, y, z: (x, y, z)
    faces = {
        "top": [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)],
        "bottom": [P(x0, y0, z0), P(x1, y0, z0), P(x1, y1, z0), P(x0, y1, z0)],
        "n": [P(x0, y0, z0), P(x1, y0, z0), P(x1, y0, z1), P(x0, y0, z1)],
        "s": [P(x1, y1, z0), P(x0, y1, z0), P(x0, y1, z1), P(x1, y1, z1)],
        "w": [P(x0, y1, z0), P(x0, y0, z0), P(x0, y0, z1), P(x0, y1, z1)],
        "e": [P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)],
    }
    tris = []
    for k, p in faces.items():
        tris += quad_tris(p, mats.get(k, mat))
    return Mesh()._orient(tris, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))


def prism(poly, z0, z1, mat, top=None, bottom=None):
    """Vertical prism over a convex polygon (list of (x,y)); sides wrap the tile once around."""
    n = len(poly)
    cx, cy = sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    tris = []
    f = uvbox(mat)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        u0, u1 = i / n, (i + 1) / n
        A, B, C, D = (a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)
        tris += [((A, f(u0, 1)), (B, f(u1, 1)), (C, f(u1, 0))), ((A, f(u0, 1)), (C, f(u1, 0)), (D, f(u0, 0)))]
    for z, m in ((z1, top or mat), (z0, bottom or mat)):
        g = uvbox(m)
        c = ((cx, cy, z), g(0.5, 0.5))
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            ua = lambda p: g(0.5 + (p[0] - cx) * 0.5 / max(1e-6, max(abs(q[0] - cx) for q in poly)), 0.5 + (p[1] - cy) * 0.5 / max(1e-6, max(abs(q[1] - cy) for q in poly)))
            tris.append((c, ((a[0], a[1], z), ua(a)), ((b[0], b[1], z), ua(b))))
    return Mesh()._orient(tris, (cx, cy, (z0 + z1) / 2))


def cylinder(cx, cy, z0, z1, r, n, mat, top=None, bottom=None, r1=None):
    """Vertical cylinder / frustum (r at z0, r1 at z1)."""
    r1 = r if r1 is None else r1
    if abs(r - r1) < 1e-9:
        return prism([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)], z0, z1, mat, top, bottom)
    tris = []
    f = uvbox(mat)
    ring = lambda rr, z: [(cx + rr * math.cos(2 * math.pi * i / n), cy + rr * math.sin(2 * math.pi * i / n), z) for i in range(n)]
    lo, hi = ring(r, z0), ring(r1, z1)
    for i in range(n):
        j = (i + 1) % n
        u0, u1 = i / n, (i + 1) / n
        if r1 > 1e-6:
            tris += [((lo[i], f(u0, 1)), (lo[j], f(u1, 1)), (hi[j], f(u1, 0))), ((lo[i], f(u0, 1)), (hi[j], f(u1, 0)), (hi[i], f(u0, 0)))]
        else:
            tris.append(((lo[i], f(u0, 1)), (lo[j], f(u1, 1)), (hi[i], f((u0 + u1) / 2, 0))))
        if r > 1e-6 and r1 <= 1e-6: pass
    for z, rr, m, pts in ((z0, r, bottom or mat, lo), (z1, r1, top or mat, hi)):
        if rr <= 1e-6: continue
        g = uvbox(m)
        c = ((cx, cy, z), g(0.5, 0.5))
        for i in range(n):
            j = (i + 1) % n
            tris.append((c, (pts[i], g(0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 + 0.5 * math.sin(2 * math.pi * i / n))),
                         (pts[j], g(0.5 + 0.5 * math.cos(2 * math.pi * j / n), 0.5 + 0.5 * math.sin(2 * math.pi * j / n)))))
    return Mesh()._orient(tris, (cx, cy, (z0 + z1) / 2))


def rot_x(m, cx, cy, cz, deg=90):
    """Rotate a mesh about the x axis through (cx, cy, cz) (used for wheels lying on their side)."""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return m.transformed(lambda p: (p[0], cy + (p[1] - cy) * c - (p[2] - cz) * s, cz + (p[1] - cy) * s + (p[2] - cz) * c))


def rot_y(m, cx, cy, cz, deg=90):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return m.transformed(lambda p: (cx + (p[0] - cx) * c + (p[2] - cz) * s, p[1], cz - (p[0] - cx) * s + (p[2] - cz) * c))


def wheel(cx, cy, cz, r, w, axis="y", n=12):
    """A wheel: tyre cylinder + hub caps, axle along y (car moving along x) or x."""
    m = cylinder(cx, cy, cz - w / 2, cz + w / 2, r, n, "rubber", top="chrome", bottom="chrome")
    return rot_x(m, cx, cy, cz) if axis == "y" else rot_y(m, cx, cy, cz)


def card(p, mat, uv=None):
    """A double-sided flat quad (flags, banners, canopy undersides)."""
    return Mesh()._orient(quad_tris(p, mat, uv), both=True)


def pyramid(cx, cy, z0, z1, hw, hd, mat, apex_hw=0.0, apex_hd=0.0, both=False, under=None):
    """Hip roof / canopy: rectangle at z0 to a smaller rectangle (or point) at z1."""
    lo = [(cx - hw, cy - hd, z0), (cx + hw, cy - hd, z0), (cx + hw, cy + hd, z0), (cx - hw, cy + hd, z0)]
    hi = [(cx - apex_hw, cy - apex_hd, z1), (cx + apex_hw, cy - apex_hd, z1), (cx + apex_hw, cy + apex_hd, z1), (cx - apex_hw, cy + apex_hd, z1)]
    f = uvbox(mat)
    tris = []
    for i in range(4):
        j = (i + 1) % 4
        tris += [((lo[i], f(0, 1)), (lo[j], f(1, 1)), (hi[j], f(0.5 + apex_hw / max(hw, 1e-6) / 2, 0))),
                 ((lo[i], f(0, 1)), (hi[j], f(0.5 + apex_hw / max(hw, 1e-6) / 2, 0)), (hi[i], f(0.5 - apex_hw / max(hw, 1e-6) / 2, 0)))]
    tris = [t for t in tris if len({t[0][0], t[1][0], t[2][0]}) == 3]
    m = Mesh()._orient(tris, (cx, cy, z0 - 0.01))
    if under:                                                     # underside, seen from below
        g = uvbox(under)
        u = [(lo[0], g(0, 0)), (lo[1], g(1, 0)), (lo[2], g(1, 1)), (lo[3], g(0, 1))]
        m._orient([(u[0], u[1], u[2]), (u[0], u[2], u[3])], (cx, cy, z0 + 1))
    if apex_hw > 0:
        g = uvbox(mat)
        t = [(hi[0], g(0, 0)), (hi[1], g(1, 0)), (hi[2], g(1, 1)), (hi[3], g(0, 1))]
        m._orient([(t[0], t[1], t[2]), (t[0], t[2], t[3])], (cx, cy, z1 - 1))
    return m


def gable_roof(x0, x1, cy, hd, z0, z1, mat, under="wood_dark", overhang_end=0.0):
    """Thai-style steep gable along x: eaves at y = cy +- hd, ridge at z1. Closed (with underside)."""
    xa, xb = x0 - overhang_end, x1 + overhang_end
    A, B = (xa, cy - hd, z0), (xb, cy - hd, z0)
    C, D = (xb, cy + hd, z0), (xa, cy + hd, z0)
    R0, R1 = (xa, cy, z1), (xb, cy, z1)
    f = uvbox(mat); g = uvbox(under); w = uvbox("white_trim")
    tris = [((A, f(0, 1)), (B, f(1, 1)), (R1, f(1, 0))), ((A, f(0, 1)), (R1, f(1, 0)), (R0, f(0, 0))),
            ((C, f(0, 1)), (D, f(1, 1)), (R0, f(1, 0))), ((C, f(0, 1)), (R0, f(1, 0)), (R1, f(0, 0))),
            ((A, g(0, 0)), (D, g(0, 1)), (C, g(1, 1))), ((A, g(0, 0)), (C, g(1, 1)), (B, g(1, 0))),
            ((A, w(0, 1)), (R0, w(0.5, 0)), (D, w(1, 1))), ((B, w(0, 1)), (C, w(1, 1)), (R1, w(0.5, 0)))]
    return Mesh()._orient(tris, ((xa + xb) / 2, cy, z0 + (z1 - z0) / 3))


# ── the models ───────────────────────────────────────────────────────────────────────────
def m_songthaew():
    """Chiang Mai red truck (rot daeng): pickup with a covered bench back. Faces +x. 20 x 7.4 x 9."""
    m = Mesh()
    L, W = 20.0, 7.0
    hw = W / 2
    # chassis and wheels
    m.add(box(-10, -hw + 0.4, 1.2, 10, hw - 0.4, 2.2, "black"))
    for x in (-6.5, 6.5):
        for y in (-hw + 0.9, hw - 0.9):
            m.add(wheel(x, y, 1.7, 1.7, 1.3, "y"))
    # cab and bonnet
    m.add(box(4.0, -hw, 2.2, 10.0, hw, 4.6, "red_paint", {"e": "red_paint"}))          # bonnet + front
    m.add(box(9.9, -hw + 0.3, 2.4, 10.25, hw - 0.3, 3.4, "chrome"))                     # bumper / grille
    for y in (-hw + 1.0, hw - 1.6):
        m.add(box(9.95, y, 3.6, 10.2, y + 0.6, 4.2, "headlight"))
    m.add(box(9.95, -1.1, 2.5, 10.2, 1.1, 3.0, "plate"))
    m.add(box(1.0, -hw, 4.6, 4.0, hw, 7.4, "red_paint", {"e": "glass", "n": "glass", "s": "glass"}))   # cab with windows
    m.add(box(1.0, -hw, 2.2, 4.0, hw, 4.6, "red_paint"))
    m.add(box(0.9, -hw - 0.05, 7.4, 4.1, hw + 0.05, 7.7, "red_dark"))                   # cab roof
    # the back: floor, benches, side rails, posts and the roof
    m.add(box(-10, -hw, 2.2, 1.0, hw, 3.0, "red_paint"))                                 # load bed
    for y in (-hw, hw - 0.4):
        m.add(box(-10, y, 3.0, 1.0, y + 0.4, 4.6, "red_paint"))                         # side walls
        m.add(box(-9.6, y + (0.4 if y < 0 else -1.4), 3.0, 0.6, y + (1.4 if y < 0 else -0.4), 4.0, "vinyl"))   # benches
    for x in (-9.9, -5.0, 0.7):
        for y in (-hw, hw - 0.3):
            m.add(box(x, y, 4.6, x + 0.3, y + 0.3, 8.4, "chrome"))                       # roof posts
    m.add(box(-10.2, -hw - 0.2, 8.4, 1.2, hw + 0.2, 8.9, "red_paint", {"top": "red_dark"}))   # roof
    m.add(box(-10.2, -hw - 0.2, 8.9, -1.0, hw + 0.2, 9.2, "chrome"))                     # roof rack
    m.add(box(-10.4, -hw + 0.6, 2.0, -10.0, hw - 0.6, 2.4, "chrome"))                    # rear step
    return m


def m_tuktuk():
    """Tuk-tuk: one front wheel, two rear, canopy. Faces +x. 11 x 5.6 x 7.5."""
    m = Mesh()
    m.add(wheel(4.4, 0, 1.1, 1.1, 0.7, "y"))
    for y in (-2.3, 2.3):
        m.add(wheel(-3.2, y, 1.1, 1.1, 0.8, "y"))
    m.add(box(-4.8, -2.6, 1.4, 1.5, 2.6, 2.4, "blue_paint"))                             # body floor
    m.add(box(1.5, -1.3, 1.4, 5.2, 1.3, 2.6, "blue_paint", {"top": "black"}))           # driver section
    m.add(box(4.6, -1.0, 1.6, 5.4, 1.0, 4.4, "blue_paint", {"e": "chrome"}))            # front fairing
    m.add(box(5.3, -0.4, 3.4, 5.5, 0.4, 4.0, "headlight"))
    m.add(box(1.8, -0.6, 2.6, 3.0, 0.6, 3.5, "vinyl"))                                  # driver seat
    m.add(box(-4.6, -2.4, 2.4, -2.6, 2.4, 3.4, "vinyl"))                                # passenger bench
    m.add(box(-4.8, -2.6, 2.4, -4.3, 2.6, 5.0, "vinyl"))                                # bench back
    m.add(box(4.0, -1.8, 4.2, 4.2, 1.8, 4.4, "chrome"))                                 # handlebar
    for x, y in ((-4.8, -2.6), (-4.8, 2.4), (4.5, -1.2), (4.5, 1.0)):
        m.add(box(x, y, 2.4, x + 0.2, y + 0.2, 7.0, "chrome"))                          # canopy posts
    m.add(box(-5.2, -2.9, 7.0, 4.9, 2.9, 7.5, "yellow_paint", {"bottom": "black"}))     # canopy
    m.add(box(-5.25, -2.95, 6.4, 4.95, 2.95, 7.0, "green_paint", {"top": "yellow_paint", "bottom": "black"}))  # valance
    m.add(box(4.9, -1.2, 4.4, 5.0, 1.2, 6.4, "glass"))                                  # windscreen
    return m


def m_parasol(mat):
    """Big square market umbrella, 11 wide, canopy edge at 8, apex 10. Pole in the middle."""
    m = Mesh()
    m.add(cylinder(0, 0, 0, 0.6, 1.0, 8, "black"))                                      # weighted base
    m.add(cylinder(0, 0, 0.6, 10.2, 0.15, 6, "steel"))
    m.add(pyramid(0, 0, 8.0, 10.0, 5.5, 5.5, mat, apex_hw=0.25, apex_hd=0.25, under=mat))
    for k in range(4):                                                                  # valance flaps
        a = [(-5.5, -5.5), (5.5, -5.5), (5.5, 5.5), (-5.5, 5.5)]
        p, q = a[k], a[(k + 1) % 4]
        m.add(card([(p[0], p[1], 7.4), (q[0], q[1], 7.4), (q[0], q[1], 8.0), (p[0], p[1], 8.0)], mat))
    return m


def m_spirit_house():
    """San phra phum: a little Thai house on a post, gold roof finials. 3.4 wide, 8.4 tall."""
    m = Mesh()
    m.add(box(-0.9, -0.9, 0, 0.9, 0.9, 0.4, "white"))
    m.add(cylinder(0, 0, 0.4, 4.4, 0.35, 8, "white_trim"))
    m.add(box(-1.7, -1.7, 4.4, 1.7, 1.7, 4.8, "white_trim"))                            # platform
    for x, y in ((-1.6, -1.6), (1.4, -1.6), (1.4, 1.4), (-1.6, 1.4)):
        m.add(box(x, y, 4.8, x + 0.2, y + 0.2, 5.2, "gold"))                            # balustrade posts
    m.add(box(-1.0, -0.8, 4.8, 1.0, 0.8, 6.4, "white", {"e": "gold"}))                  # the house, door east
    m.add(gable_roof(-1.0, 1.0, 0, 1.3, 6.4, 7.9, "roof_orange", overhang_end=0.4))
    m.add(gable_roof(-0.6, 0.6, 0, 0.9, 7.3, 8.4, "roof_green", overhang_end=0.2))      # second tier
    for x in (-1.6, 1.6):
        m.add(box(x - 0.08, -0.08, 7.9, x + 0.08, 0.08, 8.9, "gold"))                   # chofa finials
    m.add(box(1.0, -0.5, 4.8, 1.5, 0.5, 5.0, "mango"))                                  # offerings
    return m


def lantern(cx, cy, ztop, mat, s=1.0):
    """Lanna paper lantern (khom): bulging ribbed body, gold rims, tassel; hangs from ztop."""
    m = Mesh()
    h = 2.2 * s
    z1, z0 = ztop - 0.3 * s, ztop - 0.3 * s - h
    rs = [0.45, 0.85, 1.0, 0.85, 0.45]
    for i in range(4):
        za = z0 + h * i / 4; zb = z0 + h * (i + 1) / 4
        m.add(cylinder(cx, cy, za, zb, rs[i] * s, 10, mat, r1=rs[i + 1] * s))
    m.add(cylinder(cx, cy, z1, z1 + 0.15 * s, 0.5 * s, 8, "gold"))
    m.add(cylinder(cx, cy, z0 - 0.15 * s, z0, 0.5 * s, 8, "gold"))
    m.add(cylinder(cx, cy, z0 - 1.2 * s, z0 - 0.15 * s, 0.18 * s, 6, "gold", r1=0.1 * s))   # tassel
    m.add(box(cx - 0.04, cy - 0.04, z1 + 0.15 * s, cx + 0.04, cy + 0.04, ztop, "rope"))
    return m


def m_khom():
    """A single hanging lantern, top at z=0 (place it with an elevation)."""
    m = lantern(0, 0, 0, "lantern_red", 1.0)
    m.add(box(-0.05, -0.05, 0, 0.05, 0.05, 2.0, "rope"))
    return m


def m_khom_string():
    """A string of lanterns across a street: 24 long (along y), rope sagging from 12 to 10.5."""
    m = Mesh()
    pts = [(-12 + 24 * i / 12, 12 - 1.5 * (1 - ((i - 6) / 6) ** 2)) for i in range(13)]
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        m.add(Mesh()._orient(quad_tris([(0, y0, z0 - 0.06), (0, y1, z1 - 0.06), (0, y1, z1 + 0.06), (0, y0, z0 + 0.06)], "rope"), both=True))
    for k, i in enumerate((2, 4, 6, 8, 10)):
        y, z = pts[i]
        m.add(lantern(0, y, z, "lantern_red" if k % 2 == 0 else "lantern_orange", 0.8))
    return m


def m_longtail():
    """Long-tail boat (ruea hang yao): an open wooden hull with a painted band, thwarts, a raised bow
    with a garland, the engine on a long shaft at the stern. Faces +x, waterline at z = 0.5. 34 x 4.6.
    The hull is a shell: outer skin, inner skin and a gunwale strip joining them, so it reads as a
    boat from any side."""
    m = Mesh()
    # sections along x: (x, half width at gunwale, keel z, gunwale z)
    secs = [(-15, 1.6, 0.0, 2.0), (-10, 2.2, -0.2, 1.9), (0, 2.3, -0.3, 1.8), (8, 2.0, -0.2, 2.0), (13, 1.2, 0.2, 2.6), (17, 0.15, 1.2, 4.2)]
    T = 0.22                                                   # plank thickness
    outer = lambda x, w, k, g: [(x, -w, g), (x, -w * 0.55, k), (x, w * 0.55, k), (x, w, g)]          # starboard top -> keel -> port top
    def inner(x, w, k, g):
        wi = max(0.02, w - T); ki = k + T
        return [(x, -wi, g), (x, -wi * 0.55, ki), (x, wi * 0.55, ki), (x, wi, g)]
    O = [outer(*s_) for s_ in secs]; I = [inner(*s_) for s_ in secs]
    f, g, band = uvbox("wood"), uvbox("wood_dark"), uvbox("blue_paint")
    tris = []
    def quad(a, b, c, d_, uvf, want):                          # want: a point the face must face towards
        t1, t2 = ((a, uvf(0, 0)), (b, uvf(1, 0)), (c, uvf(1, 1))), ((a, uvf(0, 0)), (c, uvf(1, 1)), (d_, uvf(0, 1)))
        for t in (t1, t2):
            (p0, _), (p1, _), (p2, _) = t
            n = _cross(_sub(p1, p0), _sub(p2, p0))
            mid = tuple((p0[i] + p1[i] + p2[i]) / 3 for i in range(3))
            tris.append(t if _dot(n, _sub(want(mid), mid)) >= 0 else (t[0], t[2], t[1]))
    away = lambda mid: (mid[0], mid[1] * 3, mid[2] - 3)             # outer skin faces away from the axis
    axis = lambda mid: (mid[0], 0.0, mid[2] + 3.0)                   # inner skin faces the inside and up
    up = lambda mid: (mid[0], mid[1], mid[2] + 5)
    for j in range(len(secs) - 1):
        for k in range(3):                                          # 3 strakes per side: side, bottom, side
            quad(O[j][k], O[j + 1][k], O[j + 1][k + 1], O[j][k + 1], band if k != 1 and False else (f if k != 1 else g), away)
            quad(I[j][k], I[j + 1][k], I[j + 1][k + 1], I[j][k + 1], g, axis)
        for k in (0, 3):                                            # gunwale strips joining outer and inner tops
            quad(O[j][k], O[j + 1][k], I[j + 1][k], I[j][k], band, up)
    for (Os, Is, want) in ((O[0], I[0], lambda mid: (mid[0] - 5, mid[1], mid[2])), (O[-1], Is_ := I[-1], lambda mid: (mid[0] + 5, mid[1], mid[2]))):
        for k in range(3):                                          # end caps (transom, bow) between the skins
            quad(Os[k], Os[k + 1], Is[k + 1], Is[k], f, want)
    m.tris += tris
    m.add(box(16.5, -0.5, 3.8, 17.6, 0.5, 4.8, "garland"))                              # bow garland
    for x in (-8, -2, 4):
        m.add(box(x, -2.05, 1.2, x + 0.8, 2.05, 1.5, "wood_dark"))                      # thwarts (seats)
    m.add(box(-16.8, -0.9, 2.0, -14.6, 0.9, 3.8, "engine"))                             # engine on the stern
    m.add(rot_y(cylinder(-16.4, 0, 2.6, 13.6, 0.18, 6, "steel"), -16.4, 0, 2.6, deg=-100))   # long shaft astern
    m.add(box(-14.4, -0.08, 3.2, -13.6, 0.08, 4.2, "steel"))                            # tiller
    return m


def m_baskets():
    """Three woven baskets heaped with fruit, for a stall counter (place on the counter's floor)."""
    m = Mesh()
    for (x, y, r) in ((-1.6, 0, 0.9), (0.4, 0.3, 0.8), (2.1, -0.2, 0.7)):
        m.add(cylinder(x, y, 0, 0.9, r * 0.8, 10, "basket", top="mango", r1=r))
    m.add(box(-2.6, -1.4, 0, 2.9, -0.9, 0.5, "mango"))                                  # a low tray in front
    return m


def m_tung():
    """Lanna prayer banner (tung) on a bamboo pole: pole 16 high, banner 1.6 wide, 9 long."""
    m = Mesh()
    m.add(cylinder(0, 0, 0, 16, 0.18, 6, "wood"))
    m.add(box(-0.1, -0.1, 15.0, 2.2, 0.1, 15.2, "wood"))                                # cross arm
    m.add(card([(0.4, 0, 5.8), (2.0, 0, 5.8), (2.0, 0, 15.0), (0.4, 0, 15.0)], "tung"))
    return m


def m_thai_flag():
    """Thai national flag on a white pole: pole 18, flag 6 x 4."""
    m = Mesh()
    m.add(cylinder(0, 0, 0, 18, 0.15, 6, "white", top="gold"))
    m.add(cylinder(0, 0, 18, 18.4, 0.3, 6, "gold"))
    m.add(card([(0.2, 0, 13.6), (6.2, 0, 13.6), (6.2, 0, 17.6), (0.2, 0, 17.6)], "thai_flag",
               ((0, 1), (1, 1), (1, 0), (0, 0))))
    return m


def m_foodset():
    """Street food corner: a steel table with four red plastic stools. 8 x 8."""
    m = Mesh()
    m.add(box(-1.8, -1.2, 2.6, 1.8, 1.2, 2.8, "steel"))
    for x in (-1.6, 1.4):
        for y in (-1.0, 0.8):
            m.add(box(x, y, 0, x + 0.2, y + 0.2, 2.6, "steel"))
    for x, y in ((-3.2, 0), (3.2, 0), (0, -2.6), (0, 2.6)):
        m.add(cylinder(x, y, 0, 1.6, 0.7, 8, "plastic_red", r1=0.55))
    m.add(box(-0.6, -0.4, 2.8, 0.6, 0.4, 3.2, "basket"))                                # a basket of sticky rice
    return m


def m_fruitstall():
    """A wooden fruit table heaped with mangoes and baskets, under a blue tarp on four poles. 8 x 5."""
    m = Mesh()
    m.add(box(-4, -2.4, 0, 4, 2.4, 2.8, "wood", {"top": "mango"}))
    for x in (-3, 0, 3):
        m.add(cylinder(x, 1.2, 2.8, 3.8, 0.9, 8, "basket", top="mango"))
    for x, y in ((-4, -2.4), (3.8, -2.4), (-4, 2.2), (3.8, 2.2)):
        m.add(box(x, y, 2.8, x + 0.2, y + 0.2, 8.6, "wood_dark"))
    m.add(pyramid(0, 0, 8.4, 9.2, 4.6, 3.0, "tarp_blue", apex_hw=4.0, apex_hd=0.2, under="tarp_blue"))
    return m


def m_sala():
    """Sala: open Thai pavilion, 12 x 8 platform, 6 posts, two-tier gable roof with chofa finials.
    Purely visual (its slot has no collision height): place it on a 1-high raised floor of the same size."""
    m = Mesh()
    for x in (-5.4, -0.2, 5.0):
        for y in (-3.4, 3.0):
            m.add(cylinder(x + 0.2, y + 0.2, 0, 8.0, 0.3, 8, "red_dark"))
    m.add(box(-6.0, -4.0, 7.6, 6.0, 4.0, 8.0, "red_dark"))                               # tie beams
    m.add(gable_roof(-5.6, 5.6, 0, 5.2, 8.0, 12.4, "roof_orange", overhang_end=0.6))
    m.add(gable_roof(-3.2, 3.2, 0, 3.2, 11.0, 14.2, "roof_orange", overhang_end=0.4))
    m.add(box(-6.6, -0.12, 8.0, -6.3, 0.12, 13.6, "gold")); m.add(box(6.3, -0.12, 8.0, 6.6, 0.12, 13.6, "gold"))
    m.add(box(-3.95, -0.1, 11.0, -3.7, 0.1, 15.4, "gold")); m.add(box(3.7, -0.1, 11.0, 3.95, 0.1, 15.4, "gold"))
    for y in (-4.6, 4.6):                                                                 # green trim on the eaves
        m.add(box(-6.2, y - 0.15, 7.8, 6.2, y + 0.15, 8.1, "roof_green"))
    return m


# ── Khmer architecture (ac_wat): parametric, generated per map ─────────────────────────────
def _orient_from(tris, centre):
    return Mesh()._orient(tris, centre)


def cyl_between(p0, p1, r0, r1, n, mat, cap=True):
    """A frustum from p0 (radius r0) to p1 (radius r1) along any direction."""
    ax = _sub(p1, p0); L = math.sqrt(_dot(ax, ax)); w = tuple(c / L for c in ax)
    a = (1.0, 0, 0) if abs(w[0]) < 0.9 else (0, 1.0, 0)
    u = _cross(w, a); lu = math.sqrt(_dot(u, u)); u = tuple(c / lu for c in u); v = _cross(w, u)
    ring = lambda c, r: [tuple(c[i] + r * (math.cos(2 * math.pi * k / n) * u[i] + math.sin(2 * math.pi * k / n) * v[i]) for i in range(3)) for k in range(n)]
    lo, hi = ring(p0, r0), ring(p1, max(r1, 1e-4))
    f = uvbox(mat); tris = []
    for k in range(n):
        j = (k + 1) % n
        tris += [((lo[k], f(k / n, 1)), (lo[j], f((k + 1) / n, 1)), (hi[j], f((k + 1) / n, 0))),
                 ((lo[k], f(k / n, 1)), (hi[j], f((k + 1) / n, 0)), (hi[k], f(k / n, 0)))]
    if cap:
        for c, pts in ((p0, lo), (p1, hi)):
            for k in range(n):
                tris.append(((c, f(0.5, 0.5)), (pts[k], f(0, 0)), (pts[(k + 1) % n], f(1, 0))))
    centre = tuple((p0[i] + p1[i]) / 2 for i in range(3))
    return Mesh()._orient([t for t in tris if len({t[0][0], t[1][0], t[2][0]}) == 3], centre)


def m_gallery_roof(W, L, H, mat="khmer_roof"):
    """Khmer gallery roof segment, centred on the origin: W across (x), L along (y), eaves at z = 0,
    ridge at H. Concave stone-tile profile with fascia, closed underside (the gallery ceiling), carved
    gable ends and a ridge cap. Segments placed end to end form a continuous roof."""
    a, b = W / 2 + 0.7, W / 4
    prof = [(-a, 0.0), (a, 0.0), (a, 0.45), (b, 0.6 * H), (0.0, H), (-b, 0.6 * H), (-a, 0.45)]
    y0, y1 = -L / 2, L / 2
    roof, gab, ceil, fas = uvbox(mat), uvbox("khmer_gable"), uvbox("khmer_ceiling"), uvbox("ac12")
    tris = []
    n = len(prof)
    for i in range(n):
        (xa, za), (xb, zb) = prof[i], prof[(i + 1) % n]
        if i == 0:   g = ceil
        elif i in (1, 6): g = fas
        else:        g = roof
        A, B, C, D = (xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)
        tris += [((A, g(0, 1)), (B, g(1, 1)), (C, g(1, 0))), ((A, g(0, 1)), (C, g(1, 0)), (D, g(0, 0)))]
    for y in (y0, y1):                                           # gable ends: fan from an inner point
        c = (0.0, y, 0.3 * H)
        for i in range(n):
            (xa, za), (xb, zb) = prof[i], prof[(i + 1) % n]
            tris.append(((c, gab(0.5, 0.6)), ((xa, y, za), gab(0.5 + xa / (2 * a), 1 - za / H)), ((xb, y, zb), gab(0.5 + xb / (2 * a), 1 - zb / H))))
    m = Mesh()
    for t in tris:                                               # orient each face away from the roof's core line
        (p0, _), (p1, _), (p2, _) = t
        nrm = _cross(_sub(p1, p0), _sub(p2, p0))
        mid = tuple((p0[i] + p1[i] + p2[i]) / 3 for i in range(3))
        core = (0.0, max(y0 + 0.01, min(y1 - 0.01, mid[1])) if abs(abs(mid[1]) - L / 2) > 1e-6 else 0.0, 0.3 * H)
        m.tris.append(t if _dot(nrm, _sub(mid, core)) >= 0 else (t[0], t[2], t[1]))
    m.add(box(-0.3, y0, H - 0.15, 0.3, y1, H + 0.35, mat, {"top": "ac12"}))                # ridge cap
    return m


def _drop(m):
    """Move a mesh so its lowest point lies at z = 0."""
    z0 = min(p[2] for t in m.tris for p, _ in t)
    return m.transformed(lambda p: (p[0], p[1], p[2] - z0))


def m_pavilion_roof(W, L, H, tiers=3, finial=3.0):
    """Stepped Khmer pavilion / gopura roof, centred: tiers of hip roofs with upright bands between,
    a lotus finial on top. Eaves at z = 0, W x L footprint (plus overhang)."""
    m = Mesh()
    z = 0.0
    hw, hl = W / 2 + 0.7, L / 2 + 0.7
    dz = H / tiers
    for k in range(tiers):
        top_hw, top_hl = hw * 0.62, hl * 0.62 if L != W else hw * 0.62
        m.add(pyramid(0, 0, z, z + dz * 0.75, hw, hl, "khmer_roof", apex_hw=top_hw, apex_hd=top_hl, under="khmer_ceiling"))
        m.add(box(-top_hw * 0.92, -top_hl * 0.92, z + dz * 0.75, top_hw * 0.92, top_hl * 0.92, z + dz, "ac12", {"top": "khmer_roof", "bottom": "khmer_ceiling"}))
        z += dz; hw, hl = top_hw * 0.92, top_hl * 0.92
    r = max(0.5, min(hw, hl) * 0.35)                    # a small stone lotus bud, never a thin spike
    finial = min(finial, 2.4 * r)
    m.add(cylinder(0, 0, z, z + finial * 0.3, r * 0.7, 10, "ac12", r1=r))
    m.add(cylinder(0, 0, z + finial * 0.3, z + finial * 0.65, r, 10, "ac12", r1=r * 0.75))
    m.add(cylinder(0, 0, z + finial * 0.65, z + finial, r * 0.75, 10, "ac12", r1=r * 0.3))
    return m


def m_lid(w, d, h, top, u0, v0, side="ac12"):
    """A stone block (secret-passage lid), corner at the origin: x 0..w, y 0..d, z 0..h. The top face
    continues the AC floor texture `top` (atlas copy) with world-aligned UVs starting at (u0, v0) in
    texture periods (a 256 px texture repeats every 8 cubes), so it blends into the floor around it."""
    T = 8.0
    t = uvbox(top, u0, v0, u0 + w / T, v0 + d / T)
    tris = []
    P = [(0, 0, h), (w, 0, h), (w, d, h), (0, d, h)]
    U = [t(0, 0), t(1, 0), t(1, 1), t(0, 1)]
    q = list(zip(P, U))
    tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    sd = uvbox(side, 0, 0, 1, min(1.0, h / T))
    for (a, b_) in (((0, 0), (w, 0)), ((w, 0), (w, d)), ((w, d), (0, d)), ((0, d), (0, 0))):
        A, B, C, D = (a[0], a[1], 0), (b_[0], b_[1], 0), (b_[0], b_[1], h), (a[0], a[1], h)
        tris += [((A, sd(0, 1)), (B, sd(1, 1)), (C, sd(1, 0))), ((A, sd(0, 1)), (C, sd(1, 0)), (D, sd(0, 0)))]
    c = uvbox("khmer_ceiling")
    Bt = [((0, 0, 0), c(0, 0)), ((w, 0, 0), c(1, 0)), ((w, d, 0), c(1, 1)), ((0, d, 0), c(0, 1))]
    tris += [(Bt[0], Bt[1], Bt[2]), (Bt[0], Bt[2], Bt[3])]
    return Mesh()._orient(tris, (w / 2, d / 2, h / 2))


def extrude_x(poly_yz, x0, x1, mat, cap=None):
    """Extrude a convex polygon given in the (y, z) plane along x from x0 to x1 (closed)."""
    n = len(poly_yz)
    f, g = uvbox(mat), uvbox(cap or mat)
    cy = sum(p[0] for p in poly_yz) / n; cz = sum(p[1] for p in poly_yz) / n
    ys = [p[0] for p in poly_yz]; zs = [p[1] for p in poly_yz]
    uy = lambda y: (y - min(ys)) / max(1e-6, max(ys) - min(ys)); vz = lambda z: 1 - (z - min(zs)) / max(1e-6, max(zs) - min(zs))
    tris = []
    for i in range(n):
        (ya, za), (yb, zb) = poly_yz[i], poly_yz[(i + 1) % n]
        A, B, C, D = (x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)
        tris += [((A, f(i / n, 0)), (B, f((i + 1) / n, 0)), (C, f((i + 1) / n, 1))), ((A, f(i / n, 0)), (C, f((i + 1) / n, 1)), (D, f(i / n, 1)))]
    for x in (x0, x1):
        c = ((x, cy, cz), g(0.5, 0.5))
        for i in range(n):
            (ya, za), (yb, zb) = poly_yz[i], poly_yz[(i + 1) % n]
            tris.append((c, ((x, ya, za), g(uy(ya), vz(za))), ((x, yb, zb), g(uy(yb), vz(zb)))))
    return Mesh()._orient(tris, ((x0 + x1) / 2, cy, cz))


def m_logo_plaque():
    """A small stone plaque, 1 x 1 cube, painted with the cubeLadder icon. The engine draws our meshes
    mirrored in x (model +x points west at yaw 0, checked in game), so the back sits at model x = +1 and
    the icon on the -x face: the entity stands one cell out from the wall (yaw 0: wall to the west, 1800:
    to the east)."""
    m = Mesh()
    m.add(box(0.9, -0.5, 0, 1.0, 0.5, 1.0, "ac12", {"w": "cl_logo"}))
    return m


def m_qr(rows, size, up=True, flip=False, ox=0.0, oy=0.0, quiet=3, oz=0.0):
    """A QR code as geometry, not as a texture: a light plate with every dark module a thin raised black
    block (runs of dark modules in a row merged into one block). Nothing of it is in the atlas image, so
    the code cannot be read off the model pack without rendering the model. rows: the module matrix as
    strings of '0'/'1'. size: the plate's edge (cubes); quiet: light modules around the code. up: faces +z
    (lies on a floor, its top at z = 0) or -z (hangs under something, its back at z = 0). flip mirrors
    the matrix in x: the engine draws our meshes mirrored in x, and seeing a plate from below mirrors it
    once more, so the caller picks flip to make the code read the right way round in game.
    oz lifts the whole code inside the model: a mapmodel's height is stored in steps of 0.2 cubes
    (attr3 / 5), so the caller places it at a storable height and passes the remainder here (a code
    meant to lie 0.02 above a surface was rounded 0.04 into the stone and vanished)."""
    n = len(rows)
    mod = size / (n + 2 * quiet)
    t, r_ = 0.12, 0.03                                   # plate thickness (reaches into the surface below), raise of the dark modules
    m = Mesh()
    h = size / 2
    if up:
        m.add(box(ox - h, oy - h, oz - t, ox + h, oy + h, oz, "cl_white"))
    else:
        m.add(box(ox - h, oy - h, oz, ox + h, oy + h, oz + t, "cl_white"))
    for y, row in enumerate(rows):
        row = row[::-1] if flip else row
        x = 0
        while x < n:
            if row[x] != "1":
                x += 1
                continue
            x1 = x
            while x1 < n and row[x1] == "1":
                x1 += 1
            ax0 = ox - h + (quiet + x) * mod
            ax1 = ox - h + (quiet + x1) * mod
            ay0 = oy - h + (quiet + y) * mod
            ay1 = ay0 + mod
            m.add(box(ax0, ay0, oz, ax1, ay1, oz + r_, "black") if up else box(ax0, ay0, oz - r_, ax1, ay1, oz, "black"))
            x = x1
    return m


def m_ledge(w=4.0, d=4.0, t=1.2):
    """A stone block sticking out of a wall (or hanging free) as a jump platform, its top at z = 0."""
    m = Mesh()
    m.add(box(-w / 2, -d / 2, -t, w / 2, d / 2, 0, "ac12", {"top": "ac12_moss"}))
    return m


def m_lintel(w=4.0, d=2.0, h=16.0):
    """Wall above a window: a block w x d from z = -h up to 0, cut into courses about 1.5 high so the
    stone texture keeps its scale."""
    m = Mesh()
    n = max(1, round(h / 1.5))
    for i in range(n):
        m.add(segbox(-w / 2, -d / 2, -h + h * i / n, w / 2, d / 2, -h + h * (i + 1) / n, "ac12"))
    return m


def m_block_stack():
    """Cover: three big sandstone blocks fallen on each other, two on the ground and one across them,
    about 3.6 square and 5 tall (a player hides behind it, nobody jumps on it)."""
    m = Mesh()
    m.add(rot_z(box(-1.75, -1.55, 0, 0.05, 1.55, 2.5, "ac12", {"top": "ac12_moss"}), -0.85, 0, 4))
    m.add(rot_z(box(0.2, -1.45, 0, 1.75, 1.35, 2.3, "ac12", {"top": "ac12_moss"}), 1.0, 0, -6))
    m.add(rot_z(box(-1.35, -1.15, 2.3, 1.3, 1.1, 5.0, "ac12", {"top": "ac12_moss"}), 0, 0, 11))
    return m


def m_cl_logo(L=0.75, splash=1.0):
    """The cubeLadder logo in 3D, faces +x, standing at z = 0: a white cube (turned 45 degrees, dark-blue
    outlined edges, blue paint dripping down its sides, a QR code to cubeladder.ovh on its top), a blue
    paint splash round its foot and a blue ladder leaning on its front edge. L scales it (1: cube 1.7)."""
    m = Mesh()
    top = 0.0
    sp = [((1.75 + 0.45 * math.sin(a * 3.7)) * L * splash * math.cos(math.radians(a)),
           (1.75 + 0.45 * math.sin(a * 3.7)) * L * splash * math.sin(math.radians(a))) for a in range(0, 360, 15)]
    m.add(prism(sp, top, top + 0.07 * L, "cl_blue"))                                     # paint splash
    cube = Mesh()
    z0, z1, h, e = top + 0.07 * L, top + 1.77 * L, 0.85 * L, 0.07 * L
    cube.add(box(-h, -h, z0, h, h, z1, "cl_drips", {"top": "cl_qr", "bottom": "cl_white"}))   # QR code on top
    for sx in (-1, 1):                                                                     # outlines: the 12 edges
        for sy in (-1, 1):
            cube.add(box(sx * h - e, sy * h - e, z0, sx * h + e, sy * h + e, z1 + e, "cl_edge"))
        for z in (z0 + e, z1):
            cube.add(box(sx * h - e, -h, z - e, sx * h + e, h, z + e, "cl_edge"))
            cube.add(box(-h, sx * h - e, z - e, h, sx * h + e, z + e, "cl_edge"))
    m.add(rot_z(cube, 0, 0, 45))                                                           # on edge to the front
    # the ladder, leaning on the cube's front edge (x = h * sqrt 2 + e): every rung stays in front of it
    (bx, bz), (tx, tz) = (1.8 * L, z0), (1.32 * L, z0 + 2.0 * L)
    for s in (-1, 1):
        m.add(cyl_between((bx, 0.32 * L * s, bz), (tx, 0.32 * L * s, tz), 0.07 * L, 0.07 * L, 6, "cl_blue"))
    for k in range(5):
        t = (k + 0.6) / 5.6
        x, z = bx + (tx - bx) * t, bz + (tz - bz) * t
        assert z > z1 or x - 0.05 * L > h * math.sqrt(2) + e, (k, x, z)
        m.add(cyl_between((x, -0.32 * L, z), (x, 0.32 * L, z), 0.05 * L, 0.05 * L, 6, "cl_blue"))
    return m


def cl_logo_size(L=0.75):
    """(cube half size with its outline, cube top, ladder foot x), model units, logo standing at z = 0."""
    return (0.85 + 0.07) * L, (0.07 + 1.7 + 0.07) * L, 1.8 * L


PILLAR_TOP = 5.85          # the great pillar's platform (model units above its foot)


def m_great_pillar():
    """The great pillar under the central prang: a stepped plinth, a redented shaft (a cross of two blocks,
    like the prang tiers) with carved moss-edged bands, a corbelled capital stepping out into a square
    platform, and a lotus bud on it. 2.6 across the plinth, the platform 3.0 square, about 6.9 tall."""
    m = Mesh()
    m.add(box(-1.25, -1.25, 0, 1.25, 1.25, 0.4, "ac12", {"top": "ac12_moss"}))             # plinth
    m.add(box(-1.0, -1.0, 0.4, 1.0, 1.0, 0.8, "ac12"))
    for (hx, hy) in ((0.72, 0.5), (0.5, 0.72)):                                           # redented shaft
        m.add(segbox(-hx, -hy, 0.8, hx, hy, 4.6, "ac12", seg=0.6))
    for z in (0.8, 1.9, 3.0, 4.1):                                                        # carved bands
        m.add(box(-0.82, -0.82, z, 0.82, 0.82, z + 0.22, "ac12_moss" if z < 2 else "ac12"))
    for i, r in enumerate((0.95, 1.15, 1.35)):                                            # corbelled capital
        m.add(box(-r, -r, 4.6 + 0.3 * i, r, r, 4.9 + 0.3 * i, "ac12"))
    m.add(box(-1.5, -1.5, 5.5, 1.5, 1.5, PILLAR_TOP, "ac12", {"top": "ac12_moss"}))          # the platform
    m.add(cylinder(0, 0, PILLAR_TOP, PILLAR_TOP + 0.35, 0.42, 12, "ac12", r1=0.5))         # lotus bud
    m.add(cylinder(0, 0, PILLAR_TOP + 0.35, PILLAR_TOP + 0.85, 0.5, 12, "ac12", r1=0.25))
    m.add(cylinder(0, 0, PILLAR_TOP + 0.85, PILLAR_TOP + 1.05, 0.25, 12, "ac12", r1=0.04))
    return m


def m_naga(moss=False):
    """Seven-headed naga at the end of a causeway balustrade, in temple sandstone; faces +x.
    A rising body, a broad fan-shaped hood and seven heads along its rim. 4.8 wide, 6.4 tall. moss: overgrown
    pedestal, body and hood, every other head."""
    m = Mesh()
    mo = "ac12_moss" if moss else "ac12"
    m.add(box(-1.3, -1.2, 0, 1.0, 1.2, 0.8, mo))                                           # pedestal
    m.add(cyl_between((-0.9, 0, 0.8), (-0.55, 0, 2.6), 0.62, 0.55, 10, mo))             # the rising body
    m.add(cyl_between((-0.55, 0, 2.6), (-0.3, 0, 3.4), 0.55, 0.5, 10, mo))
    cz, ry, rz = 3.0, 2.4, 2.9
    rim = [(ry * math.sin(math.radians(a)), cz + rz * math.cos(math.radians(a))) for a in range(-95, 96, 10)]
    hood = [(0.9, cz - 0.9)] + rim[::-1] + [(-0.9, cz - 0.9)]
    hood = [(0.9, cz - 0.9), (-0.9, cz - 0.9)] + rim                                         # convex, counter-clockwise
    m.add(extrude_x(hood, -0.75, -0.25, mo))                                             # the hood
    for k in range(7):
        a = math.radians(-72 + k * 24)
        lift = 0.5 * math.cos(a) ** 6                                                         # centre head highest
        p0 = (-0.35, 0.95 * ry * math.sin(a), cz + 0.95 * rz * math.cos(a) + lift)
        p1 = (0.15, 1.0 * ry * math.sin(a), cz + 1.0 * rz * math.cos(a) + 0.2 + lift)
        m.add(cyl_between(p0, p1, 0.5, 0.42, 8, mo if k % 2 else "ac12"))                    # head, hooded
        m.add(cyl_between(p1, (p1[0] + 0.32, p1[1], p1[2] - 0.08), 0.42, 0.14, 8, "ac12"))   # snout
    return m


MODELS = {
    "sala": (m_sala, "Sala, open Thai pavilion"),
    "songthaew": (m_songthaew, "Red truck (rot daeng)"),
    "tuktuk": (m_tuktuk, "Tuk-tuk"),
    "parasol_red": (lambda: m_parasol("canvas_red"), "Market umbrella, red"),
    "parasol_green": (lambda: m_parasol("canvas_green"), "Market umbrella, green"),
    "parasol_blue": (lambda: m_parasol("canvas_blue"), "Market umbrella, blue"),
    "spirit_house": (m_spirit_house, "Spirit house (san phra phum)"),
    "khom": (m_khom, "Lanna paper lantern"),
    "khom_string": (m_khom_string, "String of Lanna lanterns, 24 long"),
    "longtail": (m_longtail, "Long-tail boat"),
    "tung": (m_tung, "Lanna prayer banner (tung)"),
    "thai_flag": (m_thai_flag, "Thai flag on a pole"),
    "foodset": (m_foodset, "Street food table and stools"),
    "fruitstall": (m_fruitstall, "Fruit stall with tarp"),
    "baskets": (m_baskets, "Baskets of fruit for a counter"),
}


# ── MD3 writer ───────────────────────────────────────────────────────────────────────────
def write_md3(path, mesh, name):
    """One frame, one surface. Vertices are welded per (position, uv)."""
    verts, index, tris = [], {}, []
    for t in mesh.tris:
        ids = []
        for p, uv in t:
            key = (round(p[0], 4), round(p[1], 4), round(p[2], 4), round(uv[0], 5), round(uv[1], 5))
            if key not in index:
                index[key] = len(verts); verts.append((p, uv))
            ids.append(index[key])
        tris.append(ids)
    U = 16.0                                   # model units per cube
    xs = [p[0] * U for p, _ in verts]; ys = [p[1] * U for p, _ in verts]; zs = [p[2] * U for p, _ in verts]
    for v in xs + ys + zs:
        assert abs(v * 64) < 32767, f"{name}: vertex out of md3 range"
    nv, nt = len(verts), len(tris)
    # surface
    sh = struct.calcsize("<4s64si4i5i")
    ofs_tris = sh
    ofs_shaders = ofs_tris + 12 * nt
    ofs_uv = ofs_shaders + 68
    ofs_verts = ofs_uv + 8 * nv
    size = ofs_verts + 8 * nv
    surf = struct.pack("<4s64si4i5i", b"IDP3", name.encode()[:63], 0, 1, 1, nv, nt, ofs_tris, ofs_shaders, ofs_uv, ofs_verts, size)
    surf += b"".join(struct.pack("<3i", *t) for t in tris)
    surf += struct.pack("<64si", b"skin.png", 0)
    surf += b"".join(struct.pack("<2f", uv[0], uv[1]) for _, uv in verts)
    for (p, _) in verts:                       # file stores (y, x, z): the loader swaps x and y back
        surf += struct.pack("<3hh", int(round(p[1] * U * 64)), int(round(p[0] * U * 64)), int(round(p[2] * U * 64)), 0)
    # header + one frame
    hdr = struct.calcsize("<4si64si4i4i")
    frame = struct.pack("<3f3f3ff16s", min(ys), min(xs), min(zs), max(ys), max(xs), max(zs), 0, 0, 0,
                        max(math.dist((0, 0, 0), (x, y, z)) for x, y, z in zip(xs, ys, zs)), b"frame0")
    ofs_frames = hdr; ofs_tags = ofs_frames + len(frame); ofs_meshes = ofs_tags; ofs_eof = ofs_meshes + len(surf)
    head = struct.pack("<4si64si4i4i", b"IDP3", 15, name.encode()[:63], 0, 1, 0, 1, 0, ofs_frames, ofs_tags, ofs_meshes, ofs_eof)
    open(path, "wb").write(head + frame + surf)
    return nv, nt


def check_closed(mesh):
    """Every edge of a closed, consistently wound mesh is used once in each direction. Returns the
    number of edges that are not (cards and open shells count; parts are closed individually)."""
    from collections import Counter
    e = Counter()
    for t in mesh.tris:
        ps = [tuple(round(c, 4) for c in p) for p, _ in t]
        for i in range(3):
            e[(ps[i], ps[(i + 1) % 3])] += 1
    return sum(1 for (a, b), n in e.items() if e.get((b, a), 0) != n)


def build_pack(outdir, folder, models, atlas_name, dist, owner="stylebar"):
    """Write models {name: (mesh_fn, desc)} to <outdir>/<owner>/<folder>/<name>/ with a shared atlas."""
    atlas = paint_atlas()
    base = os.path.join(outdir, owner, folder)
    os.makedirs(base, exist_ok=True)
    atlas.save(os.path.join(base, atlas_name))
    rows = []
    for key, (fn, desc) in models.items():
        mesh = fn()
        d = os.path.join(base, key); os.makedirs(d, exist_ok=True)
        nv, nt = write_md3(os.path.join(d, "tris.md3"), mesh, key)
        open(os.path.join(d, "md3.cfg"), "w").write(
            f'md3load tris.md3\nmd3skin {key} ../{atlas_name}\nmdlattribute desc "{desc}"\n'
            f'mdlattribute author "{owner}"\nmdlattribute distribution "{dist}"\n')
        rows.append((key, nv, nt, check_closed(mesh)))
    return rows


def build(outdir="models"):
    atlas = paint_atlas()
    base = os.path.join(outdir, "stylebar", "thai")
    os.makedirs(base, exist_ok=True)
    atlas.save(os.path.join(base, "thai_atlas.png"))
    rows = []
    for key, (fn, desc) in MODELS.items():
        mesh = fn()
        d = os.path.join(base, key); os.makedirs(d, exist_ok=True)
        nv, nt = write_md3(os.path.join(d, "tris.md3"), mesh, key)
        open(os.path.join(d, "md3.cfg"), "w").write(
            f'md3load tris.md3\nmd3skin {key} ../thai_atlas.png\nmdlattribute desc "{desc}"\n'
            f'mdlattribute author "stylebar (generated)"\nmdlattribute distribution "ac_chiangmai"\n')
        rows.append((key, nv, nt, check_closed(mesh)))
    return rows


# ── offline preview ──────────────────────────────────────────────────────────────────────
def render(mesh, atlas, size=320, yaw=35, pitch=25):
    """Orthographic flat-shaded render with back-face culling, so holes and inward faces show as gaps.
    The camera sits at azimuth `yaw` (0 = looking from +y, i.e. from the south) and `pitch` above."""
    im = Image.new("RGB", (size, size), (34, 38, 46))
    d = ImageDraw.Draw(im)
    a, b = math.radians(yaw), math.radians(pitch)
    cam = (math.sin(a) * math.cos(b), math.cos(a) * math.cos(b), math.sin(b))     # towards the camera
    right = (math.cos(a), -math.sin(a), 0.0)
    up = _cross(cam, right)
    if up[2] < 0: up = tuple(-c for c in up); right = tuple(-c for c in right)
    proj = lambda p: (_dot(p, right), -_dot(p, up), -_dot(p, cam))                 # screen x, screen y, depth
    pts = [proj(p) for t in mesh.tris for p, _ in t]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    s = (size - 30) / max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    ox, oy = size / 2 - s * (max(xs) + min(xs)) / 2, size / 2 - s * (max(ys) + min(ys)) / 2
    px = atlas.load()
    faces = []
    for t in mesh.tris:
        n = _cross(_sub(t[1][0], t[0][0]), _sub(t[2][0], t[0][0]))
        if _dot(n, cam) <= 0: continue
        v = [proj(p) for p, _ in t]
        u = sum(uv[0] for _, uv in t) / 3; w = sum(uv[1] for _, uv in t) / 3
        c = px[min(ATLAS - 1, int(u * ATLAS)), min(ATLAS - 1, int(w * ATLAS))]
        ln = math.sqrt(_dot(n, n)) or 1
        shade = 0.5 + 0.5 * max(0, _dot(n, (0.35, 0.45, 0.82)) / ln)
        faces.append((sum(q[2] for q in v) / 3, [(ox + s * q[0], oy + s * q[1]) for q in v], tuple(int(cc * shade) for cc in c)))
    for _, poly, c in sorted(faces, key=lambda f: -f[0]):
        d.polygon(poly, fill=c)
    return im


def preview(out):
    atlas = paint_atlas()
    keys = list(MODELS)
    cols = 4
    sheet = Image.new("RGB", (cols * 320, ((len(keys) + cols - 1) // cols) * 340), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for i, k in enumerate(keys):
        mesh = MODELS[k][0]()
        im = render(mesh, atlas)
        x, y = (i % cols) * 320, (i // cols) * 340
        sheet.paste(im, (x, y)); d.text((x + 6, y + 322), f"{k}  {len(mesh.tris)} tris", fill=(255, 255, 120))
    sheet.save(out)


# ── Angkor ruins (ac_wat): barrel vault roofs of small stones, stepped prang towers, square pillars ─
def rot_z(m, cx, cy, deg):
    """Rotate a mesh about the vertical axis through (cx, cy) (keeps the winding)."""
    a = math.radians(deg); c, s_ = math.cos(a), math.sin(a)
    return m.transformed(lambda p: (cx + (p[0] - cx) * c - (p[1] - cy) * s_, cy + (p[0] - cx) * s_ + (p[1] - cy) * c, p[2]))


def _shift(m, dx, dy, dz):
    return m.transformed(lambda p: (p[0] + dx, p[1] + dy, p[2] + dz))


def voussoir(a, H, t, th0, th1, x0, x1, mat):
    """One stone of a barrel vault: the part of the half-ellipse ring (outer a wide across y, H high,
    t thick) between angles th0 and th1, from x0 to x1 along the vault."""
    pts = [(a * math.cos(th0), H * math.sin(th0)), (a * math.cos(th1), H * math.sin(th1)),
           ((a - t) * math.cos(th1), (H - t) * math.sin(th1)), ((a - t) * math.cos(th0), (H - t) * math.sin(th0))]
    return extrude_x(pts, x0, x1, mat)


def vault_profile(W, H):
    """Outer half-width of the vault over a W-wide hallway and its height (for clips and roots)."""
    return W / 2 + 0.5, H


def m_vault_roof(W, L, H, bw=2.0, variant=0, n=10):
    """Khmer gallery roof: a barrel vault (half ellipse, W/2 + 0.5 wide each side, H high) built of
    rings of small stones, on two stone beams that lie on the pillar rows (z 0..1.3 = beams, z = 0 is
    the pillar tops). L along y. variant picks where the moss grows."""
    import random as _r
    rnd = _r.Random(variant * 7919 + int(W * 31 + L * 17 + H * 5))
    m = Mesh()
    a, _ = vault_profile(W, H)
    t = 0.6
    for s_ in (-1, 1):                                                   # beams (built along x)
        c = s_ * (W / 2 - bw / 2)
        m.add(box(-L / 2, c - bw / 2, 0, L / 2, c + bw / 2, 0.9, "ac12"))
        m.add(box(-L / 2, c - bw / 2 - 0.25, 0.9, L / 2, c + bw / 2 + 0.25, 1.3, "ac12"))
    m.add(box(-L / 2, -(a - t), 1.3, L / 2, a - t, 1.42, "ac12"))
    # solid stone at both ends: seen from outside the vault is a block of stone, not a hollow shell
    curve = lambda y: H * math.sqrt(max(0.0, 1 - (y / a) ** 2))
    ns = max(2, round(2 * a / 1.5))
    for i in range(ns):
        y0, y1 = -a + 2 * a * i / ns, -a + 2 * a * (i + 1) / ns
        top = min(curve(y0), curve(y1))
        nr = max(1, int(top / 1.5))
        for j in range(nr + 1):
            z0 = top * j / nr if j < nr else top
            if j < nr:
                poly = [(y0, z0), (y1, z0), (y1, top * (j + 1) / nr), (y0, top * (j + 1) / nr)]
            else:                                                          # the piece under the curve
                if curve(y0) - top < 0.02 and curve(y1) - top < 0.02: continue
                poly = [(y0, z0), (y1, z0), (y1, curve(y1)), (y0, curve(y0))]
            mat = "ac12_moss" if rnd.random() < 0.25 + 0.4 * (z0 / H) else "ac12"
            for (e0, e1) in ((-L / 2, -L / 2 + 0.4), (L / 2 - 0.4, L / 2)):
                m.add(_shift(extrude_x([pt for pt in poly], e0, e1, mat), 0, 0, 1.3))
    k = max(1, round(L / 1.0))
    ln = L / k
    for i in range(k):
        x0 = -L / 2 + i * ln + 0.04
        for j in range(n):
            th0, th1 = math.pi * j / n, math.pi * (j + 1) / n
            mossy = rnd.random() < (0.3 + 0.5 * math.sin((th0 + th1) / 2)) * (1.0 if variant else 0.7)
            m.add(_shift(voussoir(a, H, t, th0 + 0.006, th1 - 0.006, x0, x0 + ln - 0.08, "ac12_moss" if mossy else "ac12"), 0, 0, 1.3))
    return rot_z(m, 0, 0, 90)


def segbox(x0, y0, z0, x1, y1, z1, mat, seg=1.5):
    """A box cut into blocks about `seg` long along its longer side, so every block gets the texture
    at about the right scale (box() stretches the whole tile over each face)."""
    m = Mesh()
    if x1 - x0 >= y1 - y0:
        n = max(1, round((x1 - x0) / seg))
        for i in range(n):
            m.add(box(x0 + (x1 - x0) * i / n, y0, z0, x0 + (x1 - x0) * (i + 1) / n, y1, z1, mat))
    else:
        n = max(1, round((y1 - y0) / seg))
        for i in range(n):
            m.add(box(x0, y0 + (y1 - y0) * i / n, z0, x1, y0 + (y1 - y0) * (i + 1) / n, z1, mat))
    return m


def prang_tiers(W, storey, dz=0.975, scale=2.0, over=0.7):
    """The steps of a Khmer prang roof (model units, drawn at `scale`): (half size, top) of the
    cornice slab, the upright storey, then the redented tiers of the bud. Each tier rises dz and steps
    in by 0.6 world cubes at the bottom, more towards the top (the bud's bulge): a player jumps up
    tier by tier (a jump clears 2.2, and pushing against the next tier lands him on the ledge)."""
    hw, b0 = W / 2 + over, W / 2 * 0.95                          # over: the cornice slab's overhang
    tiers = [(hw, 0.6), (b0, 0.6 + storey)]
    z, r, i = 0.6 + storey, b0, 0
    n = int(b0 * scale / 0.95)
    while True:
        r -= (0.6 + 1.0 * (i / n) ** 2) / scale
        if r < 0.7: break
        z += dz; i += 1
        tiers.append((r, z))
    return tiers


def gridbox(x0, y0, z0, x1, y1, z1, mat, seg=1.5):
    """A flat box cut into blocks about `seg` square (x and y), so a big ceiling keeps the texture scale."""
    m = Mesh()
    nx, ny = max(1, round((x1 - x0) / seg)), max(1, round((y1 - y0) / seg))
    for i in range(nx):
        for j in range(ny):
            m.add(box(x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, z0,
                      x0 + (x1 - x0) * (i + 1) / nx, y0 + (y1 - y0) * (j + 1) / ny, z1, mat))
    return m


def _cross_ring(hx, hy, h, slit=0.0):
    """A redented tier (the cross of an hx x hy and an hy x hx box) around a square shaft of half size h,
    as non-overlapping boxes (x0, y0, x1, y1); slit > 0 cuts a narrow window through the middle of
    each side."""
    def cut(x0, y0, x1, y1, along_x):
        if not slit: return [(x0, y0, x1, y1)]
        return ([(x0, y0, -slit, y1), (slit, y0, x1, y1)] if along_x else [(x0, y0, x1, -slit), (x0, slit, x1, y1)])
    out = []
    out += cut(-hx, -hy, hx, -h, True) + cut(-hx, h, hx, hy, True)               # the long box minus the shaft
    out += cut(-hx, -h, -h, h, False) + cut(h, -h, hx, h, False)
    out += cut(-hy, -hx, hy, -hy, True) + cut(-hy, hy, hy, hx, True)               # the cross box's arms beyond it
    return out


def m_prang2(W, storey, dz=0.975, over=0.7, hole=0.0):
    """Khmer prang roof over a square hall: a cornice slab, an upright storey, then redented tiers
    (a cross of two boxes, so the corners step in) with a band at the top of each, closing into a
    lotus bud and a rounded stone lotus finial. Centred, eaves at z = 0. Follows prang_tiers() so the
    clips match it. hole > 0: hollow inside, a corbelled stone shaft of that half size rising from the
    slab, narrowing tier by tier, with slits near the top where the sky shows through."""
    m = Mesh()
    tiers = prang_tiers(W, storey, dz, over=over)
    hw, top = tiers[0]
    if hole:
        for (x0, y0, x1, y1) in _cross_ring(hw, hw, hole):
            m.add(gridbox(x0, y0, 0, x1, y1, top, "ac12"))
    else:
        m.add(box(-hw, -hw, 0, hw, hw, top, "ac12", {"bottom": "khmer_ceiling"}))
    zb = top
    for i, (r, zt) in enumerate(tiers[1:]):
        band = "ac12_moss" if i % 3 != 1 else "ac12"
        h = min(hole - 0.16 * i, r * 0.74 - 0.9) if hole else 0                  # corbelled: steps in every tier
        if h >= 0.4:
            slit = 0.12 if h < 0.37 * hole and i % 2 == 0 else 0.0              # light through the upper tiers
            for (x0, y0, x1, y1) in _cross_ring(r * 0.96, r * 0.74, h, slit):
                m.add(segbox(x0, y0, zb, x1, y1, zt - 0.18, "ac12"))
            for (x0, y0, x1, y1) in _cross_ring(r, r * 0.74, h, slit):
                m.add(segbox(x0, y0, zt - 0.18, x1, y1, zt, band))
            zb = zt
            continue
        for (hx, hy) in ((r * 0.96, r * 0.74), (r * 0.74, r * 0.96)):
            m.add(segbox(-hx, -hy, zb, hx, hy, zt - 0.18, "ac12"))
        for (hx, hy) in ((r, r * 0.74), (r * 0.74, r)):
            m.add(segbox(-hx, -hy, zt - 0.18, hx, hy, zt, band))
        zb = zt
    r = tiers[-1][0]
    m.add(cylinder(0, 0, zb, zb + 0.8, r * 0.7, 12, "ac12", r1=r * 0.95))
    m.add(cylinder(0, 0, zb + 0.8, zb + 1.7, r * 0.95, 12, "ac12", r1=r * 0.55))
    m.add(cylinder(0, 0, zb + 1.7, zb + 2.3, r * 0.55, 12, "ac12", r1=r * 0.15))
    return m


def m_square_pillar(L=12.0, seed=1):
    """A fallen square 2 x 2 pillar (like the hallway pillars) lying along x, broken into drums that
    shifted a little when they hit the ground; moss on top."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    k = 3
    x = -L / 2
    for i in range(k):
        ln = L / k - 0.15
        d = box(x, -1, 0, x + ln, 1, 2, "ac12", {"top": "ac12_moss", "s": "ac12_moss"})
        m.add(rot_z(_shift(d, 0, rnd.uniform(-0.25, 0.25), 0), x + ln / 2, 0, rnd.uniform(-6, 6)))
        x += ln + 0.15 + rnd.uniform(0, 0.4)
    return m


def m_pillar_pile(L=12.0, seed=2):
    """Three fallen pillars: two side by side on the ground (along x), one across on top of them."""
    m = Mesh()
    m.add(_shift(m_square_pillar(L, seed), 0, -1.15, 0))
    m.add(_shift(m_square_pillar(L * 0.8, seed + 1), 0.6, 1.15, 0))
    m.add(rot_z(_shift(m_square_pillar(L * 0.7, seed + 2), 0, 0, 2.0), 0, 0, 82))
    return m


def m_vault_debris(Wd=10.0, Ld=10.0, n=40, seed=3):
    """The small stones of a fallen vault scattered over Wd x Ld, lying every which way."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    for i in range(n):
        th = rnd.uniform(0, math.pi)
        p = voussoir(6.5, 5.0, 0.6, th, th + math.pi / 10, -0.45, 0.45, "ac12_moss" if rnd.random() < 0.6 else "ac12")
        c = (6.5 * math.cos(th + 0.15), 5.0 * math.sin(th + 0.15))
        p = _shift(p, 0, -c[0], -c[1])
        p = rot_x(p, 0, 0, 0, rnd.uniform(0, 360))
        p = rot_z(p, 0, 0, rnd.uniform(0, 360))
        p = _drop(p)
        m.add(_shift(p, rnd.uniform(-Wd / 2, Wd / 2), rnd.uniform(-Ld / 2, Ld / 2), 0 if i < n * 0.7 else rnd.uniform(0.3, 0.9)))
    return m


def m_stone_steps(steps, w=4.0, seed=5):
    """Big fallen cornice stones piled against a wall: steps = [(start, top)] along +y up to y = 0 (the
    wall), each block reaching from `start` to the wall, `top` high, w wide (x); jittered and mossy."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    for i, (y0, top) in enumerate(steps):
        for j in range(3):
            x0 = -w / 2 + w * j / 3
            jit = rnd.uniform(-0.12, 0.12)
            m.add(box(x0 + 0.04, y0 + jit, 0, x0 + w / 3 - 0.04, 0, top - rnd.uniform(0, 0.15),
                      "ac12", {"top": "ac12_moss" if (i + j) % 3 != 2 else "ac12"}))
    return m


def m_vines(h, w=6.0, seed=1, n=7):
    """Vines hanging down a wall: n thin wavy strands from z = h to the ground spread over w (x), just
    in front of the wall (y < 0, the wall face at y = 0), with clumps of leaves along them."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    for i in range(n):
        x = rnd.uniform(-w / 2, w / 2)
        length = h * rnd.uniform(0.55, 1.0)
        k = max(2, int(length / 1.5))
        pts = [(x + 0.5 * math.sin(j * 0.9 + i), -0.25 - 0.15 * math.sin(j * 1.3), h - length * j / k) for j in range(k + 1)]
        for a, b in zip(pts, pts[1:]):
            m.add(cyl_between(a, b, 0.11, 0.1, 5, "fig_bark"))
        for p_ in pts[1::2]:
            r = rnd.uniform(0.35, 0.7)
            m.add(cylinder(p_[0], p_[1] - 0.2, p_[2] - r * 0.5, p_[2] + r * 0.2, r * 0.5, 6, "leaves", r1=r))
            m.add(cylinder(p_[0], p_[1] - 0.2, p_[2] + r * 0.2, p_[2] + r * 0.6, r, 6, "leaves", r1=r * 0.2))
    m.add(box(-w / 2 - 0.3, -0.7, h - 0.5, w / 2 + 0.3, 0, h + 0.4, "leaves"))       # the tangle on top
    return m


def m_balusters(w=3.0, h=8.0, n=5):
    """A Khmer window: a row of n turned stone balusters across w (x), h high, with a sill."""
    m = Mesh()
    for i in range(n):
        x = -w / 2 + w * (i + 0.5) / n
        m.add(cylinder(x, 0, 0, h, 0.2, 8, "ac12"))
        for f in (0.2, 0.5, 0.8):
            m.add(cylinder(x, 0, h * f - 0.25, h * f + 0.25, 0.3, 8, "ac12"))
    return m


def m_water_plane(x0, y0, x1, y1, cell=3.0, algae=0.2, seed=5):
    """Standing water in a basin: a thin surface from (x0, y0) to (x1, y1) relative to the origin, in
    tiles about `cell` wide (one texture per tile), some of them green with algae (more near the edges).
    AC has one water level per map, so a pool above it is this model: players wade through it."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    nx, ny = max(1, round((x1 - x0) / cell)), max(1, round((y1 - y0) / cell))
    for i in range(nx):
        for j in range(ny):
            edge = min(i, j, nx - 1 - i, ny - 1 - j)
            mat = "murky_water" if algae >= 1 or rnd.random() < algae * (2.5 if edge <= 1 else 0.5) else "pool_water"
            m.add(box(x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, -0.05,
                      x0 + (x1 - x0) * (i + 1) / nx, y0 + (y1 - y0) * (j + 1) / ny, 0, mat))
    return m


def m_plank(L, W=2.4):
    """A wooden plank bridge along x, L long: three boards on cross battens, top at z = 0."""
    m = Mesh()
    bw = W / 3
    for i in range(3):
        y0 = -W / 2 + i * bw
        m.add(segbox(-L / 2, y0 + 0.04, -0.25, L / 2, y0 + bw - 0.04, 0, "ac111", seg=2.0))
    n = max(2, int(L / 2.5))
    for i in range(n + 1):
        x = -L / 2 + 0.3 + (L - 0.6) * i / n
        m.add(box(x - 0.2, -W / 2 - 0.1, -0.55, x + 0.2, W / 2 + 0.1, -0.25, "ac111"))
    return m


def m_fig(W, H, drop, L=10.0, seed=3, trunk=15.0):
    """A strangler fig (Ta Prohm) on a vault roof over a W-wide hallway (vault ridge H above the
    origin): a massive root base over the vault, roots over both sides down to the floor `drop`
    below the origin, a tall bending pale trunk and its own crown of leaf clusters."""
    import random as _r
    rnd = _r.Random(seed)
    m = Mesh()
    a, _ = vault_profile(W, H)
    pt = lambda th, y, lift=0.5: (a * math.cos(th), y, H * math.sin(th) + lift)
    m.add(cyl_between((0, 0, H - 1.0), (0, 0.5, H + 4), 4.0, 2.3, 12, "fig_bark"))            # root base
    path = [(0, 0.5, H + 4), (0.8, 1.0, H + trunk * 0.4), (0.2, 1.8, H + trunk * 0.7), (1.2, 1.2, H + trunk)]
    for j in range(len(path) - 1):
        r0 = 2.2 * (1 - 0.22 * j)
        m.add(cyl_between(path[j], path[j + 1], r0, r0 * 0.8, 10, "fig_bark"))
    for i in range(18):                                                                       # roots
        s_ = 1 if i % 2 else -1
        y = rnd.uniform(-L / 2, L / 2)
        r0 = rnd.uniform(0.6, 1.1)
        th = [math.pi / 2 - s_ * 0.25, math.pi / 2 - s_ * 0.7, math.pi / 2 - s_ * 1.1, math.pi / 2 - s_ * 1.45]
        pts = [(s_ * 1.5, y * 0.2, H + 1.2)] + [pt(t_, y * (0.4 + 0.2 * k)) for k, t_ in enumerate(th)]
        pts += [(s_ * (a + 0.4), y, -drop * 0.5), (s_ * (a + rnd.uniform(0.5, 1.5)), y * 1.05, -drop - 0.3)]
        for j in range(len(pts) - 1):
            rr = r0 * (1 - 0.08 * j)
            m.add(cyl_between(pts[j], pts[j + 1], rr, rr * 0.93, 7, "fig_bark"))
        bx, by, _ = pts[-1]
        m.add(cyl_between((bx, by, -drop + 1.5), (bx, by, -drop - 0.3), r0 * 0.8, r0 * 1.8, 7, "fig_bark"))
    top = path[-1]
    for i in range(16):                                                                       # crown
        ang = i * 2 * math.pi / 7 + rnd.uniform(-0.4, 0.4)
        d = rnd.uniform(2.0, 7.0) if i else 0
        c = (top[0] + d * math.cos(ang), top[1] + d * math.sin(ang), top[2] + rnd.uniform(-1.5, 1.5))
        m.add(cyl_between(top, c, 0.6, 0.35, 6, "fig_bark"))
        r = rnd.uniform(2.0, 3.2)
        m.add(cylinder(c[0], c[1], c[2] - r * 0.4, c[2] + r * 0.2, r * 0.6, 9, "leaves", r1=r))
        m.add(cylinder(c[0], c[1], c[2] + r * 0.2, c[2] + r * 0.8, r, 9, "leaves", r1=r * 0.3))
    return m


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        for r in build(sys.argv[2] if len(sys.argv) > 2 else "models"):
            print("%-14s %4d verts %4d tris  unmatched edges %d" % r)
    elif cmd == "install":
        for r in build(os.path.expanduser("~/.assaultcube/v1.3/packages/models/mapmodels")):
            print("%-14s %4d verts %4d tris  unmatched edges %d" % r)
    elif cmd == "preview":
        preview(sys.argv[2])
