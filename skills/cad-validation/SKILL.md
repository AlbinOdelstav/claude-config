---
name: cad-validation
description: Buildability checks for parametric CAD, especially FreeCAD parts destined for 3D printing. Use whenever generating, modifying or reviewing CAD geometry, writing a build/validation script, or before telling the user a part is ready to print. Catches faults where the geometry measures correctly but cannot be built, reached, fastened, mated or loaded.
---

# CAD validation — check buildability, not just geometry

For parametric CAD in FreeCAD, driven by scripts and printed on an FDM printer
(e.g. a Bambu Lab P1S). Load this whenever CAD geometry is being produced or
blessed.

## The rule

**Dimensions being right is not the same as the part being buildable.**

Every serious fault on this project passed the dimension checks. Each one was
found by the user looking at a render, after filament had been spent. The
checks below exist because of specific shipped faults, not theory.

For every feature, ask four questions the CAD kernel will never ask for you:

1. **Is it attached?** `fuse()` on shapes that merely touch returns two solids.
2. **Can a tool reach it?** A hole can be perfectly placed and still unusable.
3. **Does the mating real-world part fit it?** Not a generic one — the actual
   servo, horn, bearing, screw the user owns.
4. **What force does it carry, and does it bear on anything?** A feature the
   load pulls *off* its support is not a fixing.

## Use the library

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.claude/skills/cad-validation"))
import cadcheck
```

`cadcheck.py` sits beside this file. Read it — every function's docstring
records the fault it was written for. Wire the relevant ones into the
project's build script as permanent checks, so they run on every rebuild
rather than once.

| Function | Catches |
|---|---|
| `one_piece` | lumps that abut instead of fusing, and float |
| `needs_support` / `overhang_reach` | droop; every overhanging layer, **ledges (3 mm) and bridges (35 mm) judged separately** |
| `all_pairs` | clashes in pairs nobody thought to test |
| `axis_reaches_air` | fasteners with no insertion path |
| `boss_span` + `screw_length` | screws too short to reach or long enough to bottom |
| `contiguous_travel` | strokes that foul in the middle |
| `retained_against` | anchors the load drags off |
| `crosses_load` | holes bored along the pull instead of across it |
| `mesh_ok` | non-manifold / multi-shell STLs |

## The failure taxonomy

Each of these shipped. Check for all of them.

- **Not attached.** Two lap tabs and a journal post floated free in a part
  that passed `isValid()` and a volume check. Overlap before fusing.
- **Unreachable fastener.** Two blind holes faced each other across a mating
  face — lined up perfectly, took a screw from either side, could never join
  the parts. Test insertion against the sub-assembly present *at that build
  step*.
- **Wrong screw length.** Specified 12 mm for 41 mm of grip, then 45 mm when
  the user's longest was 20 mm. Derive length from measured grip and pilot;
  check both ends of the window.
- **Interface that fits nothing real.** A coupler with eight holes on two bolt
  circles "so any horn fits" fitted no actual horn without drilling. Get the
  real part's dimensions from the user and cut to those.
- **Anchor the load pulls off.** A band anchor was a tongue joined at the
  front and open at the back; the pull dragged the band straight off. Whatever
  takes load must be wider than the opening behind it.
- **Hole bored along the load.** The sled's band hole ran parallel to the
  pull, so the band slid out. Anchoring holes must cross the load.
- **Partial check coverage.** The interference check tested 4 pairs out of 21
  and would not have caught a clash in the other 17. Enumerate exhaustively.
- **Hovering features passed as self-supporting.** A 6 mm boss held from
  one end and a 5 mm pin sticking out of a wall passed the support check,
  which used one limit for ledges and bridges, measured only the biggest
  overhang layer and ignored small areas. The user saw them float in the
  slicer. Never say "support off" without the per-layer check, and look at the
  part's undersides in a render.
- **Measuring the wrong thing.** A bounding box called a 17 mm cantilever a
  "36 mm bridge". Measure the quantity that governs the failure.

## Verifying a check

A check that has never failed proves nothing. **Run new checks against the
known-bad geometry** — an old version folder, or a deliberately broken copy —
and confirm they fail. Several checks here were themselves wrong first time:
probe boxes read half their own width early, probe axes got swapped, a stroke
scan took first-clear and last-clear without testing continuity. If a probe
result looks surprising, suspect the probe before the part.

## Working habits that would have saved most of this

- **Render and look at it.** The user caught every fault this way. Rasterise
  SVG with `msedge --headless --screenshot` and actually read the image.
- **Re-read the report, don't assume.** FreeCAD's progress bar overwrites
  stdout; write the report to a file and read that.
- **State what a check does *not* cover.** "All checks pass" invites a print.
- **Version folders before changing printed geometry.** Once a version has
  been printed, put changes in a new version folder so the printed one stays
  reproducible. Follow the project's own rule if it has one.
