#!/usr/bin/env python3
"""
Top-down floor plan of a map as a PNG, plus layout numbers: the playable bounding box,
open-cell ratio, floor and ceiling ranges, flag positions and distance, spawns per team,
and a walkability check (can each team reach both flags from its spawns?).

    python3 plan.py <map.cgz> <out.png> [scale]
    python3 plan.py reach <map.cgz>            # only the walkability report

Colours: solid black; open cells by floor height (dark blue low, light yellow high);
ceiling below 6 cubes above floor = greyer (crouch / low passage); water = blue;
cells no player can stand on (too narrow, too low, unreachable) are hatched dark red.
Entities: red/blue flag squares, spawn dots per team, pickups green rings.

Walkability follows physics.cpp: the player box is o +- 1.1 cubes, so it covers 3 x 3 cells
when centred on a cell; it needs ceil - floor >= 5.2 over all of them, no solid among them,
can walk up 1.26 cubes (spacelo > -1.26) and jump about 2 cubes. FHF floor = floor minus the
mean of the four vertex vdeltas / 4.
"""
import sys, math
from collections import deque
from PIL import Image, ImageDraw
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import acmap

RADIUS, HEIGHT, STEP, JUMP = 1.1, 5.2, 1.26, 2.2


def phys_floor(m, x, y):
    c = m.cell(x, y)
    if c.type == acmap.FHF:
        v = c.vdelta + m.cell(x + 1, y).vdelta + m.cell(x, y + 1).vdelta + m.cell(x + 1, y + 1).vdelta
        return c.floor - v / 16.0
    return float(c.floor)


def phys_ceil(m, x, y):
    c = m.cell(x, y)
    if c.type == acmap.CHF:
        v = c.vdelta + m.cell(x + 1, y).vdelta + m.cell(x, y + 1).vdelta + m.cell(x + 1, y + 1).vdelta
        return c.ceil + v / 16.0
    return float(c.ceil)


def stand(m):
    """For every cell: the height a player stands at when centred on it, or None if the 3x3 box
    does not fit (solid, corner, too low)."""
    n = m.ssize
    st = [[None] * n for _ in range(n)]
    for y in range(1, n - 2):
        for x in range(1, n - 2):
            lo, hi, ok = -128.0, 127.0, True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    c = m.cell(x + dx, y + dy)
                    if c.type in (acmap.SOLID, acmap.CORNER):
                        ok = False; break
                    lo = max(lo, phys_floor(m, x + dx, y + dy)); hi = min(hi, phys_ceil(m, x + dx, y + dy))
                if not ok: break
            # the player must also be able to stand on this very cell: a position whose box only
            # overlaps a higher ledge is that ledge's, not this cell's
            if ok and hi - lo >= HEIGHT and lo - phys_floor(m, x, y) <= STEP:
                st[y][x] = lo
    # CLIP / PLCLIP boxes: a player centred on the cell may not overlap one that spans its body height
    for e in clips(m):
        for (x, y) in clip_cells(e, n):
            if st[y][x] is not None:
                bottom, top = clip_at(m, e, x + 0.5, y + 0.5)
                if bottom < st[y][x] + HEIGHT and top > st[y][x] + STEP:
                    st[y][x] = None
    return st


def clips(m):
    return [e for e in m.entities if e.name in ("CLIP", "PLCLIP")]


def clip_cells(e, n):
    """Cells whose centred player box overlaps the clip (unrotated clips: attr2 / attr3 half sizes / 5)."""
    hx, hy = e.attr2 / 5, e.attr3 / 5
    for y in range(max(0, int(e.y - hy - RADIUS - 1)), min(n, int(e.y + hy + RADIUS + 1))):
        for x in range(max(0, int(e.x - hx - RADIUS - 1)), min(n, int(e.x + hx + RADIUS + 1))):
            if abs(x + 0.5 - e.x) < hx + RADIUS and abs(y + 0.5 - e.y) < hy + RADIUS:
                yield (x, y)


