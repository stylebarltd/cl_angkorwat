#!/usr/bin/env python3
"""
cl_angkorwat - Angkor Wat temple CTF by cubeLadder: the fight happens inside the temple only. Generated, not hand-built.

512 grid. The playable temple is 192 x 192 cells (centred on 255.5); the moat, the lawns, the
libraries and the compound wall around it are scenery, seen through the windows but out of reach.
Both bases are on the 2nd floor: red in the south-west pagoda, blue in the north-east one. Blue's side
is red's mirrored across the NW-SE diagonal.

  - 2nd floor (floor 20), where the action is: wide covered hallways in a ring and a cross to the
    great hall, four courtyards sunk 4 cubes. Every line is a wall: plain (closed), with baluster
    windows (closed, see and shoot through) or broken (fallen in, passable). Three lanes: the middle
    through the courtyards, cross hallways and great hall; one side over the NW pagoda; the other
    down to the 1st floor
  - 1st floor (floor 4): only the south-east L is reached, by the middle stairs (south and east,
    beside a window wall across the gallery) and the SE pagoda's two stairs; broken stretches of the
    gallery's inner wall join gallery and terrace, broken walls of the SE pocket drop down to it
  - the five towers are walk-in halls under Khmer prang roof models (cubeladder/khmer pack, scale 2).
    The great hall has balconies (floor 30) in its SW and NE corners behind baluster windows, each reached
    by a ramp: the sniper spots
  - clean: walls, vault roofs and T-junctions stand; nagas in the Ts face the great pagoda; the
    jungle (moss, plants, vines, strangler figs) is the only ruin

    python3 gen_wat.py [out.cgz]          # also writes the model pack to models/cubeladder/khmer
"""
import copy, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acmap, models
from acmap import SOLID, Entity, ENT
from builder import Builder, make_extras

NAME = "cl_angkorwat"
OWNER = "cubeladder"                     # model folder (packages/models/mapmodels/cubeladder/khmer) and author
SF = 9                                  # 512 x 512
N = 1 << SF
SKY = 110                                # room for the great prang (top ~98) and players on it
TA, TB = 160, 351                        # the playable temple (1st floor ring outer edge)
KEEP = 0                                 # cells kept round the temple; beyond them solid sky (`strip_scenery`; 3 let players out: the edge clips stood there)
SF_OUT, CROP = 8, 128                    # the written map: 256 x 256, cells CROP.. of the build grid (`crop`)
PA, PB = 194, 317                        # the 2nd floor platform
F1, F2, FC, FB = 4, 20, 16, 30           # floors: 1st, 2nd, courtyards, central hall balcony
E1, E2, EP, EC = 16, 32, 34, 48          # pillar tops: 1st floor gallery, hallways; walls: corner halls, central hall

# textures (0-based ids of default_map_settings.cfg)
T_STONE, T_SLAB, T_FLAG, T_LATERITE = 12, 50, 45, 23
T_ROUGH, T_GRASS, T_GRASS2, T_MUD, T_ROCK, T_SAND = 26, 133, 132, 138, 160, 141
# The embedded config resets the mapmodel list (an entity stores its model slot in one byte, so
# 202 defaults + this map's custom models would overflow 255). Our list: these defaults first
# (same parameters as default_map_settings.cfg), then the custom models.
DEFAULT_MODELS = [("1 7 0 0", "toca/tree1"), ("0 17 0 0", "toca/palmtree1"), ("0 14 0 0", "toca/tree2"),
                  ("0 2 0 0", "toca/plants/bush"), ("1 4 0 0", "toca/plants/smaltree"), ("0 0 0 0", "makke/plant_leafy"), ("0 10 0 0", "makke/ladder_10x")]
M_TREE, M_PALM, M_TREE2, M_BUSH, M_SMALLTREE, M_PLANT, M_LADDER = range(7)
FIRST_CUSTOM = len(DEFAULT_MODELS)

# ── custom models, registered while building, written to the pack at the end ───────────────
PACK = {}                                # key -> (fn, desc)
SLOTS = []                               # keys in slot order


SCALE = {}                               # key -> mapmodel scale (0 = default 1)


def slot(key, fn, desc, scale=0):
    if key not in PACK:
        PACK[key] = (fn, desc); SLOTS.append(key); SCALE[key] = scale
    i = FIRST_CUSTOM + SLOTS.index(key)
    assert i <= 255, "too many mapmodel slots"
    return i


def vault_slot(W, L, H, bw, variant):
    return slot(f"vault_{W}x{L}_h{H}_b{bw}_v{variant}", lambda: models.m_vault_roof(W, L, H, bw, variant),
                f"Khmer vault roof {W}x{L}")


def rotp(k, px, py):
    """A world point (cell corner) rotated k times by 90° clockwise around the map centre."""
    for _ in range(k % 4):
        px, py = N - py, px
    return px, py


def pav_slot(W, L, H, tiers=3):
    return slot(f"pavroof_{W}x{L}_h{H}_t{tiers}", lambda: models.m_pavilion_roof(W, L, H, tiers, finial=H * 0.35),
                f"Khmer pavilion roof {W}x{L}")


# ── four-fold rotation around the map centre: describe the north / north-west quarter, rotate ──
def rot(k, x, y):
    """Cell (x, y) rotated k times by 90° clockwise (north -> east)."""
    for _ in range(k % 4):
        x, y = N - 1 - y, x
    return x, y


def rbox(k, x0, y0, x1, y1):
    ax, ay = rot(k, x0, y0); bx, by = rot(k, x1, y1)
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)


# Model yaw turns the other way: a higher yaw turns a model counter-clockwise (seen from above, y south),
# so a model rotated with its quarter gets yaw - 900 * k.
def rdir(k, d):
    return "nesw"[("nesw".index(d) + k) % 4]


