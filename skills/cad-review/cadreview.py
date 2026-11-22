# -*- coding: utf-8 -*-
"""Pre-print review of the STL files that actually go to the printer.

Run with FreeCAD's interpreter (it has Mesh, Part and numpy):

    "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" cadreview.py <spec.json>

Pass ONLY a .json path after the script. freecadcmd tries to open .stl/.step
arguments itself.

Everything here is measured from the exported mesh, never from params.py,
so it catches what a self-checking build script cannot: a stale STL, wrong
units, a mirrored part, a bore that came out a different size, a wall the
slicer will drop, a part that won't stay on the bed.

Spec format (all keys except "parts[].stl" are optional):

{
  "out": "C:/.../review",               # report + PNGs go here
  "bed": [256, 256, 256],               # Bambu P1S
  "source": ["C:/.../params.py"],       # STL must be newer than these
  "min_wall": 0.8,                      # 2 lines of a 0.4 nozzle
  "min_gap": 0.4,                       # gaps narrower than this fuse shut
  "parts": [{
    "stl": "C:/.../DriveDisk_RH.stl",
    "name": "DriveDisk_RH",
    "bbox": [40.0, 40.0, 12.0], "bbox_tol": 0.3,
    "planes": [                          # extra sections to measure + draw
      {"axis": "z", "at": 3.0, "label": "bore"}
    ],
    "holes": [                           # expected round holes
      {"label": "TT shaft", "axis": "z", "at": 3.0, "d": 5.7, "flats": 3.9,
       "tol": 0.1, "near": [20, 20], "source": "measured, pinion test print"}
    ],
    "coupon": {"min": [0, 0, 0], "max": [40, 40, 4]}   # write a test slice
  }]
}

Exit code is 1 when any FAIL line was written.
"""

import os, sys, json, math, time, zlib, struct

_RAN = globals().get("_CADREVIEW_RAN", False)
_CADREVIEW_RAN = True

import numpy as np
import FreeCAD as App
import Mesh

AX = {"x": 0, "y": 1, "z": 2}
NRM = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


# ----------------------------------------------------------------- report
class Report(object):
    def __init__(self):
        self.lines, self.fails, self.warns = [], 0, 0

    def head(self, s):
        self.lines += ["", s]

    def row(self, tag, what, detail=""):
        if tag == "FAIL":
            self.fails += 1
        if tag == "WARN":
            self.warns += 1
        self.lines.append("  [%-4s] %-48s %s" % (tag, what, detail))

    def note(self, s):
        self.lines.append("         " + s)

    def text(self):
        return "\n".join(self.lines) + "\n"


# ------------------------------------------------------------- mesh basics
def arrays(mesh):
    pts, fac = mesh.Topology
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float)
    F = np.array(fac, dtype=int)
    return P, F


def normals(P, F):
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    n = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(n, axis=1)
    n = n / np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-12)
    return n, area


def sections(mesh, axis, at):
    base = [0.0, 0.0, 0.0]
    base[AX[axis]] = float(at)
    res = mesh.crossSections([(App.Vector(*base), App.Vector(*NRM[axis]))], 1e-6)
    loops = []
    for pl in res[0]:
        q = [(v.x, v.y, v.z) for v in pl]
        if len(q) < 4:
            continue
        loops.append(np.array(q))
    return loops


def to2d(loop, axis):
    k = [i for i in range(3) if i != AX[axis]]
    return loop[:, k]


def poly_area(q):
    x, y = q[:, 0], q[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def poly_perim(q):
    return float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1)))


def inside(pt, q):
    x, y = pt
    xs, ys = q[:, 0], q[:, 1]
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    cross = ((ys > y) != (y2 > y))
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = xs + (y - ys) * (x2 - xs) / (y2 - ys)
    return int(np.sum(cross & (x < xi))) % 2 == 1