def clip_at(m, e, px, py):
    """(bottom, top) of a clip for a player at (px, py), as physics.cpp computes it: attr1 elevation
    / 10 over the floor of the clip's cell, attr4 height / 5; a tilted clip (attr6 slope / 40 per
    cube, attr7 1 = along x, 2 = along y) moves up and down in whole-cube steps."""
    cz = m.cell(e.x, e.y).floor + e.attr1 / 10
    s = e.attr6 if e.attr6 < 128 else e.attr6 - 256
    if s and e.attr7 & 3 in (1, 2):
        d, half = (px - e.x, e.attr2 / 5) if e.attr7 & 3 == 1 else (py - e.y, e.attr3 / 5)
        d += RADIUS * (1 if s > 0 else -1)
        cz += math.floor(0.5 + max(-half, min(half, d))) * s / 40
    return cz, cz + e.attr4 / 5


def surfaces(m, st):
    """Every height a player can stand at, per cell: the ground (stand()) and the tops of CLIP boxes
    (roofs). Returns {(x, y): [heights]}."""
    n = m.ssize
    cl = clips(m)
    hits = {}
    for e in cl:
        for c in clip_cells(e, n):
            hits.setdefault(c, []).append(e)
    surf = {}
    surf_hits = hits
    for y in range(n):
        for x in range(n):
            if st[y][x] is not None:
                surf[(x, y)] = [st[y][x]]
    for (x, y), es in hits.items():
        box = [m.cell(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        if any(c.type in (acmap.SOLID, acmap.CORNER) for c in box):
            continue
        ground = max(phys_floor(m, x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        ceil = min(phys_ceil(m, x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        spans = [clip_at(m, e, x + 0.5, y + 0.5) for e in es]
        out = []
        for (_, top) in spans:
            if top < ground + STEP: continue
            h = top
            for (b2, t2) in spans:                       # stepping onto a slightly higher clip
                if h < t2 <= h + STEP: h = t2
            if ceil - h < HEIGHT: continue
            if any(b2 < h + HEIGHT and t2 > h + STEP for (b2, t2) in spans): continue
            if all(abs(h - o) > 0.3 for o in out): out.append(h)
        if out:
            surf.setdefault((x, y), []).extend(out)
    surf[None] = {c: [clip_at(m, e, c[0] + 0.5, c[1] + 0.5) for e in es] for c, es in surf_hits.items()}
    return surf


def passable(m, surf, x, y, h):
    """Can a player pass over cell (x, y) at height h (mid-jump)? The 3 x 3 box is clear of solid
    cells and of floors above h + STEP, the ceiling leaves room, and no clip spans the body."""
    box = [(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    if any(m.cell(a, b).type in (acmap.SOLID, acmap.CORNER) for (a, b) in box): return False
    if max(phys_floor(m, a, b) for (a, b) in box) > h + STEP: return False
    if min(phys_ceil(m, a, b) for (a, b) in box) < h + HEIGHT: return False
    return not any(b < h + HEIGHT and t > h + STEP for (b, t) in surf[None].get((x, y), ()))


def reach3(m, surf, starts, longdrop=True):
    """Like reach(), over several standing heights per cell (roofs on clips): moves of 1-3 cells rise
    at most JUMP, running jumps down cover 3 cells + 1 per 1.5 cubes of drop (at most 10); every cell
    jumped across must let the player box pass at the start height (passable()). Returns the set of
    (x, y, height)."""
    seen = set()
    q = deque()
    for s in starts:
        if len(s) == 3:                                    # a given height (e.g. the top of a ladder)
            seen.add(s); q.append(s); continue
        for h in surf.get(s, [])[:1]:
            seen.add(s + (h,)); q.append(s + (h,))
    while q:
        x, y, h = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for k in range(1, 11):
                nx, ny = x + dx * k, y + dy * k
                c = m.cell(nx, ny)
                if c.type == acmap.SOLID or phys_floor(m, nx, ny) > h + JUMP and (nx, ny) not in surf: break
                for t in surf.get((nx, ny), ()):
                    rise = t - h
                    ok = rise <= JUMP if k <= 3 else (longdrop and rise < 0 and k <= 3 + (-rise) / 1.5)
                    if ok and (nx, ny, t) not in seen:
                        seen.add((nx, ny, t)); q.append((nx, ny, t))
                if (k >= 3 and not longdrop) or not passable(m, surf, nx, ny, h + (JUMP if k <= 2 else 0)): break
    return seen


def reach(m, st, starts, jump=JUMP):
    """Cells reachable from the start cells. A walk goes to a 4-neighbour with a rise <= STEP; a jump
    goes 2 or 3 cells straight ahead with a rise <= jump (the cells at the foot of a ledge cannot
    hold a standing player, so a ledge is always crossed in one jump), provided no solid cell is in
    the way and there is headroom over the cells jumped across."""
    n = m.ssize
    seen = set()
    q = deque()
    for (x, y) in starts:
        if st[y][x] is not None and (x, y) not in seen:
            seen.add((x, y)); q.append((x, y))
    while q:
        x, y = q.popleft()
        h = st[y][x]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for k in (1, 2, 3):
                nx, ny = x + dx * k, y + dy * k
                if not (0 <= nx < n and 0 <= ny < n): break
                c = m.cell(nx, ny)
                if c.type == acmap.SOLID: break
                if phys_ceil(m, nx, ny) - max(h, phys_floor(m, nx, ny)) < HEIGHT: break
                t = st[ny][nx]
                if t is not None and (nx, ny) not in seen and t - h <= (STEP if k == 1 else jump):
                    seen.add((nx, ny)); q.append((nx, ny))
                if t is not None and k == 1 and t - h <= STEP: break      # plain walking covers the rest
    return seen


def near(st, x, y, r=1):
    """A standable cell at or next to (x, y) (flags and items sit on cells a player only has to touch)."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if 0 <= y + dy < len(st) and 0 <= x + dx < len(st) and st[y + dy][x + dx] is not None:
                return (x + dx, y + dy)
    return None


def walk_report(m, st=None):
    st = st or stand(m)
    flags = {e.attr2: e for e in m.entities if e.name == "CTF_FLAG"}
    spawns = {}
    for e in m.entities:
        if e.name == "PLAYERSTART":
            spawns.setdefault(e.attr2, []).append(e)
    items = [e for e in m.entities if e.name.startswith("I_")]
    out = []
    all_reach = set()
    for team, name in ((0, "red"), (1, "blue"), (100, "ffa")):
        sp = spawns.get(team, [])
        bad = [(e.x, e.y) for e in sp if st[e.y][e.x] is None]
        starts = [(e.x, e.y) for e in sp if st[e.y][e.x] is not None]
        r = reach(m, st, starts)
        all_reach |= r
        line = f"{name:4s} spawns {len(sp):2d}" + (f"  NOT STANDABLE {bad}" if bad else "")
        for ft, fe in sorted(flags.items()):
            c = near(st, fe.x, fe.y)
            line += f"  -> {'red' if ft == 0 else 'blue'} flag ({fe.x},{fe.y}): " + ("ok" if c and c in r else "UNREACHABLE")
        line += f"  reach {len(r)} cells"
        out.append(line)
    lost = [(e.name, e.x, e.y) for e in items if not (near(st, e.x, e.y) and near(st, e.x, e.y) in all_reach)]
    out.append(f"items {len(items)}" + (f"  UNREACHABLE {lost}" if lost else "  all reachable"))
    standable = sum(1 for row in st for v in row if v is not None)
    out.append(f"standable cells {standable}, reachable from any spawn {len(all_reach)}")
    return out


def stats(m):
    opens = [(x, y, m.cell(x, y)) for y in range(m.ssize) for x in range(m.ssize) if m.cell(x, y).type != acmap.SOLID and m.cell(x, y).ceil - m.cell(x, y).floor >= 5]
    x1 = min(x for x, y, c in opens); x2 = max(x for x, y, c in opens)
    y1 = min(y for x, y, c in opens); y2 = max(y for x, y, c in opens)
    floors = [c.floor for x, y, c in opens]; ceils = [c.ceil for x, y, c in opens]
    flags = [e for e in m.entities if e.name == "CTF_FLAG"]
    spawns = {}
    for e in m.entities:
        if e.name == "PLAYERSTART":
            spawns[e.attr2] = spawns.get(e.attr2, 0) + 1
    fd = math.dist((flags[0].x, flags[0].y), (flags[1].x, flags[1].y)) if len(flags) == 2 else None
    return dict(title=m.title, size=m.ssize, box=(x1, y1, x2, y2), span=(x2 - x1 + 1, y2 - y1 + 1), open_cells=len(opens),
                open_ratio=round(len(opens) / ((x2 - x1 + 1) * (y2 - y1 + 1)), 2), floor=(min(floors), max(floors)), ceil=(min(ceils), max(ceils)),
                flags=[(e.x, e.y, e.z, e.attr2) for e in flags], flag_distance=round(fd, 1) if fd else None, spawns=spawns,
                lights=sum(1 for e in m.entities if e.name == "LIGHT"), ambient=m.ambient, waterlevel=m.waterlevel,
                mapmodels=sum(1 for e in m.entities if e.name == "MAPMODEL"), items=sum(1 for e in m.entities if e.name.startswith("I_")))


def draw(m, out, scale=6, crop=True):
    st = stats(m)
    sd = stand(m)
    starts = [(e.x, e.y) for e in m.entities if e.name == "PLAYERSTART"]
    reached = reach(m, sd, starts)
    x1, y1, x2, y2 = st["box"]
    if not crop:
        x1 = y1 = 0; x2 = y2 = m.ssize - 1
    pad = 3
    x1 -= pad; y1 -= pad; x2 += pad; y2 += pad
    w, h = (x2 - x1 + 1), (y2 - y1 + 1)
    im = Image.new("RGB", (w * scale, h * scale), (0, 0, 0))
    d = ImageDraw.Draw(im)
    fmin, fmax = st["floor"]
    for y in range(max(0, y1), min(m.ssize, y2 + 1)):
        for x in range(max(0, x1), min(m.ssize, x2 + 1)):
            c = m.cell(x, y)
            if c.type == acmap.SOLID:
                continue
            h_ = c.ceil - c.floor
            t = (c.floor - fmin) / max(1, fmax - fmin)
            col = (int(40 + 215 * t), int(60 + 180 * t), int(120 - 100 * t))
            if m.waterlevel > -1000 and c.floor * 10 < m.waterlevel:
                col = (30, 80, 200)
            if h_ < 5:
                col = tuple(v // 3 for v in col)
            if c.type in (acmap.FHF, acmap.CHF):
                col = (col[0], col[1], min(255, col[2] + 60))
            if c.type == acmap.CORNER:
                col = tuple(v // 2 for v in col)
            px, py = (x - x1) * scale, (y - y1) * scale
            d.rectangle((px, py, px + scale - 1, py + scale - 1), fill=col)
            if (x, y) not in reached:                    # nobody can stand here: hatch it
                d.line((px, py + scale - 1, px + scale - 1, py), fill=(140, 0, 0))
    for e in m.entities:
        px, py = (e.x - x1) * scale, (e.y - y1) * scale
        if e.name == "CTF_FLAG":
            d.rectangle((px - scale, py - scale, px + 2 * scale, py + 2 * scale), fill=(255, 0, 0) if e.attr2 == 0 else (0, 90, 255), outline=(255, 255, 255))
        elif e.name == "PLAYERSTART":
            col = (255, 80, 80) if e.attr2 == 0 else (80, 140, 255) if e.attr2 == 1 else (255, 255, 255)
            d.ellipse((px, py, px + scale, py + scale), fill=col)
        elif e.name.startswith("I_"):
            d.ellipse((px + 1, py + 1, px + scale - 1, py + scale - 1), outline=(0, 255, 0))
        elif e.name == "LADDER":
            d.rectangle((px, py, px + scale, py + scale), outline=(255, 255, 0))
    im.save(out)
    return st, sd


if __name__ == "__main__":
    if sys.argv[1] == "reach":
        m = acmap.read(sys.argv[2])
        print("\n".join(walk_report(m)))
        sys.exit()
    m = acmap.read(sys.argv[1])
    st, sd = draw(m, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)
    for k, v in st.items():
        print(f"{k}: {v}")
    print("\n".join(walk_report(m, sd)))
