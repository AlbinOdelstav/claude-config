# -*- coding: utf-8 -*-
"""Buildability checks for FreeCAD parts.

    import os, sys; sys.path.insert(0, os.path.expanduser("~/.claude/skills/cad-validation"))
    import cadcheck

Every function here exists because a real part shipped with the fault it
catches. None of them check that geometry is *correct* - FreeCAD and your own
dimension checks do that. They check that the correct geometry can actually be
**built, reached, fastened, mated and loaded**, which is a different question
and the one that keeps getting missed.

All functions take FreeCAD Part shapes and return (ok, detail) so they drop
straight into whatever reporting a build script already has.
"""

import math

import FreeCAD as App
from FreeCAD import Vector as V
import Part


# ---------------------------------------------------------------- one piece
def one_piece(shape):
    """Is the part a single connected solid?

    fuse() on shapes that merely TOUCH returns two solids, not one. isValid()
    is perfectly happy with that, and so is a volume check, so a part can ship
    with lumps floating unattached - visible in the viewer, and a multi-shell
    STL the slicer may silently drop or print in mid-air.

    Overlap shapes before fusing. Abutting is not joining.
    """
    n = len(shape.Solids)
    if n == 1:
        return True, "single solid"
    sizes = sorted((s.Volume / 1000.0 for s in shape.Solids), reverse=True)
    return False, "%d lumps: %s cm3" % (
        n, ", ".join("%.2f" % v for v in sizes))


# ---------------------------------------------------------------- overhangs
def xsec(shape, z):
    """Solid cross-section at height z, as faces with their holes."""
    try:
        wires = shape.slice(V(0, 0, 1), z)
    except Exception:
        return []
    if not wires:
        return []
    try:
        return Part.makeFace(wires, "Part::FaceMakerBullseye").Faces
    except Exception:
        return []


def overhang_reach(shape, z, box2d=None, step=0.5, below=0.6, window=15.0,
                   max_bridge=35.0):
    """Measure one layer: (cantilever_mm, bridge_mm, n_unsupported).

    Grids the layer, marks each point of new material supported or not by
    what is directly beneath, and for each unsupported point finds the
    nearest support in every 10 deg direction. If two of those lie >= 150 deg
    apart within max_bridge, the point is BRIDGED (span = the two added);
    otherwise it is CANTILEVERED by the nearest distance. Bridges and
    cantilevers get different limits - see needs_support.

    box2d = (x0, x1, y0, y1) of the overhanging faces: only points on them are
    judged, supports are searched `window` mm around them. Without it the
    whole part is gridded (slow on big parts).
    """
    up, dn = xsec(shape, z + 0.3), xsec(shape, z - below)
    if not up:
        return 0.0, 0.0, 0
    bb = shape.BoundBox
    fx0, fx1, fy0, fy1 = box2d or (bb.XMin, bb.XMax, bb.YMin, bb.YMax)
    x0, y0, x1, y1 = fx0 - window, fy0 - window, fx1 + window, fy1 + window
    ins = lambda fs, x, y, zz: any(f.isInside(V(x, y, zz), 1e-6, True) for f in fs)
    sup, uns = [], []
    x = x0
    while x <= x1:
        y = y0
        while y <= y1:
            if ins(up, x, y, z + 0.3):
                if ins(dn, x, y, z - below):
                    sup.append((x, y))
                elif fx0 - 1.0 <= x <= fx1 + 1.0 and fy0 - 1.0 <= y <= fy1 + 1.0:
                    uns.append((x, y))
            y += step
        x += step
    if not uns:
        return 0.0, 0.0, 0
    cant, span, NS = 0.0, 0.0, 36
    for ux, uy in uns:
        near = [None] * NS
        for sx, sy in sup:
            dx, dy = sx - ux, sy - uy
            d = math.hypot(dx, dy)
            k = int((math.atan2(dy, dx) + math.pi) / (2 * math.pi) * NS) % NS
            if near[k] is None or d < near[k]:
                near[k] = d
        have = [d for d in near if d is not None]
        if not have:
            cant = max(cant, window)
            continue
        best = None
        for i in range(NS):
            if near[i] is None:
                continue
            for j in range(i + 1, NS):
                if near[j] is None or min(j - i, NS - (j - i)) < 15:
                    continue
                t = near[i] + near[j]
                if best is None or t < best:
                    best = t
        if best is not None and best <= max_bridge:
            span = max(span, best)
        else:
            cant = max(cant, min(have))
    return cant, span, len(uns)