class Wat:
    def __init__(self):
        self.b = Builder(SF, "Angkor Wat - temple CTF by cubeLadder", sky=SKY)
        self.b.ftex, self.b.wtex, self.b.ptex, self.b.rtex = T_GRASS, T_STONE, T_STONE, T_STONE
        self.covered = set()             # cells under roof models (lit dimmer)
        self.placed = []                 # (entity, absolute base height): re-anchored at the end

    # a model centred at world point (cx, cy) with its base at absolute height z; mirror=True also
    # places the point-mirrored copy (centre 512 - c, yaw + 180)
    def place(self, cx, cy, idx, yaw, z, mirror=True):
        for (x, y, a) in ([(cx, cy, yaw), (N - cx, N - cy, (yaw + 1800) % 3600)] if mirror else [(cx, cy, yaw)]):
            c = self.b.cell(int(x), int(y))
            dz = z - c.floor
            assert 0 <= dz <= 51, (x, y, z, c.floor)
            self.b.model(int(x), int(y), idx, a, dz=dz, sym=False)
            self.placed.append((self.b.ents[-1], z))

    def reanchor(self):
        """A model's height is stored relative to the floor of its entity cell; geometry carved after
        the model was placed changes that floor, so recompute every elevation from its absolute height."""
        for e, z in self.placed:
            dz = z - self.b.cell(e.x, e.y).floor
            assert 0 <= dz <= 51, (e.x, e.y, z)
            e.attr3 = int(round(dz * 5))

    def pav(self, x0, y0, x1, y1, W, L, H, tiers, eave, along_x):
        """A pavilion roof model with stepped clips that follow its tiers (W across the model's x)."""
        self.roof(x0, y0, x1, y1, pav_slot(W, L, H, tiers), eave, along_x)
        hw, hl, z, dz, boxes = W / 2 + 0.7, L / 2 + 0.7, 0.0, H / tiers, []
        for _ in range(tiers):
            boxes.append((0.81 * hw, 0.81 * hl, z + 0.375 * dz))
            hw, hl = 0.62 * hw * 0.92, 0.62 * hl * 0.92
            boxes.append((hw, hl, z + dz)); z += dz
        self.tiers(x0, y0, x1, y1, eave, [(b_[1], b_[0], b_[2]) if along_x else b_ for b_ in boxes])

    def prang_clips(self, x0, y0, x1, y1, eave, W, storey, scale, over=0.7):
        """Clips for a prang roof model, tier by tier (models.prang_tiers): every step is a jump, so
        the tower can be climbed to the top."""
        cx, cy = (x0 + x1 + 1) // 2, (y0 + y1 + 1) // 2
        tiers = models.prang_tiers(W, storey, scale=scale, over=over)
        hw, top = tiers[0]
        self.rawclip(cx, cy, hw * scale, hw * scale, eave, top * scale)
        for (r, top) in tiers[1:]:
            z = top * scale
            for (hx, hy) in ((r, r * 0.74), (r * 0.74, r)):
                self.rawclip(cx, cy, hx * scale, hy * scale, eave + max(0.0, z - 8), min(z, 8))

    def roof(self, x0, y0, x1, y1, idx, eave, along_x, mirror=False):
        """A roof model covering cells x0..x1, y0..y1 (centre on the cell grid corners)."""
        cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
        assert cx == int(cx) and cy == int(cy), (x0, y0, x1, y1)
        self.place(int(cx), int(cy), idx, 900 if along_x else 0, eave, mirror)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.covered.add((x, y))
                if mirror: self.covered.add((N - 1 - x, N - 1 - y))

    def groof(self, k, box, along_x, eave, H, bw=2.0):
        """A vault roof over a quarter-frame box, rotated into quarter k, with stepped clips that
        follow the vault so players walk on it (up to the ridge)."""
        x0, y0, x1, y1 = rbox(k, *box)
        ax = along_x != (k % 2 == 1)
        W, L = (y1 - y0 + 1, x1 - x0 + 1) if ax else (x1 - x0 + 1, y1 - y0 + 1)
        self.roof(x0, y0, x1, y1, vault_slot(W, L, H, bw, (x0 * 7 + y0 * 3) % 3), eave, ax)
        a, _ = models.vault_profile(W, H)
        cx, cy = (x0 + x1 + 1) // 2, (y0 + y1 + 1) // 2
        for z in [float(i) for i in range(1, H)] + [H - 0.4]:
            half = a * math.sqrt(1 - (z / H) ** 2)
            hx, hy = (L / 2, half) if ax else (half, L / 2)
            self.rawclip(cx, cy, hx, hy, eave, 1.3 + z)

    def rawclip(self, ix, iy, hx, hy, bottom, h, slope=0, axis=0):
        """A CLIP entity centred on world point (ix, iy) (integers), half sizes hx, hy, from absolute
        height `bottom`, `h` high; slope in cubes per cube along axis 1 = x, 2 = y."""
        assert hx <= 51 and hy <= 51 and h <= 51, (ix, iy, hx, hy, h)
        el = bottom - self.b.cell(ix, iy).floor
        self.b.ents.append(Entity(ENT["CLIP"], ix, iy, self.b.cell(ix, iy).floor, int(round(el * 10)),
                                  int(math.ceil(hx * 5)), int(math.ceil(hy * 5)), int(round(h * 5)), 0,
                                  int(round(slope * 40)), axis))

    def slope(self, l0, l1, a0, a1, base, s_, side, across):
        """One roof side: along the run from l0 to l1, across from a0 to a1 (world), the surface rising
        from base + 0.45 at the eave edge (a1 for side +1, a0 for side -1) by s_ per cube to the ridge."""
        lc = int(round((l0 + l1) / 2)); hl = max(lc - l0, l1 - lc)
        ac = int(round((a0 + a1) / 2)); ha = max(ac - a0, a1 - ac)
        eave_edge = a1 if side > 0 else a0
        top = base + 0.45 + abs(ac - eave_edge) * s_
        sl = -s_ * side
        if across == "y":
            self.rawclip(lc, ac, hl, ha, top - 3, 3, sl, 2)
        else:
            self.rawclip(ac, lc, ha, hl, top - 3, 3, sl, 1)

    def tiers(self, x0, y0, x1, y1, eave, boxes):
        """Stepped clips over a roof model centred on the box: boxes = [(half x, half y, top above eave)]."""
        cx, cy = (x0 + x1 + 1) // 2, (y0 + y1 + 1) // 2
        for (hx, hy, top) in boxes:
            self.rawclip(cx, cy, hx, hy, eave, min(51, top))

    def clipbox(self, x0, y0, x1, y1, z0, z1):
        """An invisible CLIP box over cells x0..x1, y0..y1 from absolute height z0 to z1."""
        cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
        ix, iy = int(cx), int(cy)
        hx, hy = cx - x0 + (cx - ix), cy - y0 + (cy - iy)
        self.b.clip(ix, iy, hx, hy, z1 - z0, dz=z0 - self.b.cell(ix, iy).floor, sym=False)