def loops_info(loops, axis):
    """Classify section loops: outer/hole, size, roundness, centre."""
    out = []
    q2 = [to2d(l, axis) for l in loops]
    for i, q in enumerate(q2):
        a = abs(poly_area(q))
        p = poly_perim(q)
        if a < 1e-4 or p < 1e-4:
            continue
        cx, cy = float(q[:, 0].mean()), float(q[:, 1].mean())
        depth = sum(1 for j, o in enumerate(q2) if j != i and inside((cx, cy), o)
                    and abs(poly_area(o)) > a)
        r = np.linalg.norm(q - [cx, cy], axis=1)
        ang = np.radians(np.arange(0, 180, 1.0))
        proj = q @ np.stack([np.cos(ang), np.sin(ang)])
        cal = proj.max(0) - proj.min(0)       # caliper width at each angle
        out.append(dict(area=a, perim=p, c=(cx, cy), hole=(depth % 2 == 1),
                        w_min=float(cal.min()), w_max=float(cal.max()),
                        w_mean=float(cal.mean()),
                        round=4 * math.pi * a / (p * p),
                        d_area=2 * math.sqrt(a / math.pi),
                        d_min=2 * float(r.min()), d_max=2 * float(r.max()),
                        q=q))
    return out


# --------------------------------------------------------- raster of a slice
def raster(loops2d, lo, hi, cell):
    """Even-odd scanline fill of 2-D loops -> boolean grid (rows = axis 2)."""
    nx = int(math.ceil((hi[0] - lo[0]) / cell)) + 1
    ny = int(math.ceil((hi[1] - lo[1]) / cell)) + 1
    g = np.zeros((ny, nx), dtype=bool)
    if not loops2d:
        return g
    E = np.concatenate([np.stack([q, np.roll(q, -1, axis=0)], axis=1)
                        for q in loops2d])
    y0, y1 = E[:, 0, 1], E[:, 1, 1]
    x0, x1 = E[:, 0, 0], E[:, 1, 0]
    xs = lo[0] + (np.arange(nx) + 0.5) * cell
    for r in range(ny):
        y = lo[1] + (r + 0.5) * cell
        m = (y0 > y) != (y1 > y)
        if not m.any():
            continue
        xi = np.sort(x0[m] + (y - y0[m]) * (x1[m] - x0[m]) / (y1[m] - y0[m]))
        for a, b in zip(xi[0::2], xi[1::2]):
            g[r, (xs >= a) & (xs <= b)] = True
    return g


def _disk(rc):
    o = []
    for dy in range(-rc, rc + 1):
        for dx in range(-rc, rc + 1):
            if dx * dx + dy * dy <= rc * rc:
                o.append((dy, dx))
    return o