def needs_support(shape, deg=45.0, max_cant=3.0, max_bridge=35.0,
                  min_facet_mm2=1.0, **_old_kwargs):
    """(needs_support, detail) for a shape already in its PRINT pose.

    Measures EVERY layer that has a downward face, with separate limits for
    ledges held from one side (max_cant) and bridges held from two
    (max_bridge).

    Why it was rewritten (2026-10-08): the old version
    used one 8 mm limit for both kinds, measured only the layer with the most
    overhang area, and ignored totals under 1 cm2. A 6 mm boss held from one
    end and a 5 mm printed pin sticking out of a wall both passed as
    "self-supporting"; they were seen hovering in the slicer. Old keyword
    arguments (max_reach, min_area, probe_n) are accepted and ignored.
    """
    import MeshPart
    m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.1,
                               AngularDeflection=0.3, Relative=False)
    sgn = 0.0                       # facet normals can point inwards
    for f in m.Facets:
        c = [sum(p[i] for p in f.Points) / 3.0 for i in range(3)]
        n = f.Normal
        sgn += (c[0] * n.x + c[1] * n.y + c[2] * n.z) * f.Area / 3.0
    flip = -1.0 if sgn < 0 else 1.0
    lim = math.cos(math.radians(deg)) + 1e-3
    layers = {}
    for f in m.Facets:
        if f.Normal.z * flip >= -lim:
            continue
        zs = [p[2] for p in f.Points]
        if min(zs) < 1.5:                    # shallow recess in the bed face
            continue
        k = round(sum(zs) / 3.0 * 4.0) / 4.0
        xs, ys = [p[0] for p in f.Points], [p[1] for p in f.Points]
        a, b = layers.get(k, (0.0, [1e9, -1e9, 1e9, -1e9]))
        layers[k] = (a + f.Area, [min(b[0], min(xs)), max(b[1], max(xs)),
                                  min(b[2], min(ys)), max(b[3], max(ys))])
    res = []
    for z, (area, b) in sorted(layers.items()):
        if area < min_facet_mm2:
            continue
        c, sp, n = overhang_reach(shape, z + 0.05, b, max_bridge=max_bridge)
        if n:
            res.append((z, c, sp))
    if not res:
        return False, "no overhangs"
    bad = [t for t in res if t[1] > max_cant or t[2] > max_bridge]
    if bad:
        return True, "NEEDS SUPPORT - " + "; ".join(
            "z=%.1f ledge %.1f / bridge %.1f" % t for t in bad[:4])
    wc = max(res, key=lambda t: t[1])
    wb = max(res, key=lambda t: t[2])
    return False, "self-supporting - ledge %.1f mm at z=%.1f, bridge %.1f mm at z=%.1f" % (
        wc[1], wc[0], wb[2], wb[0])


# ------------------------------------------------------------- interference
def all_pairs(parts, engaged=(), tol=1.0):
    """Every pair of ASSEMBLED parts, not just the ones you thought of.

    parts: {name: shape} already moved into assembly position.
    engaged: pairs that are meant to overlap (keyed joints, press fits).

    The trap this catches twice over: checking only the pairs you suspect,
    and checking parts in their MODELLING frames. A part modelled Z-up in its
    own frame overlaps everything at the origin, which looks alarming and
    means nothing - and hides the pairs that genuinely clash.
    """
    import itertools
    eng = set(tuple(sorted(p)) for p in engaged)
    bad, worst = [], ("", 0.0)
    for a, b in itertools.combinations(sorted(parts), 2):
        if tuple(sorted((a, b))) in eng:
            continue
        v = parts[a].common(parts[b]).Volume
        if v > worst[1]:
            worst = ("%s / %s" % (a, b), v)
        if v > tol:
            bad.append((a, b, v))
    if bad:
        return False, "; ".join("%s/%s %.1f mm3" % t for t in bad)
    return True, "all clear, worst %s %.2f mm3" % worst


# ---------------------------------------------------------------- fasteners
def axis_reaches_air(solid, origin, direction, rad, limit=170.0):
    """Can a screw actually be INSERTED along this axis?

    Holes being 'in the metal' is not enough. Two blind holes facing each
    other across a mating face line up perfectly, take a screw from either
    side, and can never fasten the two parts together - the head ends up
    buried. A fastener is only real if its axis reaches open air at one end.

    Test against the sub-assembly present at THAT step of the build, not the
    finished article, or later parts will mask access that exists in practice.
    """
    area = math.pi * rad * rad
    u = V(*direction)
    u.normalize()
    o = V(*origin)
    for sgn in (1.0, -1.0):
        d, blocked = 0.0, False
        while d < limit:
            cyl = Part.makeCylinder(rad, 1.0, o + u * (sgn * d), u * sgn)
            if solid.common(cyl).Volume > area * 0.85:
                blocked = True
                break
            d += 1.0
        if not blocked:
            return True, "reaches open air"
    return False, "BLOCKED AT BOTH ENDS - no screw can be fitted"