def split_even(n, maxlen=16):
    """Split a length into even parts <= maxlen, as equal as possible."""
    assert n % 2 == 0, n
    k = math.ceil(n / maxlen)
    while True:
        base = (n // k) // 2 * 2
        parts = [base] * k
        rest = n - base * k
        i = 0
        while rest > 0: parts[i] += 2; rest -= 2; i += 1
        if max(parts) <= maxlen: return parts
        k += 1


def blocks(w, k, items, base, tex=T_ROUGH):
    """Fallen blocks: (x0, y0, x1, y1, height above base) in the quarter frame; base None = the
    highest floor under the block."""
    for (x0, y0, x1, y1, h) in items:
        box = rbox(k, x0, y0, x1, y1)
        z = base if base is not None else max(w.b.cell(x, y).floor for x in range(box[0], box[2] + 1) for y in range(box[1], box[3] + 1))
        w.b.wall(*box, z + h, tex, ftex=tex, sym=False)


# ── layout after the design sketch v2 (absolute cells) ────────────────────────────────────────────
# Red's side is described, blue's is its mirror across the NW-SE diagonal, (x, y) -> (y, x): the red
# pagoda (SW) and the south side map onto the blue pagoda (NE) and the east side; the NW and SE corners
# mirror onto themselves. Wall lines are 2 cells thick: ("x", s0, s1, r, kind) runs along x over cells
# s0..s1 in rows r, r + 1, ("y", ...) along y in columns r, r + 1. Kinds: plain (closed up to the eave),
# win (closed, baluster windows to see and shoot through), broken (fallen in: a ragged V, passable in
# the middle). Gaps between lines are open.
WALLS_2F = (                                                      # floor F2, eave E2; north and south sides
    # ring hallways: outer walls (south: the middle stair arrives at 264..275, a breach in the SE pocket)
    ("x", 218, 233, 194, "win"), ("x", 234, 247, 194, "win"), ("x", 248, 263, 194, "win"), ("x", 264, 277, 194, "win"),
    ("x", 278, 293, 194, "win"),
    ("x", 218, 233, 316, "win"), ("x", 234, 247, 316, "win"), ("x", 248, 263, 316, "win"), ("x", 276, 282, 316, "plain"),
    ("x", 283, 292, 316, "broken"), ("x", 293, 293, 316, "plain"),
    # ring hallways: inner walls = the courtyards' outer edges (open where the cross hallway starts)
    ("x", 218, 229, 216, "broken"), ("x", 230, 231, 216, "plain"), ("x", 232, 245, 216, "broken"), ("x", 246, 247, 216, "plain"), ("x", 248, 249, 216, "plain"), ("x", 262, 263, 216, "plain"),
    ("x", 264, 275, 216, "plain"), ("x", 276, 289, 216, "broken"), ("x", 290, 293, 216, "plain"),
    ("x", 218, 247, 294, "plain"), ("x", 248, 249, 294, "plain"), ("x", 262, 263, 294, "plain"), ("x", 264, 283, 294, "plain"),
    ("x", 284, 293, 294, "win"),
    # across the ring hallways: broken between the corner pagodas and the Ts, windows towards blue / the SE pocket
    ("y", 196, 215, 230, "broken"), ("y", 196, 215, 270, "win"),
    ("y", 296, 315, 230, "broken"), ("y", 296, 315, 280, "win"),
    # cross hallways: their walls are the courtyards' inner edges
    ("y", 218, 235, 248, "plain"), ("y", 218, 219, 262, "plain"), ("y", 220, 233, 262, "broken"), ("y", 234, 235, 262, "plain"),
    ("y", 276, 279, 248, "plain"), ("y", 280, 291, 248, "broken"), ("y", 292, 293, 248, "plain"), ("y", 276, 293, 262, "plain"))
WALLS_1F = tuple(("x", 176 + 16 * i, 191 + 16 * i, r, "win") for r in (160, 350) for i in range(10)) + (   # floor F1, eave E1
    # gallery inner walls: closed in the north (and west); in the south (and east) broken out to the terrace
    ("x", 176, 335, 174, "plain"),
    ("x", 176, 263, 336, "plain"), ("x", 264, 279, 336, "gone"), ("x", 280, 281, 336, "plain"), ("x", 282, 295, 336, "gone"),
    ("x", 296, 299, 336, "plain"), ("x", 300, 315, 336, "broken"), ("x", 316, 317, 336, "plain"), ("x", 318, 333, 336, "gone"),
    ("x", 334, 335, 336, "plain"),
    ("y", 338, 349, 256, "win"),                                  # across the south gallery: the red half ends here
    ("y", 338, 349, 298, "broken"))                               # ... and a broken one further on
# the great hall's wall broken out above the corner balcony beside red's courtyard (mirror: blue's): drop down from it
HALL_BREACH = ("y", 264, 275, 236, "broken")
TERRACE_WALL = (256, 318, 263, 335)                               # across the south terrace, tall
# stairs between the floors (box, low edge): the middle stair beside the window wall
STAIRS = (((264, 318, 275, 331), "s"), ((318, 264, 331, 275), "e"),
          ((180, 203, 193, 208), "w"), ((203, 180, 208, 193), "n"))         # ... and the NW pagoda's two
RED_FLAG = (205, 305)
# the 1st floor's south-east corner is the ruined one: the gallery vault next to the corner tower fell in on
# both sides (quarter, gallery segment), its stones and fallen pillars lie around (kind, corner x, y, yaw;
# mirrored across the diagonal)
GALLERY_FALLEN = ((2, 0), (1, 9))
# ... and on the 2nd floor the north-west corner: the ring hallway vaults from the NW pagoda to both Ts
RING_FALLEN = ((0, 0), (0, 1), (3, 3), (3, 4), (2, 0), (1, 4))   # NW: both stretches to the Ts; SE: next to the pagoda (the stair exits stay roofed)
FALLEN = (("stones", 328, 344, 0), ("pillar", 310, 341, 0), ("pillar", 288, 346, 0), ("pillar", 288, 330, 900),
          ("pillar", 222, 204, 900), ("pile", 238, 211, 0), ("stones", 240, 201, 0),
          ("pillar", 288, 310, 0), ("stones", 287, 301, 0))                                    # the SE ring beside the pagoda
# walls left without a roof in these corners get ragged tops (still too high to climb)
RUINED = lambda x, y: x + y <= 470 or x + y >= 552
# the 2nd floor's south-east corner broke off along a ragged line around x + y = 626: its rubble slopes down
# over the terrace corner (where the SE pagoda's stairs were), lower towards its sides: the way up into the pagoda
BREAK_LINE = 626
# the NW courtyard is flooded: 10 deep, 3 of it water (a water surface model: AC has one water level per
# map, at the moat), a wooden plank crosses it diagonally between the broken walls, two ladders lead out
POOL, WATER = 10, 13
PLANK = ((239, 217), (217, 239))                                  # its ends (cell corners): breach to breach
# ladders: (corner x, y on the basin wall's face, model yaw, model offset). makke/ladder_10x is a row of staple
# rungs whose legs reach 0.97 cube to one side of its origin (east at yaw 0, west at 1800, north at 2700):
# the model stands one cube out from the wall with its legs on the wall face
LADDERS = ((224, 218, 2700, (0, 1)), (218, 224, 1800, (1, 0)))     # up into the corner breaches' gaps
PAGODA_LADDERS = ((235, 246, 0), (246, 235, 900),                   # up the great hall's west and north walls onto the prang
                  (277, 265, 1800))                                  # ... and out of the closed SE courtyard (east face: x + 1)
# red's and blue's courtyards: a ladder back up through the hall breach onto the balcony
BREACH_LADDERS = ((235, 270, 0), (270, 235, 900))
LOGOS = ((177, 183, 0), (293, 283, 1800))                          # cubeLadder plaques: NW terrace corner, SE courtyard
# ambient sounds (default mapsound slots): idx, x, y, height above the floor, fade radius, full-volume radius, volume
SOUNDS = ((27, 230, 230, 4, 28, 10, 150),                          # NW pool: water and an owl
          (0, 256, 256, 8, 20, 10, 140),                           # great hall: dripping echo under the shaft
          (6, 256, 256, 42, 30, 12, 160),                          # wind on the great pagoda
          (4, 232, 281, 2, 26, 8, 110), (4, 281, 232, 2, 26, 8, 110),  # crickets in red's and blue's courtyards
          (42, 281, 281, 2, 20, 6, 120),                           # flies in the closed SE courtyard
          (44, 206, 206, 10, 35, 0, 100))                          # an owl in the NW pagoda
# a way up the great pillar in the NW corner of the great hall: ledges out of the west and north
# walls, then blocks hanging out towards the middle, each one jump (1 cell, 2 up) higher; from the last a jump onto
# the pillar's platform. (centre, top); 4 x 4 cells each
LEDGES = (((240, 247), 22), ((240, 241), 24), ((245, 240), 26), ((250, 240), 28),
          ((249, 245), 30), ((252, 250), 32), ((249, 255), 34))
LEDGE_ITEMS = ("I_ARMOUR", "I_HELMET", "I_HEALTH", "I_GRENADE")              # highest ledge first
# windows in the walled-up north door (cells along x 250..261, the wall y 236..237; mirrored: the west one):
# (first cell, sill, top), 4 wide x 3 high, in the middle; a lintel model above it, one cube in its lower left corner
DOOR_WINDOWS = ((254, 23, 26),)
COVER = ((252, 230), (230, 252), (259, 281), (281, 259))           # block stacks in the cross hallways before the hall doors
NW_CLEAR = {(239, 214), (214, 227), (213, 227), (212, 234), (213, 225), (245, 213), (210, 222)}         # bushes taken out beside the pool
COURT_TEX = {0: T_FLAG, 1: T_GRASS2, 2: T_GRASS, 3: T_SAND}
COURT_MODELS = {0: [],
                1: [(226, 226, M_TREE, 300), (219, 233, M_BUSH, 0)],
                2: [(221, 243, M_SMALLTREE, 0), (244, 219, M_PLANT, 0)],
                3: [(226, 226, M_PALM, 1300), (243, 221, M_BUSH, 0)]}
RING_SEGS = ((218, 233), (234, 247), (248, 263), (264, 277), (278, 293))   # ring hallway vaults (north side; 2 = the T)
CROSS_SEGS = ((218, 227), (228, 235))
# strangler figs on vault roofs: (quarter, frame box, along_x, eave, lowest floor beside, vault W, H)
FIGS = ((2, (208, 160, 223, 175), True, E1, 2, 16, 5), (3, (234, 194, 247, 217), True, E2, F1, 24, 6),
        (1, (208, 160, 223, 175), True, E1, 2, 16, 5), (1, (264, 194, 277, 217), True, E2, F1, 24, 6),
        (2, (234, 194, 247, 217), True, E2, F1, 24, 6))   # over the south stairs' exit (the east one has its own)


def dmirror(spec):
    axis, s0, s1, r, kind = spec
    return ("y" if axis == "x" else "x", s0, s1, r, kind)


def profile(spec, fl, eave, rnd):
    """Heights along a wall line, and the window centres (offsets of the cell corner)."""
    axis, s0, s1, r, kind = spec
    L = s1 - s0 + 1
    if kind == "plain":
        return [eave] * L, []
    if kind == "win":                                            # 4-cell windows every 8, wall on both ends
        wins = [j for j in range(0, L, 8) if j + 7 <= L - 1]
        return [fl + 2 if any(j + 2 <= t <= j + 5 for j in wins) else eave for t in range(L)], [j + 4 for j in wins]
    if kind == "gone":                                           # fallen completely: a low line of rubble
        profile(spec[:4] + ("broken",), fl, eave, rnd)           # (same random draws as before: the rest stays put)
        return [fl + (1 if (s0 + t) * 7 % 5 == 0 else 0) for t in range(L)], []
    gap = max(4, L // 3)                                         # broken: ragged 2-cell steps down to the floor
    side = (L - gap) // 2
    hs = []
    for t in range(L):
        d = min(t, L - 1 - t)
        h = fl if d >= side else eave - (eave - fl) * (d // 2 * 2) / side - rnd.randint(0, 2)
        hs.append(int(round(max(fl, h))))
    return hs, []


def dpair(b, typ, x, y, dz, a1=0, a2=0, team=False):
    """An entity and its mirror across the NW-SE diagonal (angle mirrored, team swapped)."""
    b.ent(typ, x, y, dz, a1, a2, sym=False)
    if x != y:
        a1m = (2700 - a1) % 3600 if typ in ("PLAYERSTART", "CTF_FLAG") else a1
        b.ent(typ, y, x, dz, a1m, {0: 1, 1: 0}.get(a2, a2) if team else a2, sym=False)


def hidden_qr_codes(w, plat, plank_len, pmx, pmy):
    """The QR hunt (cubeladder.ovh/q/<token>): two codes built as geometry (models.m_qr), from
    private/qr_codes.json (make_qr.py). That file is the secret and is not in the public repository:
    without it the codes are left out. One lies on the great pillar's platform beside the lotus bud
    (seen from above), one hangs under the plank over the flooded pool between two battens (seen from
    the water, looking up). flip: the engine mirrors our meshes, seeing a plate from below mirrors it
    again, so the platform code is built mirrored and the plank code not."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "private", "qr_codes.json")
    if not os.path.exists(path):
        print("QR hunt: private/qr_codes.json missing, hidden codes left out")
        return
    import json
    codes = {c["key"]: c for c in json.load(open(path))}
    if "platform" in codes:
        c = codes["platform"]
        # the platform is 3.6 from the centre to its edge, the lotus bud 1.2: the code (2.2) in between, a hair
        # above the platform's top face (no z-fighting)
        # a model's height is stored in fifths of a cube: place it at a storable height just under the platform's
        # top and lift the tablet inside the model by the rest (plat + 0.02 alone was rounded into the stone)
        z0 = math.floor((plat + 0.02) * 5) / 5
        idx = slot("worn_tablet", lambda r=c["matrix"], oz=plat + 0.02 - z0: models.m_qr(r, 2.2, up=True, flip=True, ox=2.4, oz=oz), "Worn stone tablet")
        w.place(256, 256, idx, 0, z0, mirror=False)
    if "plank" in codes:
        c = codes["plank"]
        # between the two battens nearest the middle (m_plank: n + 1 battens, 0.4 wide, from -L/2 + 0.3)
        n = max(2, int(plank_len / 2.5))
        xs = [-plank_len / 2 + 0.3 + (plank_len - 0.6) * i / n for i in range(n + 1)]
        gap = (xs[n // 2] + xs[n // 2 + 1]) / 2
        assert (xs[1] - xs[0]) - 0.4 >= 2.05, "no room for the code between the battens"
        idx = slot("carved_board", lambda r=c["matrix"], g=gap: models.m_qr(r, 2.0, up=False, flip=False, ox=g), "Carved board")
        yaw = 1350 if (PLANK[1][0] - PLANK[0][0]) * (PLANK[1][1] - PLANK[0][1]) < 0 else 450
        w.place(pmx, pmy, idx, yaw, F2 - 0.5 - 0.25 - 0.03, mirror=False)           # just under the boards (no z-fighting)
    print(f"QR hunt: {len(codes)} hidden code(s) placed")


def jungle(w):
    """The forest takes the temple back (Ta Prohm): moss on the floors, bushes, leafy plants and
    trees in the courtyards and on the terrace between the floors, vines hanging down the walls.
    Different in every quarter."""
    b = w.b
    rnd = random.Random(1999)
    near_stairs = lambda x, y, m: any(a - m <= x <= c + m and b_ - m <= y <= d + m for ((a, b_, c, d), _) in STAIRS)
    for k in range(4):                                                           # moss and grass patches
        for _ in range(150):
            cx, cy, r = rnd.randint(160, 300), rnd.randint(160, 250), rnd.uniform(1.5, 4.5)
            tex = T_GRASS if rnd.random() < 0.7 else T_GRASS2
            for y in range(int(cy - r), int(cy + r) + 1):
                for x in range(int(cx - r), int(cx + r) + 1):
                    if (x - cx) ** 2 + (y - cy) ** 2 > r * r or rnd.random() < 0.25: continue
                    c = b.cell(*rot(k, x, y))
                    if c.type != SOLID and c.floor in (F1, F2, FC, FC + 1, FC + 2, FC + 3):
                        c.ftex = tex
    def plant(k, x, y, idx, floors):
        rx, ry = rot(k, x, y)
        if near_stairs(rx, ry, 3): return False
        if b.cell(rx, ry).floor in floors and all(b.cell(rx + dx, ry + dy).floor == b.cell(rx, ry).floor
                                                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
            b.model(rx, ry, idx, rnd.randint(0, 3599), sym=False)
            return True
        return False
    for k in range(4):
        for _ in range(14):                                                       # courtyards
            x, y = rnd.randint(219, 246), rnd.randint(219, 246)
            if x >= 236 and y >= 236: continue
            plant(k, x, y, rnd.choice((M_BUSH, M_BUSH, M_PLANT, M_PLANT, M_SMALLTREE)), range(FC - 2, F2))
        for _ in range(22):                                                       # the terrace between the floors
            x, y = rnd.randint(178, 330), rnd.randint(177, 192)
            plant(k, x, y, rnd.choice((M_BUSH, M_PLANT, M_PLANT, M_BUSH)), (F1,))
        n = 0
        for _ in range(30):                                                       # big trees against the 2nd floor wall
            x = rnd.randint(214, 298)
            if plant(k, x, 191, rnd.choice((M_TREE2, M_TREE, M_PALM)), (F1,)): n += 1
            if n == 2: break
        for _ in range(8):                                                        # 2nd floor hallways
            x, y = rnd.randint(219, 292), rnd.choice((197, 198, 213, 214))
            plant(k, x, y, rnd.choice((M_PLANT, M_BUSH)), (F2,))
    nw = lambda x, y: x + y <= 470                                                # the roofless NW corner: greener
    for _ in range(90):
        cx, cy, r = rnd.randint(194, 260), rnd.randint(194, 260), rnd.uniform(1.5, 4.5)
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                c = b.cell(x, y)
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and nw(x, y) and c.type != SOLID and rnd.random() < 0.8:
                    c.ftex = T_GRASS if rnd.random() < 0.6 else T_GRASS2
    placed = 0
    for _ in range(400):
        if placed == 45: break
        x, y = rnd.randint(196, 246), rnd.randint(196, 246)
        if not nw(x, y) or (x, y) in w.covered: continue
        if plant(0, x, y, rnd.choice((M_BUSH, M_BUSH, M_PLANT, M_PLANT, M_SMALLTREE)), (F2, F2 - 1, F2 - 2, F2 - 3, F2 - 4)):
            placed += 1
    # vines down the walls: wherever a wall face rises 12..28 above a 6-cell stretch of floor (not near the stairs)
    def vines(h, shifted):
        i = rnd.randint(0, 1)
        key = f"vines_{h}_{i}" + ("s" if shifted else "")
        fn = (lambda: models._shift(models.m_vines(h, 6, 11 * h + i), 0, 1, 0)) if shifted else (lambda: models.m_vines(h, 6, 11 * h + i))
        return slot(key, fn, "Hanging vines")
    cand = []
    for y in range(TA + 1, TB):
        for x in range(TA + 1, TB):
            c = b.cell(x, y)
            if c.type == SOLID or c.type == acmap.FHF: continue
            for (dx, dy) in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                h = b.cell(x + dx, y + dy).floor - c.floor
                if h in (12, 13, 14, 16, 22, 28): cand.append((x, y, dx, dy, h))
    rnd.shuffle(cand)
    taken = []
    ladder_spots = [(lx + ox, ly + oy) for (lx, ly, _, (ox, oy)) in LADDERS] + [(lx, ly) for (lx, ly, _) in PAGODA_LADDERS + BREACH_LADDERS]
    for (x, y, dx, dy, h) in cand:
        if len(taken) == 190: break
        if near_stairs(x, y, 3) or any(abs(x - a) + abs(y - b_) < 7 for (a, b_) in taken): continue
        if any(abs(x - lx) <= 5 and abs(y - ly) <= 5 for (lx, ly) in ladder_spots): continue       # keep the ladders clear
        ax, ay = (1, 0) if dy else (0, 1)
        if not all(b.cell(x + ax * i, y + ay * i).floor == b.cell(x, y).floor and
                   b.cell(x + ax * i + dx, y + ay * i + dy).floor - b.cell(x, y).floor >= h - 1 for i in range(-3, 3)): continue
        yaw = {(0, 1): 0, (1, 0): 900, (0, -1): 1800, (-1, 0): 2700}[(dx, dy)]
        # the model hangs in front of a wall on its +y side; a wall on the south or east side of the cell is
        # one cube away from the cell's corner, where the entity stands: the shifted variant
        w.place(x, y, vines(h, (dx, dy) in ((0, 1), (1, 0))), yaw, b.cell(x, y).floor, mirror=False)
        taken.append((x, y))
    # moss on the walls: patches of wall faces, most of the low broken ones
    hsh = lambda a, c_: ((a * 73856093) ^ (c_ * 19349663)) % 1000 / 1000
    for y in range(TA, TB + 1):
        for x in range(TA, TB + 1):
            c = b.cell(x, y)
            if c.type == SOLID: continue
            rise = c.floor - min(b.cell(x + dx, y + dy).floor for (dx, dy) in ((0, -1), (1, 0), (0, 1), (-1, 0)))
            if rise >= 4 and (hsh(x // 3, y // 3) < (0.5 if x + y <= 470 else 0.25) or (rise <= 9 and hsh(x, y) < 0.55)):
                c.wtex = T_GRASS

def build():
    w = Wat(); b = w.b; m = b.m
    m.ambient = 24
    m.maprevision = 2                     # raise for every version that goes on a server: clients only fetch
                                          # the server's map by themselves when its revision is higher (autogetnewmaprevisions)
    m.waterlevel = -1280                  # no water: AC renders the scene a second time for its reflection
    m.watercolor = (70, 90, 70, 190)

    # everything round the temple is sky-textured solid (shows the skybox). The moat, lawns, compound
    # wall, gates and trees were cut on 2026-10-27 for frame rate (see `strip_scenery`).
    b.solid(0, 0, N - 1, N - 1, 0, sym=False)

    # ── the temple: 1st floor ring (only the south-east L is reached, by the stairs) ──────────
    b.open(157, 157, 354, 354, floor=2, ftex=T_SLAB, wtex=T_LATERITE, sym=False)  # base step
    b.open(TA, TA, TB, TB, floor=F1, ftex=T_SLAB, wtex=T_STONE, sym=False)
    for k in range(4):
        # outer gallery (north side in the frame), as wide as the corner towers
        b.open(*rbox(k, 176, 161, 335, 175), floor=F1, ftex=T_FLAG, wtex=T_STONE, sym=False)
        # corner tower (walk-in)
        b.ring(*rbox(k, 160, 160, 175, 175), 0, b.wall, height=20, wtex=T_STONE, ftex=T_STONE, sym=False)
        b.open(*rbox(k, 161, 161, 174, 174), floor=F1, ftex=T_FLAG, wtex=T_STONE, sym=False)
        b.open(*rbox(k, 175, 162, 175, 173), floor=F1, ftex=T_FLAG, sym=False)          # doors
        b.open(*rbox(k, 162, 175, 173, 175), floor=F1, ftex=T_FLAG, sym=False)
    # ── 2nd floor: platform, sunken courtyards stepped down 4 cubes on every side ─────────────
    b.open(PA, PA, PB, PB, floor=F2, ftex=T_SLAB, wtex=T_STONE, sym=False)
    for k in range(4):
        court = {(x, y) for y in range(218, 248) for x in range(218, 248) if not (x >= 236 and y >= 236)}
        if k == 0:                                                                # flooded: a deep stepped basin
            ring, layer, r = {}, set(court), 1
            while layer:
                edge = {(x, y) for (x, y) in layer if any((x + dx, y + dy) not in layer for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
                for c in edge: ring[c] = r
                layer -= edge; r += 1
            for (x, y), r in ring.items():
                h = POOL                                                          # straight walls, all water
                b.open(x, y, x, y, floor=h, ftex=T_LATERITE if h > POOL else T_MUD, wtex=T_LATERITE, sym=False)
            continue
        layer, h = set(court), F2 - 1
        while layer:
            edge = {(x, y) for (x, y) in layer if h > FC and
                    any((x + dx, y + dy) not in layer for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
            for (x, y) in (edge if h > FC else layer):
                b.open(*rbox(k, x, y, x, y), floor=h, ftex=T_LATERITE if h > FC else COURT_TEX[k], wtex=T_LATERITE, sym=False)
            layer = layer - edge if h > FC else set()
            h -= 1
        if k == 2:                                                                # dry basin
            b.ring(*rbox(k, 222, 222, 231, 231), 0, b.open, floor=FC - 1, ftex=T_LATERITE, wtex=T_LATERITE, sym=False)
            b.open(*rbox(k, 223, 223, 230, 230), floor=FC - 2, ftex=T_MUD, wtex=T_LATERITE, sym=False)
        else:                                                                     # raised planter with a tree
            b.wall(*rbox(k, 222, 222, 231, 231), FC + 1, T_LATERITE, ftex=T_GRASS, sym=False)
    # ── walls of both floors (red's side and its diagonal mirror) ─────────────────────────────
    rnd = random.Random(5)
    windows = []                                                     # (corner x, corner y, along x, floor, eave)
    for (specs, fl, eave) in ((WALLS_2F, F2, E2), (WALLS_1F, F1, E1)):
        for spec in specs:
            hs, wins = profile(spec, fl, eave, rnd)
            for sp in (spec, dmirror(spec)):
                axis, s0, s1, r, _ = sp
                for t, h in enumerate(hs):
                    box = (s0 + t, r, s0 + t, r + 1) if axis == "x" else (r, s0 + t, r + 1, s0 + t)
                    b.wall(*box, h, T_STONE, ftex=T_STONE if h >= eave else T_GRASS, sym=False)
                for c in wins:
                    windows.append(((s0 + c, r + 1) if axis == "x" else (r + 1, s0 + c)) + (axis == "x", fl, eave))
    for box in (TERRACE_WALL, (TERRACE_WALL[1], TERRACE_WALL[0], TERRACE_WALL[3], TERRACE_WALL[2])):
        b.wall(*box, F2 + 6, T_STONE, ftex=T_GRASS, sym=False)
    # ── corner towers: a walk-in hall under the prang roof. The SE one opens to its stairs down to the
    # 1st floor; the others have baluster windows on their outer sides ─────────────────────────
    se_broken, _ = profile(("x", 0, 6, 0, "broken"), F2, EP, rnd)
    for k in range(4):
        b.open(*rbox(k, 194, 194, 217, 217), floor=F2, ftex=T_FLAG, wtex=T_STONE, sym=False)
        for (x0, y0, x1, y1, outer) in ((194, 194, 195, 217, True), (196, 194, 215, 195, True),
                                        (216, 194, 217, 217, False), (196, 216, 215, 217, False)):
            horiz = x1 - x0 > y1 - y0
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    t = (x if horiz else y) - 194
                    if not outer:
                        if 6 <= t <= 17: continue                                 # doors to the hallways
                        h = EP
                    elif k == 2:                                                  # broken down to the 1st floor side
                        if 9 <= t <= 14: continue                                 # door to the stairs
                        if 2 <= t <= 21: continue                                 # gone, no posts left standing
                        h = EP
                    else:
                        if k == 0 and 9 <= t <= 14: continue                       # NW: door to the stairs
                        h = F2 + 2 if any(c - 2 <= t <= c + 1 for c in (5, 12, 19)) else EP
                    b.wall(*rbox(k, x, y, x, y), h, T_STONE, ftex=T_STONE, sym=False)
            if outer and k != 2:
                for c in ((5, 19) if k == 0 else (5, 12, 19)):
                    (px, py) = rotp(k, 194 + c, 195) if horiz else rotp(k, 195, 194 + c)
                    windows.append((px, py, horiz == (k % 2 == 0), F2, EP))
        if k == 0:                                                                # pedestal (the flag pagodas have none)
            b.wall(*rbox(k, 204, 204, 207, 207), F2 + 2, T_STONE, ftex=T_SLAB, sym=False)
        elif k == 2:                                                              # SE: a broad two-step base for the logo
            b.wall(*rbox(k, 200, 200, 211, 211), F2 + 1, T_STONE, ftex=T_SLAB, sym=False)
            b.wall(*rbox(k, 202, 202, 209, 209), F2 + 2, T_STONE, ftex=T_SLAB, sym=False)
    # ── the central hall under the great prang: balcony with baluster windows, ramps up ───────
    b.open(236, 236, 275, 275, floor=F2, ftex=T_FLAG, wtex=T_STONE, sym=False)
    for k in range(4):
        for y in (236, 237):
            for x in range(236, 276):
                t = x - 236
                if 14 <= t <= 25: continue                                         # door, as wide as the cross hallway
                h = FB + 1 if t in (4, 5, 6, 7, 32, 33, 34, 35) else EC
                b.wall(*rbox(k, x, y, x, y), h, T_STONE, ftex=T_STONE, sym=False)
        for c in (242, 270):
            px, py = rotp(k, c, 237)
            windows.append((px, py, k % 2 == 0, FB - 1, FB + 9))
        if k in (1, 3):                                                           # balcony: the SW and NE corners
            b.wall(*rbox(k, 238, 238, 247, 243), FB, T_STONE, ftex=T_SLAB, sym=False)
        else:
            b.wall(*rbox(k, 264, 238, 273, 243), FB, T_STONE, ftex=T_SLAB, sym=False)
    b.wall(253, 253, 258, 258, F2 + 2, T_STONE, ftex=T_SLAB, sym=False)            # Buddha pedestal
    b.wall(250, 236, 261, 237, EC, T_STONE, ftex=T_STONE, sym=False)              # the north and west doors walled up
    b.wall(236, 250, 237, 261, EC, T_STONE, ftex=T_STONE, sym=False)
    for (x0, sill, _) in DOOR_WINDOWS:                                              # the window gaps, down to the sill
        b.wall(x0, 236, x0 + 3, 237, sill, T_STONE, ftex=T_STONE, sym=False)
        b.wall(236, x0, 237, x0 + 3, sill, T_STONE, ftex=T_STONE, sym=False)
        b.wall(x0 + 3, 236, x0 + 3, 237, sill + 1, T_STONE, ftex=T_STONE, sym=False)  # a cube in the corner (left, seen from the hallway)
        b.wall(236, x0 + 3, 237, x0 + 3, sill + 1, T_STONE, ftex=T_STONE, sym=False)
    hs, _ = profile(HALL_BREACH, FB, EC, rnd)
    for (axis, s0, s1, r, _) in (HALL_BREACH, dmirror(HALL_BREACH)):
        for t, h in enumerate(hs):
            box = (s0 + t, r, s0 + t, r + 1) if axis == "x" else (r, s0 + t, r + 1, s0 + t)
            b.wall(*box, h, T_STONE, ftex=T_STONE if h >= EC else T_GRASS, sym=False)
        windows = [wd for wd in windows if not (axis == ("x" if wd[2] else "y") and
                                               (wd[0] if wd[2] else wd[1]) in range(s0, s1 + 2) and (wd[1] if wd[2] else wd[0]) == r + 1)]
    rh = random.Random(77)
    noise = {i: rh.randint(-3, 3) for i in range(-60, 61)}
    intact = lambda x, y: PA <= x <= PB and PA <= y <= PB and (x + y < BREAK_LINE + noise[(x - y) // 3])
    box_ = [(x, y) for y in range(266, 336) for x in range(266, 336) if x >= 276 and y >= 276]
    dist, front = {}, [(x, y) for (x, y) in box_ if intact(x, y)]
    for c in front: dist[c] = 0
    while front:                                                                 # distance out from the break
        nxt = []
        for (x, y) in front:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = (x + dx, y + dy)
                    if 266 <= c[0] <= 335 and 266 <= c[1] <= 335 and c not in dist:
                        dist[c] = dist[(x, y)] + 1; nxt.append(c)
        front = nxt
    for (x, y) in box_:
        if intact(x, y): continue
        h = int(round(F2 - 1 - 0.6 * (dist[(x, y)] - 1) - 0.4 * max(0, abs(x - y) - 4)))   # <= 1 per cell: walkable
        if h > F1 or (PA <= x <= PB and PA <= y <= PB):
            b.wall(x, y, x, y, max(h, F1), T_STONE, ftex=(T_GRASS, T_STONE, T_ROUGH, T_GRASS)[rh.randint(0, 3)], sym=False)
    # ── stairs (ramps last) ────────────────────────────────────────────────────────────────
    for ((x0, y0, x1, y1), d) in STAIRS:
        b.ramp(x0, y0, x1, y1, lo=F1, hi=F2, direction=d, ftex=T_STONE, sym=False)
    for k in (1, 3):                                                              # up to the two balcony corners
        b.ramp(*rbox(k, 244, 244, 252, 247), lo=F2, hi=FB, direction=rdir(k, "e"), ftex=T_STONE, sym=False)

    # ── roofs (models) ──────────────────────────────────────────────────────────────────────
    # hollow too: a shaft 13..16 wide (no pillars in the hall)
    corner_prang = slot("prang_corner_wide", lambda: models.m_prang2(12, 2.6, hole=4.0), "Khmer prang, corner tower", scale=2)
    # hollow: a corbelled shaft 24 wide over the Buddha (no pillars under it), light through slits at the top
    centre_prang = slot("prang_centre_open", lambda: models.m_prang2(20, 0.35, over=0.0, hole=6.0), "Khmer prang, central tower", scale=2)
    for k in range(4):
        x0, y0, x1, y1 = rbox(k, 160, 160, 175, 175)
        w.pav(x0, y0, x1, y1, 16, 16, 18, 3, 20, False)                           # 1st floor corner towers
        x0, y0, x1, y1 = rbox(k, 194, 194, 217, 217)
        w.roof(x0, y0, x1, y1, corner_prang, EP, False)                          # the corner pagodas
        w.prang_clips(x0, y0, x1, y1, EP, 12, 2.6, 2)
        for i in range(10):                                                       # outer gallery
            if (k, i) in GALLERY_FALLEN: continue                                  # fallen in (SE corner)
            w.groof(k, (176 + 16 * i, 160, 191 + 16 * i, 175), True, E1, 5, bw=2.0)
        for i, (s0, s1) in enumerate(RING_SEGS):                                  # ring hallways, the Ts
            if (k, i) in RING_FALLEN: continue
            w.groof(k, (s0, 194, s1, 217), True, E2, 6)
        for (s0, s1) in CROSS_SEGS:                                               # cross hallways
            w.groof(k, (248, s0, 263, s1), False, E2, 6)
    w.roof(236, 236, 275, 275, centre_prang, EC, False)                          # the great pagoda
    pillar = slot("great_pillar", models.m_great_pillar, "Great pillar with a lotus bud", scale=2.4)
    w.place(256, 256, pillar, 0, F2 + 2, mirror=False)                          # on the pedestal
    b.ent("LIGHT", 256, 256, F2 + 2 + 20 - b.cell(256, 256).floor, 22, 230, 235, 255, sym=False)
    plat = F2 + 2 + models.PILLAR_TOP * 2.4                                        # its platform, 36: a jump from the top ledge
    w.rawclip(256, 256, 2.0, 2.0, F2 + 2, plat - 1.2 - (F2 + 2))                  # the shaft
    w.rawclip(256, 256, 3.6, 3.6, plat - 1.2, 1.2)                                 # the platform
    w.rawclip(256, 256, 1.2, 1.2, plat, 2.5)                                       # the lotus bud
    # the cubeLadder logo on the pedestal in the SE corner pagoda, its ladder (and the QR code) to the hall
    lg = slot("cl_logo2", lambda: models.m_cl_logo(0.75, splash=0.9), "cubeLadder logo", scale=2.4)
    w.place(306, 306, lg, 450, F2 + 2, mirror=False)                            # facing NW, into the hall (yaw 450, checked in game)
    b.ent("LIGHT", 306, 306, F2 + 2 + 10 - b.cell(306, 306).floor, 14, 230, 235, 255, sym=False)
    half, ctop, foot = (v * 2.4 for v in models.cl_logo_size(0.75))
    w.rawclip(306, 306, half, half, F2 + 2, ctop)
    lx = int(round(306 - foot / math.sqrt(2))) - 1                                # the ladder's foot, on the hall floor
    b.ent("LADDER", lx, lx, 0, int(math.ceil(F2 + 2 + ctop + 1 - b.cell(lx, lx).floor)), sym=False)
    ledge = slot("ledge_4", models.m_ledge, "Stone ledge (jump platform)")
    for ((cx, cy), top) in LEDGES:
        w.place(cx, cy, ledge, 0, top, mirror=False)
        w.rawclip(cx, cy, 2.0, 2.0, top - 1.2, 1.2)
    # pickups on the top ledges, the best one highest (an item's attr1 lifts both the model and the pickup point)
    for (typ, ((cx, cy), top)) in zip(LEDGE_ITEMS, sorted(LEDGES, key=lambda l: -l[1])):
        b.ent(typ, cx, cy, top - b.cell(cx, cy).floor + 1, int(round((top - b.cell(cx, cy).floor) * 10)), sym=False)
    w.prang_clips(236, 236, 275, 275, EC, 20, 0.35, 2, over=0.0)        # flush with the hall walls
    # an invisible wall around the temple: from the outer roofs nobody jumps out into the scenery
    for k in range(4):
        for (s0, s1) in ((150, 219), (220, 291), (292, 361)):
            x0, y0, x1, y1 = rbox(k, 150, s0, 158, s1)
            w.rawclip((x0 + x1 + 1) // 2, (y0 + y1 + 1) // 2, (x1 - x0 + 1) / 2 + 0.5, (y1 - y0 + 1) / 2 + 0.5, F1 + 2, 51)
    # baluster windows (a clip keeps players from climbing through)
    for (px, py, along_x, fl, eave) in windows:
        h = eave - fl - 2
        bal = slot(f"balusters_{h}", lambda h=h: models.m_balusters(4, h, 6), "Khmer baluster window")
        w.place(px, py, bal, 0 if along_x else 900, fl + 2, mirror=False)
        w.rawclip(px, py, 2 if along_x else 1, 1 if along_x else 2, fl + 2, max(h, 10))
    for (k, box, along_x, eave, low, W, H) in FIGS:                               # strangler figs
        x0, y0, x1, y1 = rbox(k, *box)
        ax = along_x != (k % 2 == 1)
        drop = eave + 1.3 - low
        fig = slot(f"fig_{W}_{H}_{drop:.0f}", lambda W=W, H=H, d=drop: models.m_fig(W, H, d), "Strangler fig on a vault")
        cx, cy = (x0 + x1 + 1) // 2, (y0 + y1 + 1) // 2
        w.place(cx, cy, fig, 900 if ax else 0, eave + 1.3, mirror=False)
        w.rawclip(cx, cy, 2.6, 2.6, eave + 1.3 + H - 1, 16)

    rr = random.Random(41)
    for by in range(TA, TB + 1, 2):
        for bx in range(TA, TB + 1, 2):
            drop = rr.randint(0, 4)
            for (x, y) in ((bx, by), (bx + 1, by), (bx, by + 1), (bx + 1, by + 1)):
                c = b.cell(x, y)
                if c.type == SOLID or (x, y) in w.covered or not RUINED(x, y) or c.floor not in (E1, E2, EP, EC): continue
                if c.floor - min(b.cell(x + dx, y + dy).floor for (dx, dy) in ((0, -1), (1, 0), (0, 1), (-1, 0))) >= 10:
                    c.floor -= drop
                    if drop: c.ftex = T_GRASS
    kinds = {"pillar": (slot("pillar_down", lambda: models.m_square_pillar(12, 1), "Fallen pillar"), [(6.2, 1.2, 0, 2)]),
             "pile": (slot("pillar_pile", models.m_pillar_pile, "Three fallen pillars"), [(6.6, 2.4, 0, 2), (1.3, 4.6, 2, 2)]),
             "stones": (slot("vault_stones", lambda: models.m_vault_debris(10, 9, 44, 3), "Stones of a fallen vault"), [])}
    for (kind, x, y, yaw) in FALLEN:
        idx, cl = kinds[kind]
        for (px, py, a) in ([(x, y, yaw)] + ([(y, x, (2700 - yaw) % 3600)] if x != y else [])):
            z = b.cell(px, py).floor
            w.place(px, py, idx, a, z, mirror=False)
            for (hx, hy, b0, h) in cl:
                w.rawclip(px, py, *((hy, hx) if a % 1800 == 900 else (hx, hy)), z + b0, h)

    # the NW pool: water surface, the plank across, ladders out
    # centred on the pool: the model's axes come out flipped in game, an off-centre plane missed the S and E
    water = slot("pool_water2", lambda: models.m_water_plane(-16, -16, 16, 16, algae=1.0), "Standing water")   # new name: no cached old copy
    w.place(233, 233, water, 0, WATER, mirror=False)
    (ax, ay), (bx, by) = PLANK
    ln = math.hypot(bx - ax, by - ay) + 2
    plank = slot(f"plank_{ln:.0f}", lambda: models.m_plank(ln), "Wooden plank bridge")
    mx, my = (ax + bx) // 2, (ay + by) // 2
    # a diagonal model turns the other way than the quarter turns (checked in game): NE-SW is yaw 1350
    w.place(mx, my, plank, 1350 if (bx - ax) * (by - ay) < 0 else 450, F2 - 0.5, mirror=False)
    steps = max(abs(bx - ax), abs(by - ay))
    for t in range(steps + 1):
        px, py = ax + (bx - ax) * t // steps, ay + (by - ay) * t // steps
        if b.cell(px, py).floor < F2 - 1:
            w.rawclip(px, py, 1.5, 1.5, F2 - 1.5, 1.0)                           # overlapping: a solid walkway
    for (lx, ly, yaw, (ox, oy)) in LADDERS:
        b.ent("LADDER", lx + ox, ly + oy, 0, F2 - POOL - 1, sym=False)          # like the official maps: a cell out, rise - 1
        b.model(lx + ox, ly + oy, M_LADDER, yaw, sym=False)
    for (lx, ly, yaw) in BREACH_LADDERS:                                          # courtyard floor to the balcony (FB)
        rise = FB - b.cell(lx, ly).floor
        b.ent("LADDER", lx, ly, 0, int(rise + 1), sym=False)
        b.model(lx, ly, M_LADDER, yaw, dz=rise - 10, sym=False)                   # one 10-cube ladder, its top at the gap
    for (lx, ly, yaw) in PAGODA_LADDERS:                                          # floor to the slab top (EC + 1.2)
        rise = EC + 1.2 - b.cell(lx, ly).floor
        b.ent("LADDER", lx, ly, 0, int(rise + 1), sym=False)
        for i in range(round(rise / 10)):                                         # 10-cube models, ending at the slab
            b.model(lx, ly, M_LADDER, yaw, dz=10 * i, sym=False)

    for (x0, sill, top) in DOOR_WINDOWS:                                            # lintels up to the hall's eave
        lt = slot(f"lintel_{EC - top}", lambda h=EC - top: models.m_lintel(4.0, 2.0, h), "Wall above a window")
        for (cx, cy, a) in ((x0 + 2, 237, 0), (237, x0 + 2, 900)):
            w.place(cx, cy, lt, a, EC, mirror=False)
            w.rawclip(cx, cy, 2.0, 2.0, top, EC - top)
    stack = slot("block_stack", models.m_block_stack, "Fallen sandstone blocks (cover)")
    for k, (cx, cy) in enumerate(COVER):
        w.place(cx, cy, stack, 900 * k, F2, mirror=False)
        w.rawclip(cx, cy, 1.8, 1.8, F2, 5.0)
    for (si, sx, sy, sz, rad, size, vol) in SOUNDS:
        b.ent("SOUND", sx, sy, sz, si, rad, size, vol, sym=False)
    logo = slot("cl_plaque", models.m_logo_plaque, "cubeLadder plaque")
    for (lx, ly, yaw) in LOGOS:
        w.place(lx, ly, logo, yaw, b.cell(lx, ly).floor + 1.5, mirror=False)
    hidden_qr_codes(w, plat, ln, mx, my)

    jungle(w)
    b.ents[:] = [e for e in b.ents if not (e.name == "MAPMODEL" and e.attr2 == M_BUSH and (e.x, e.y) in NW_CLEAR)]
    w.reanchor()

    # ── entities (red's side, mirrored across the diagonal for blue) ───────────────────────
    dpair(b, "CTF_FLAG", *RED_FLAG, 4, 900, 0, team=True)
    for (x, y, a) in ((205, 299, 0), (205, 312, 0), (198, 305, 900), (213, 305, 900),     # red pagoda
                      (206, 280, 0), (206, 290, 0), (222, 300, 900), (222, 311, 900)):    # its two hallway stretches
        dpair(b, "PLAYERSTART", x, y, 5, a, 0, team=True)
    for (x, y, a) in ((202, 197, 1800), (200, 238, 900), (306, 298, 0), (290, 342, 2700),
                      (280, 328, 0), (256, 240, 1800), (256, 200, 1800)):
        dpair(b, "PLAYERSTART", x, y, 5, a, 100)
    for (t, x, y) in (("I_HEALTH", 210, 276), ("I_HEALTH", 256, 300), ("I_HEALTH", 226, 226),
                      ("I_ARMOUR", 209, 209), ("I_ARMOUR", 313, 313), ("I_HELMET", 230, 285),
                      ("I_CLIPS", 240, 305), ("I_CLIPS", 256, 228),
                      ("I_AMMO", 270, 344), ("I_AMMO", 284, 326), ("I_AMMO", 200, 226),
                      ("I_GRENADE", 250, 262), ("I_AKIMBO", 298, 298),
                      ("I_HELMET", 296, 326), ("I_HEALTH", 326, 326),                         # the SE ruin
                      ("I_GRENADE", 344, 344), ("I_GRENADE", 300, 300),
                      ("I_HEALTH", 244, 200)):                                            # NW ring hallways, near the Ts (mirror: 200, 244)                    # ... a grenade in its 1st floor corner, one in the pagoda hall
        dpair(b, t, x, y, 4)
    # lights: open terraces and courtyards warm, roofed halls dim, flag pagodas tinted
    for y in range(TA + 5, TB, 10):
        for x in range(TA + 5, TB, 10):
            c = b.cell(x, y)
            if c.type not in (SOLID, acmap.FHF) and (x, y) not in w.covered and c.ceil - c.floor >= 5:
                b.light(x, y, radius=14, rgb=(225, 185, 140), dz=8, sym=False)
    for (x, y) in sorted(w.covered):
        c = b.cell(x, y)
        if x % 8 == 0 and y % 8 == 0 and c.type != SOLID and TA <= x <= TB and TA <= y <= TB:
            b.light(x, y, radius=10, rgb=(150, 110, 70), dz=5, sym=False)
    fx, fy = RED_FLAG
    for (x, y) in ((fx, fy), (fx - 6, fy), (fx + 6, fy)):
        b.light(x, y, radius=9, rgb=(255, 120, 90), dz=6, sym=False)
        b.light(y, x, radius=9, rgb=(110, 140, 255), dz=6, sym=False)
    # the courtyards' own plants
    for k in range(4):
        for (x, y, idx, a) in COURT_MODELS[k]:
            rx, ry = rot(k, x, y)
            b.model(rx, ry, idx, (a - 900 * k) % 3600, sym=False)
    big_naga = slot("naga_big", models.m_naga, "Seven-headed naga, temple size", scale=1.6)
    moss_naga = slot("naga_big_moss", lambda: models.m_naga(True), "Seven-headed naga, temple size, overgrown", scale=1.6)
    for k in range(4):                                                            # in every T, facing the great pagoda
        px, py = rotp(k, 256, 206)
        w.place(px, py, moss_naga if k in (2, 3) else big_naga, (2700 - 900 * k + 1800 * (k % 2)) % 3600, F2, mirror=False)   # east and west turned in game
        w.rawclip(px, py, 3, 3, F2, 9)

    # ── header extras ────────────────────────────────────────────────────────────────────
    config = 'fog 1024\nfogcolour 0xD8A070\nloadsky "ladynighthawk/inhcanyons1"\nshadowyaw 300\n'
    config += "mapmodelreset\n" + "".join(f'mapmodel {a} "{n}"\n' for a, n in DEFAULT_MODELS)
    config += "".join(f'mapmodel 0 0 0 {SCALE[k]} "{OWNER}/khmer/{k}"\n' for k in SLOTS)
    m.extras = make_extras((166 - CROP, 166 - CROP, 52, 135, -14), "cc-by-sa-4.0",       # over the NW corner, in written coordinates
                           "Angkor Wat temple CTF: both bases on the 2nd floor, three lanes (2nd floor middle and side, "
                           "a 1st floor flank in the south-east), covered hallways, sunken courtyards, five towers under "
                           "prang roofs, a sniper balcony. By cubeLadder. Models: cubeladder/khmer pack.", config)
    return b.finish()


def strip_scenery(m):
    """Performance (2026-10-27, 32 fps reported): the moat's water was rendered twice (reflection) and the
    lawns, moat, compound wall and trees were drawn from every roof. Everything further than KEEP cells
    outside the temple becomes solid sky (the skybox shows behind the temple), and its entities go."""
    A, B = TA - KEEP, TB + KEEP
    for y in range(m.ssize):
        for x in range(m.ssize):
            if not (A <= x <= B and A <= y <= B):
                c = m.cell(x, y); c.type = acmap.SOLID; c.wtex = 0; c.vdelta = 0
    m.entities = [e for e in m.entities if A <= e.x <= B and A <= e.y <= B]
    return m


def crop(m):
    """The written map: the 256 x 256 window from CROP of the build grid (the temple plus a solid border)."""
    out = copy.deepcopy(m)
    n = 1 << SF_OUT
    assert CROP + 2 <= TA - KEEP and TB + KEEP <= CROP + n - 3, "temple does not fit the window"
    out.sfactor = SF_OUT
    out.cells = [m.cell(CROP + x, CROP + y) for y in range(n) for x in range(n)]
    for e in out.entities:
        e.x -= CROP; e.y -= CROP
    return out


def check(m):
    """Walkability (spawns, flags, items), nobody leaves the temple, the 1st floor is only reached in
    the south-east L, and both flags are reached over the 2nd floor alone."""
    import plan
    st = plan.stand(m)
    out = plan.walk_report(m, st)
    spawns = [(e.x, e.y) for e in m.entities if e.name == "PLAYERSTART"]
    surf = plan.surfaces(m, st)
    r3 = plan.reach3(m, surf, spawns)
    foot = {(x, y) for (x, y, h) in r3}
    tops = [(x, y, h) for e in m.entities if e.name == "LADDER"
            and any((e.x + dx, e.y + dy) in foot for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            for x in range(e.x - 2, e.x + 3) for y in range(e.y - 2, e.y + 3)
            for h in surf.get((x, y), ()) if m.cell(e.x, e.y).floor + 2 < h <= m.cell(e.x, e.y).floor + e.attr1 + 1.3]
    r3 = plan.reach3(m, surf, spawns + tops)                                     # ladders: plan.py has none, start at their tops
    out_of = sorted({(x, y) for (x, y, h) in r3 if not (TA <= x <= TB and TA <= y <= TB)})
    out.append(f"outside the temple: {len(out_of)} reachable cells (roofs included)" + (f"  ESCAPE {out_of[:8]}" if out_of else ""))
    roofs = {(x, y) for (x, y, h) in r3 if h >= E2 + 1 or (E1 + 1 <= h < F2 - 2 and m.cell(x, y).type != acmap.FHF
                                                           and not (PA <= x <= PB and PA <= y <= PB)
                                                           and x + y <= BREAK_LINE)}
    out.append(f"roofs: {len(roofs)} cells reachable" + (" (up the ladder to the great pagoda)" if roofs else " (nothing is broken, no way up)"))
    plat = lambda x, y: PA <= x <= PB and PA <= y <= PB
    low = [[v if v is not None and v < F2 - 4 and not plat(x, y) else None for x, v in enumerate(row)] for y, row in enumerate(st)]
    se = plan.reach(m, low, [(300, 344)])
    nw = plan.reach(m, low, [(184, 184)])
    leak = [c for c in se if c[0] < 256 or c[1] < 256]
    out.append(f"1st floor: south-east L {len(se)} cells, north / west ring {len(nw)} cells"
               + (f"  LEAKS between them {leak[:6]}" if leak or set(se) & set(nw) else ", apart (only over the 2nd floor)"))
    se_court = any(264 <= x <= 293 and 264 <= y <= 293 and not (x <= 275 and y <= 275) for (x, y, h) in r3)
    out.append("SE courtyard: " + ("reachable" if se_court else "closed (seen through its windows)"))
    # the middle: red's pagoda reaches blue's flag without leaving the 2nd floor
    up = [[v if v is not None and v >= FC - 3 and plat(x, y) else None for x, v in enumerate(row)] for y, row in enumerate(st)]
    rf = [(e.x, e.y) for e in m.entities if e.name == "CTF_FLAG"]
    r2 = plan.reach(m, up, [rf[0]])
    out.append("2nd floor: flag to flag " + ("ok" if any(abs(x - rf[1][0]) <= 2 and abs(y - rf[1][1]) <= 2 for (x, y) in r2) else "NO WAY"))
    print("\n".join(out))
    if any(w_ in l for l in out for w_ in ("UNREACHABLE", "NOT STANDABLE", "ESCAPE", "NO WAY", "LEAKS")):
        raise SystemExit("walkability check failed")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else f"maps/{NAME}.cgz"
    m = strip_scenery(build())
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    acmap.write(crop(m), out)
    back = acmap.read(out)
    n = back.ssize
    same = lambda c: (c.type, c.wtex, c.vdelta) if c.type == SOLID else c.key()      # a solid cell stores only these
    assert all(same(back.cell(x, y)) == same(m.cell(CROP + x, CROP + y)) for y in range(n) for x in range(n)), "crop round trip"
    print(f"wrote {out}: {back.ssize}x{back.ssize}, {len(back.entities)} entities, extras {len(back.extras)} B, {len(SLOTS)} custom models")
    rows = models.build_pack("models", "khmer", PACK, "khmer_atlas.png", NAME, owner=OWNER)
    bad = [r for r in rows if r[3]]
    print(f"model pack: {len(rows)} models" + (f", NOT CLOSED: {bad}" if bad else ", all closed"))
    check(m)                                     # in build coordinates (the crop is a pure shift)