def _shift(g, dy, dx, fill):
    h, w = g.shape
    o = np.full_like(g, fill)
    o[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = \
        g[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return o


def erode(g, rc):
    o = g.copy()
    for dy, dx in _disk(rc):
        o &= _shift(g, dy, dx, False)
    return o


def dilate(g, rc):
    o = g.copy()
    for dy, dx in _disk(rc):
        o |= _shift(g, dy, dx, False)
    return o


def thin_and_gaps(loops, axis, min_wall, min_gap, cell=0.1):
    """Material thinner than min_wall, and gaps narrower than min_gap.

    Opening (erode then dilate) by min_wall/2 removes walls thinner than
    min_wall; closing by min_gap/2 fills gaps narrower than min_gap. The
    difference is what the slicer will drop or fuse.
    """
    q2 = [to2d(l, axis) for l in loops]
    if not q2:
        return 0.0, None, 0.0, None
    allp = np.concatenate(q2)
    lo, hi = allp.min(0) - 1.0, allp.max(0) + 1.0
    g = raster(q2, lo, hi, cell)
    rw = max(1, int(round(min_wall / 2 / cell)) - 1)
    rg = max(1, int(round(min_gap / 2 / cell)) - 1)
    opened = dilate(erode(g, rw), rw)
    thin = g & ~opened
    closed = erode(dilate(g, rg), rg)
    gap = closed & ~g

    def where(m):
        if not m.any():
            return None
        ys, xs = np.nonzero(m)
        return (lo[0] + xs.mean() * cell, lo[1] + ys.mean() * cell)

    a = cell * cell
    return float(thin.sum() * a), where(thin), float(gap.sum() * a), where(gap)


# ------------------------------------------------------------------ images
def _png(path, w, h, px):
    raw = b"".join(b"\x00" + px[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6))
                + chunk(b"IEND", b""))


def _basis(view):
    d = np.array(view, dtype=float)
    d /= np.linalg.norm(d)
    up = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.array([0.0, 1.0, 0.0])
    r = np.cross(d, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    return r, u, d


def render(P, F, n, path, view, red=None, w=800, h=600, margin=24):
    """Shaded orthographic z-buffer render. red: facet mask tinted red."""
    R, U, D = _basis(view)
    L = -np.array([-0.4, -0.6, -1.0])
    L /= np.linalg.norm(L)
    sx, sy, sz = P @ R, -(P @ U), P @ D
    span = max(sx.max() - sx.min(), 1e-6), max(sy.max() - sy.min(), 1e-6)
    sc = min((w - 2 * margin) / span[0], (h - 2 * margin) / span[1])
    X = (w - sc * span[0]) / 2 + sc * (sx - sx.min())
    Y = (h - sc * span[1]) / 2 + sc * (sy - sy.min())
    shade = 0.30 + 0.70 * np.abs(n @ L)
    base = np.array([170, 185, 205], dtype=float)
    col = (base[None, :] * shade[:, None])
    if red is not None:
        col[red] = np.array([230, 60, 50])[None, :] * shade[red][:, None]
    col = np.clip(col, 0, 255).astype(np.uint8)
    img = np.full((h, w, 3), 250, dtype=np.uint8)
    zb = np.full((h, w), np.inf)
    for i, (a, b, c) in enumerate(F):
        x0, x1, x2 = X[a], X[b], X[c]
        y0, y1, y2 = Y[a], Y[b], Y[c]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        xa, xb = max(0, int(min(x0, x1, x2))), min(w - 1, int(max(x0, x1, x2)) + 1)
        ya, yb = max(0, int(min(y0, y1, y2))), min(h - 1, int(max(y0, y1, y2)) + 1)
        if xa > xb or ya > yb:
            continue
        gx, gy = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        l2 = 1.0 - l0 - l1
        m = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not m.any():
            continue
        z = l0 * sz[a] + l1 * sz[b] + l2 * sz[c]
        sub = zb[ya:yb + 1, xa:xb + 1]
        m &= z < sub
        sub[m] = z[m]
        img[ya:yb + 1, xa:xb + 1][m] = col[i]
    _png(path, w, h, img)


def draw_section(infos, path, w=700, h=700, margin=30, mark=()):
    """Filled section; holes outlined blue, expected-hole centres as red dots."""
    if not infos:
        return
    allp = np.concatenate([i["q"] for i in infos])
    lo, hi = allp.min(0), allp.max(0)
    span = np.maximum(hi - lo, 1e-6)
    sc = min((w - 2 * margin) / span[0], (h - 2 * margin) / span[1])
    cell = 1.0 / sc
    g = raster([i["q"] for i in infos], lo, lo + np.array([w, h]) * cell, cell)
    g = g[:h, :w]
    img = np.full((h, w, 3), 250, dtype=np.uint8)
    ox, oy = margin, margin
    hh, ww = g.shape
    view = img[oy:oy + hh, ox:ox + ww]
    gg = g[:view.shape[0], :view.shape[1]]
    view[gg] = (90, 100, 120)
    for inf in infos:
        if not inf["hole"]:
            continue
        q = inf["q"]
        for (x0, y0), (x1, y1) in zip(q, np.roll(q, -1, axis=0)):
            k = max(2, int(math.hypot(x1 - x0, y1 - y0) * sc))
            for t in np.linspace(0, 1, k):
                px = int(ox + (x0 + t * (x1 - x0) - lo[0]) * sc)
                py = int(oy + (y0 + t * (y1 - y0) - lo[1]) * sc)
                if 0 <= px < w and 0 <= py < h:
                    img[max(0, py - 1):py + 2, max(0, px - 1):px + 2] = (40, 110, 230)
    for x, y in mark:
        px, py = int(ox + (x - lo[0]) * sc), int(oy + (y - lo[1]) * sc)
        img[max(0, py - 4):py + 5, max(0, px - 4):px + 5] = (230, 50, 40)
    _png(path, w, h, img[::-1].copy())     # y up


# ------------------------------------------------------------------ coupon
def coupon(stl, lo, hi, out):
    """Cut a test slice out of the part, for printing a critical fit cheaply.

    Prefer cutting the coupon from the source shape in the build script
    (exact geometry); this mesh route is for when only the STL exists.
    """
    import Part
    m = Mesh.Mesh(stl)
    s = Part.Shape()
    s.makeShapeFromMesh(m.Topology, 0.05)
    solid = Part.makeSolid(Part.makeShell(s.Faces)).removeSplitter()
    box = Part.makeBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                       App.Vector(*lo))
    c = solid.common(box)
    c.translate(App.Vector(0, 0, -c.BoundBox.ZMin))
    mm = Mesh.Mesh()
    mm.addFacets(c.tessellate(0.02))
    mm.write(out)
    return c.Volume, c.BoundBox


# -------------------------------------------------------------- per part
def review_part(spec, part, rep, out):
    stl = part["stl"]
    name = part.get("name") or os.path.splitext(os.path.basename(stl))[0]
    rep.head("PART  %s   (%s)" % (name, stl))
    if not os.path.exists(stl):
        rep.row("FAIL", "STL exists", "missing")
        return
    mt = os.path.getmtime(stl)
    rep.row("INFO", "STL written", time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)))
    for src in spec.get("source", []):
        if os.path.exists(src) and os.path.getmtime(src) > mt + 1:
            rep.row("FAIL", "STL is up to date with its source",
                    "%s was edited AFTER the STL - rebuild first" % os.path.basename(src))

    m = Mesh.Mesh(stl)
    bb = m.BoundBox
    P, F = arrays(m)
    n, area = normals(P, F)
    size = (bb.XLength, bb.YLength, bb.ZLength)

    # --- mesh sanity
    comps = m.countComponents()
    rep.row("PASS" if comps == 1 else "FAIL", "one piece (connected shells)",
            "%d shell(s)%s" % (comps, "" if comps == 1 else " - floating lumps or a fuse that didn't"))
    rep.row("PASS" if m.isSolid() else "FAIL", "watertight", "")
    nm = m.hasNonManifolds()
    rep.row("FAIL" if nm else "PASS", "manifold", "non-manifold edges" if nm else "")
    vol = m.Volume
    rep.row("PASS" if vol > 0 else "FAIL", "normals point outward",
            "volume %.1f cm3" % (vol / 1000.0) + ("" if vol > 0 else " (negative: inside-out)"))
    rep.row("INFO", "size", "%.2f x %.2f x %.2f mm, %d facets, ~%.0f g PLA solid"
            % (size + (m.CountFacets, vol / 1000.0 * 1.24)))

    # --- units / scale
    big = max(size)
    if big < 3.0:
        rep.row("FAIL", "units", "largest side %.2f mm - exported in cm/m/inch?" % big)
    elif big > 600:
        rep.row("FAIL", "units", "largest side %.0f mm - exported in micro-units?" % big)
    exp = part.get("bbox")
    if exp:
        tol = part.get("bbox_tol", 0.3)
        d = [abs(a - b) for a, b in zip(size, exp)]
        ok = max(d) <= tol
        msg = "got %.2f x %.2f x %.2f, want %.2f x %.2f x %.2f" % (tuple(size) + tuple(exp))
        sexp, ssz = sorted(exp), sorted(size)
        if not ok and max(abs(a - b) for a, b in zip(ssz, sexp)) <= tol:
            msg += " - right sizes, WRONG ORIENTATION"
        for f in (25.4, 10.0, 0.1, 1 / 25.4):
            if not ok and max(abs(a * f - b) for a, b in zip(size, exp)) <= tol * 2:
                msg += " - off by x%.4g: unit error" % f
        rep.row("PASS" if ok else "FAIL", "bounding box matches the requirement", msg)

    # --- bed
    bed = spec.get("bed", [256, 256, 256])
    fits = sorted(size[:2]) <= sorted(bed[:2]) and size[2] <= bed[2]
    rep.row("PASS" if fits else "FAIL", "fits the bed %gx%gx%g" % tuple(bed),
            "" if fits else "too big in this pose")
    if abs(bb.ZMin) > 0.01:
        rep.row("WARN", "part sits on z=0", "ZMin = %.2f (slicer will drop it, check pose)" % bb.ZMin)

    # --- first layer
    z0 = bb.ZMin + 0.1
    first = [i for i in loops_info(sections(m, "z", z0), "z")]
    fa = sum(i["area"] * (-1 if i["hole"] else 1) for i in first)
    ratio = bb.ZLength / max(math.sqrt(max(fa, 1e-6)), 1e-6)
    tag = "PASS"
    msg = "%.0f mm2 on the plate, height/footprint %.1f" % (fa, ratio)
    if fa < 25:
        tag, msg = "WARN", msg + " - tiny contact, add brim or reorient"
    elif ratio > 4:
        tag, msg = "WARN", msg + " - tall and narrow, may topple or wobble (brim)"
    rep.row(tag, "first layer holds the part", msg)
    flat = np.sum(area[(n[:, 2] < -0.99) & (np.abs(P[F[:, 0], 2] - bb.ZMin) < 0.05)])
    rep.note("flat downward faces on the plate: %.0f mm2 (elephant foot shrinks "
             "holes and grows outlines in the first ~0.3 mm)" % flat)

    # --- overhang hint (cad-validation's needs_support judges ledges/bridges)
    zc = P[F, 2].mean(axis=1)
    down = (n[:, 2] < -math.cos(math.radians(45))) & (zc > bb.ZMin + 0.3)
    oa = float(area[down].sum())
    rep.row("WARN" if oa > 5 else "PASS", "downward faces steeper than 45 deg",
            "%.0f mm2 above the plate (red in the renders)" % oa)
    if oa > 5:
        zs = np.round(zc[down]).astype(int)
        top = sorted(set(zs.tolist()))[:8]
        rep.note("at z ~ %s - judge ledge vs bridge with cadcheck.needs_support" % top)

    # --- thin walls and closing gaps, on a stack of slices
    mw, mg = spec.get("min_wall", 0.8), spec.get("min_gap", 0.4)
    levels = list(np.linspace(bb.ZMin + 0.3, bb.ZMax - 0.3, 12)) if bb.ZLength > 1 else []
    worst_t, worst_g = (0, None, None), (0, None, None)
    for z in levels:
        loops = sections(m, "z", z)
        ta, tw, ga, gw = thin_and_gaps(loops, "z", mw, mg)
        if ta > worst_t[0]:
            worst_t = (ta, z, tw)
        if ga > worst_g[0]:
            worst_g = (ga, z, gw)
    for (a, z, wpt), what, lim in ((worst_t, "no walls thinner than %.2f mm", mw),
                                   (worst_g, "no gaps narrower than %.2f mm", mg)):
        bad = a > 0.5
        rep.row("WARN" if bad else "PASS", what % lim,
                ("%.1f mm2 at z=%.1f near (%.1f, %.1f)" % (a, z, wpt[0], wpt[1]))
                if bad else "checked 12 horizontal slices")
    rep.note("slices only: walls running parallel to the plate are not covered")

    # --- planes the spec asks for, and holes
    planes = list(part.get("planes", []))
    for hspec in part.get("holes", []):
        if not any(p["axis"] == hspec["axis"] and abs(p["at"] - hspec["at"]) < 1e-6
                   for p in planes):
            planes.append({"axis": hspec["axis"], "at": hspec["at"],
                           "label": hspec.get("label", "hole")})
    if not planes:                       # always look at mid-height
        planes = [{"axis": "z", "at": (bb.ZMin + bb.ZMax) / 2, "label": "mid"}]
    for k, pl in enumerate(planes):
        infos = loops_info(sections(m, pl["axis"], pl["at"]), pl["axis"])
        holes = [i for i in infos if i["hole"]]
        rep.head("  section %s=%.2f (%s): %d loop(s), %d hole(s)"
                 % (pl["axis"], pl["at"], pl.get("label", ""), len(infos), len(holes)))
        for hh in sorted(holes, key=lambda i: i["d_area"]):
            kind = "round" if hh["round"] > 0.93 else "non-round %.2f" % hh["round"]
            rep.note("hole at (%.2f, %.2f): d %.2f, caliper %.2f..%.2f, %s"
                     % (hh["c"] + (hh["w_mean"], hh["w_min"], hh["w_max"], kind)))
        marks = [tuple(h["near"]) for h in part.get("holes", [])
                 if h["axis"] == pl["axis"] and abs(h["at"] - pl["at"]) < 1e-6 and "near" in h]
        img = os.path.join(out, "%s_sec_%s%.1f.png" % (name, pl["axis"], pl["at"]))
        draw_section(infos, img, mark=marks)
        rep.note("picture: %s" % img)

    for hspec in part.get("holes", []):
        infos = loops_info(sections(m, hspec["axis"], hspec["at"]), hspec["axis"])
        cand = [i for i in infos if i["hole"]]
        if "near" in hspec:
            cand.sort(key=lambda i: math.hypot(i["c"][0] - hspec["near"][0],
                                               i["c"][1] - hspec["near"][1]))
        else:
            cand.sort(key=lambda i: abs(i["w_max"] - hspec["d"]))
        lab = "%s d%.2f at %s=%.1f" % (hspec.get("label", "hole"), hspec["d"],
                                         hspec["axis"], hspec["at"])
        if not cand:
            rep.row("FAIL", lab, "NO hole found in that section")
            continue
        h0 = cand[0]
        tol = hspec.get("tol", 0.1)
        flats = hspec.get("flats")         # D / double-D bore: width across flats
        d_got = h0["w_max"] if flats else h0["w_mean"]
        dev = d_got - hspec["d"]
        off = (math.hypot(h0["c"][0] - hspec["near"][0], h0["c"][1] - hspec["near"][1])
               if "near" in hspec else 0.0)
        ok = abs(dev) <= tol and off <= max(0.5, tol * 3)
        extra = ""
        if flats:
            fdev = h0["w_min"] - flats
            ok = ok and abs(fdev) <= tol
            extra = ", flats %.2f (%+.2f)" % (h0["w_min"], fdev)
        elif h0["round"] < 0.93:
            ok = False
            extra = ", NOT ROUND (caliper %.2f..%.2f)" % (h0["w_min"], h0["w_max"])
        rep.row("PASS" if ok else "FAIL", lab,
                "measured d %.2f (%+.2f)%s, centre (%.2f, %.2f)%s  [%s]"
                % (d_got, dev, extra, h0["c"][0], h0["c"][1],
                   (", %.2f off" % off) if off > 0.05 else "",
                   hspec.get("source", "source not given")))
        if hspec["axis"] != "z":
            rep.note("horizontal hole: prints ~0.1-0.3 small and slightly tall-oval;"
                     " the roof droops unless it is teardrop/flat-topped")

    # --- renders
    views = {"iso": (1, 1.4, -0.8), "iso_back": (-1, -1.4, -0.8),
             "top": (0, 0, -1), "bottom": (0, 0, 1), "front": (0, 1, 0),
             "side": (-1, 0, 0)}
    paths = []
    for k, v in views.items():
        p = os.path.join(out, "%s_%s.png" % (name, k))
        render(P, F, n, p, v, red=down)
        paths.append(p)
    rep.note("renders (red = steep downward faces): %s" % ", ".join(
        os.path.basename(p) for p in paths))

    # --- coupon
    cp = part.get("coupon")
    if cp:
        cout = os.path.join(out, "%s_COUPON.stl" % name)
        try:
            v, cb = coupon(stl, cp["min"], cp["max"], cout)
            rep.row("INFO", "test coupon written",
                    "%s  %.1f x %.1f x %.1f mm, ~%.1f g vs ~%.0f g for the part"
                    % (os.path.basename(cout), cb.XLength, cb.YLength, cb.ZLength,
                       v / 1000 * 1.24, vol / 1000 * 1.24))
        except Exception as e:
            rep.row("WARN", "test coupon", "failed: %s - cut it in the build script" % e)


def main():
    args = [a for a in sys.argv if a.lower().endswith(".json")]
    if not args:
        raise SystemExit("usage: freecadcmd cadreview.py spec.json")
    spec = json.load(open(args[-1], encoding="utf-8"))
    out = spec.get("out") or os.path.join(os.path.dirname(os.path.abspath(args[-1])), "review")
    os.makedirs(out, exist_ok=True)
    rep = Report()
    rep.lines.append("CAD PRE-PRINT REVIEW  %s" % time.strftime("%Y-%m-%d %H:%M"))
    rep.lines.append("measured from the exported STL files, not from the model's parameters")
    for part in spec["parts"]:
        try:
            review_part(spec, part, rep, out)
        except Exception as e:
            import traceback
            rep.row("FAIL", "review crashed", repr(e))
            rep.lines.append(traceback.format_exc())
    rep.head("SUMMARY  %d FAIL, %d WARN" % (rep.fails, rep.warns))
    path = os.path.join(out, "review_report.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(rep.text())
    # freecadcmd's progress bar eats stdout: read review_report.txt
    sys.stdout.write("\nREPORT %s\n" % path)
    return 1 if rep.fails else 0


if not _RAN:
    code = main()
    if code:
        os._exit(code)