def boss_span(shape, origin, direction, clear_d, hi=80.0, step=0.5):
    """Real grip length: how much material a screw passes THROUGH.

    Probe wider than the hole, or the probe slips down the clearance hole and
    reports nothing. Probe with a POINT test if you need 0.1 mm accuracy - a
    box probe reads about half its own width early at each face.
    """
    rad = clear_d / 2.0 + 2.0
    u = V(*direction)
    u.normalize()
    o = V(*origin)
    lim = math.pi * rad * rad * step * 0.02
    first = last = None
    d = 0.0
    while d < hi:
        if shape.common(Part.makeCylinder(rad, step, o + u * d, u)).Volume > lim:
            if first is None:
                first = d
            last = d + step
        d += step
    return 0.0 if first is None else last - first


def screw_length(declared, grip, pilot, through=False):
    """Is this screw long enough to reach, and short enough not to bottom?

    Both halves matter. A screw shorter than the grip cannot reach the part
    it is supposed to fasten to; one longer than grip+pilot bottoms out in a
    blind hole and can never pull the joint tight. Specify from the geometry,
    never from habit.
    """
    if declared <= grip + 1.0:
        return False, "too short: %.0f mm against %.0f mm of grip" % (
            declared, grip)
    if through:
        return True, "grip %.0f + %.0f mm through -> stands %.0f mm proud" % (
            grip, pilot, max(0.0, declared - grip - pilot))
    if declared > grip + pilot:
        return False, "bottoms out: needs %.0f..%.0f mm" % (
            grip + 1.0, grip + pilot)
    return True, "grip %.0f + pilot %.0f -> %.0f..%.0f mm" % (
        grip, pilot, grip + 1.0, grip + pilot)


# ------------------------------------------------------------------- motion
def contiguous_travel(moving, fixed, place, lo, hi, step=2.0, tol=1.0):
    """Longest UNBROKEN run of travel, not just clear endpoints.

    place(t) -> a copy of `moving` positioned at t. Checking only the ends
    reports a clean full stroke even when the middle fouls; checking 'any
    clear position' does the same. Only a contiguous run is a real stroke.
    """
    rows, t = [], lo
    while t <= hi:
        rows.append((t, fixed.common(place(t)).Volume))
        t += step
    best, cur = (0.0, lo, lo), None
    for tt, v in rows:
        if v < tol:
            if cur is None:
                cur = tt
            if tt - cur > best[0]:
                best = (tt - cur, cur, tt)
        else:
            cur = None
    return best


def retained_against(wrapped_w, opening_w, margin=3.0):
    """Will a strap, band or cable stay on what it is wrapped around?

    Whatever takes the load has to be WIDER than the opening behind it, or
    the load simply drags it off. A tongue joined at the front and open at the
    back is not an anchor, however solid it looks.
    """
    if wrapped_w > opening_w + margin:
        return True, "wraps %.1f mm against a %.1f mm gap" % (
            wrapped_w, opening_w)
    return False, "wraps %.1f mm with a %.1f mm gap behind it - IT SLIDES OFF" \
        % (wrapped_w, opening_w)


def crosses_load(hole_dir, load_dir, tol=0.35):
    """A hole only anchors if its axis CROSSES the load.

    A hole bored along the pull just lets the band, cable or pin slide out.
    """
    a, b = V(*hole_dir), V(*load_dir)
    a.normalize()
    b.normalize()
    dot = abs(a.dot(b))
    if dot < tol:
        return True, "axis crosses the load (cos %.2f)" % dot
    return False, "axis lies ALONG the load (cos %.2f) - it will pull out" % dot


# -------------------------------------------------------------------- mesh
def mesh_ok(shape, lin=0.05, ang=0.3):
    """Watertight, manifold, single shell - what a slicer will accept."""
    import MeshPart
    m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=lin,
                               AngularDeflection=ang, Relative=False)
    bad = []
    try:
        if not m.isSolid():
            bad.append("not solid")
        if m.hasNonManifolds():
            bad.append("non-manifold")
        if m.hasSelfIntersections():
            bad.append("self-intersecting")
    except Exception as e:
        bad.append("could not test (%s)" % e)
    if len(shape.Shells) != 1:
        bad.append("%d shells" % len(shape.Shells))
    return (not bad), (", ".join(bad) if bad else
                       "%d triangles, watertight" % m.CountFacets)
