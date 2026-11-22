---
name: cad-review
description: Hard pre-print review of CAD parts (FreeCAD / FreeCAD MCP / build scripts) before the user spends filament. Use when they run /cad-review, ask "is it ready to print?", "kan jag skriva ut?", "review this", or before YOU say a part is ready, before /print-settings, and after every fix to a part that is about to be printed. Re-measures the exported STLs independently, audits where every critical dimension came from, checks fits against real bought parts, looks at renders, and proposes a cheap test coupon. Ends with a verdict of READY, COUPON FIRST or NOT READY.
model: opus
---

# /cad-review: review before the filament is spent

The user designs parts with Claude in FreeCAD and prints them, by default on a
**Bambu Lab P1S (0.4 nozzle, PLA, 256³ bed)**; if their CLAUDE.md or the
project names another printer, use that. Too often a part only turns out
wrong at the printer: wrong dimensions, a bought part that doesn't fit, a feature hovering
in mid-air. This skill exists to catch those faults before slicing.

**Your stance: you are the reviewer, not the designer.** Assume the part is
wrong and look for the fault. The build script's own checks were written by
the same mind that designed the part, and share its blind spots. Every fault
that reached the printer had passed them.

Load **cad-validation** too: it holds the buildability library
(`cadcheck.py`) and the failure taxonomy. This skill adds the independent,
pre-print layer on top of it.

## Output: verdict first

The user often asks while a print is queued. Line one is the verdict, in the
language they wrote in:

- **READY TO PRINT.** Every critical requirement is measured on the STL, and
  every fit rests on measured dimensions.
- **COUPON FIRST.** Geometry is sound, but a fit rests on an assumption. Print
  the coupon (grams and minutes) before the part.
- **NOT READY.** List the FAILs, each with one line on the fix.

Then: what was checked, **what was NOT checked**, and the questions for the
user. Keep **real blockers** apart from nice-to-know items. Never present a
non-dependency as a blocker. (A splice bore was once listed as blocking a part
it had nothing to do with, and the user had to point it out.)

## Step 1: Pin down exactly what gets printed

- The exact STL paths the user will load into the slicer, from the current
  version folder. Not the FCStd, not params.
- Is each STL newer than every source it was built from (`params.py`, the
  model scripts)? If not, rebuild before anything else. The script checks
  this through `source`.
- Is this a new version folder? (If the project versions its folders, any
  change goes in `vN+1/`.)

## Step 2: Requirements and provenance table (the most important step)

Before measuring, write down **what the part must do** and **every dimension
it hinges on**. Give each dimension a source:

| Tag | Meaning | Trust |
|---|---|---|
| MEASURED | calipers on the real part, or a printed test that worked | high |
| DRAWING | read off a dimensioned drawing | medium, verify the critical ones |
| SCALED | measured off a picture or an undimensioned drawing | low |
| ASSUMED | guess, "typical", habit | none |

Read the project's memory and params comments for MEASURED values (e.g. a TT
motor shaft bore 5.7/3.9, 2 mm wire in a 2.4 bore).

**Any fit that rests on SCALED or ASSUMED cannot be READY.** Either ask the
user to measure (gather every question into ONE message, name exactly where to put
the calipers, and offer a picture), or go COUPON FIRST.

### Bought parts: audit the reference model, not just the fit

The worst faults came from a **wrong model of the bought part**. When the
model is incomplete, every clash check passes. Before trusting any check
involving a motor, servo, screw, bearing or board, list everything that
sticks out of it and confirm each one is in the model:

- shafts on **both** ends (a dual-shaft TT motor once got a drawing with one)
- pegs, bosses, clip ears, tabs, tails, flanges
- wires, solder tabs, connectors, and room to bend the cable
- screw heads, nuts, and the screwdriver's path
- the part's **largest** cross-section along its whole insertion path, not
  only where it finally sits. A hole once got ledges because the motor was
  assumed narrower than its gearbox. It isn't.

Compare against a photo of the user's own part when one exists. If a drawing
and a photo disagree, the photo wins. Ask rather than guess.

## Step 3: Measure the STLs independently

Write a spec (a template sits in the docstring of `cadreview.py`) and run:

```bash
"C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" "$HOME/.claude/skills/cad-review/cadreview.py" path/to/spec.json
```

Use the user's own FreeCAD path if it differs (`freecadcmd` on Linux/macOS).
Pass only the .json; freecadcmd tries to open .stl arguments itself. Put the
spec and output in the scratchpad, or in `vN/review/` if the user wants to
keep it.
Read `review_report.txt`. The console is eaten by the progress bar. Exit code
1 means at least one FAIL.

Take the numbers in the spec from **step 2's requirements**, never from
`params.py`. Copying params into the spec tests the model against itself,
which proves nothing.

What it measures on each STL:

| Check | Catches |
|---|---|
| STL vs source mtime | printing a stale export |
| shells, watertight, manifold, normals | floating lumps, broken fuse, inside-out mesh |
| units, bbox vs requirement | mm/inch/cm export, **wrong orientation** (right sizes, wrong axes) |
| bed fit, ZMin = 0 | part off the plate or bigger than 256³ |
| first-layer area, height/footprint | parts that peel or topple |
| faces steeper than 45° (red in renders) | where to look for overhangs (judge them with `cadcheck.needs_support`) |
| walls < 0.8, gaps < 0.4 on 12 slices | walls the slicer drops, clearances that fuse shut |
| holes at given planes: d, flats, centre, roundness | bore wrong size, D-flat missing, hole moved |
| 6 shaded renders + section PNGs | what the user would see in the slicer |
| `coupon` | a small test slice of the critical area |

Its limits, to state in the verdict: it measures single parts in their print
pose, NOT assembly clashes (that's `cadcheck.all_pairs` in the build script);
thin-wall slicing is horizontal only; and the overhang list is a hint, not a
support verdict.

## Step 4: Look at every image

Read the PNGs, every one. Most faults that got through were visible in a
picture. Per part:

- **bottom** and **iso_back**: anything red that is not on the plate? Pins,
  bosses, roofs, tabs hanging in air? (Twice "support off" was given while
  features hovered, including a roof added as a fix.)
- **top / front / side**: does it match the intent from step 2? Is a feature
  missing or mirrored (RH/LH)? Is it on the wrong side?
- **sections**: is the bore where the mating part's shaft will be? Is the wall
  around it at least 1.2 mm?
- Would a screw, wire or finger actually reach where it must go?

If a picture surprises you, suspect your probe or spec before blaming the part,
then verify.

## Step 5: Fits against real parts

For every interface, put three numbers side by side: the real part (with
source tag), the printed feature (measured in step 3), and the clearance. Use
the project's own measured values first. Otherwise use these P1S/PLA starting
points, and call them starting points:

| Fit | Clearance (on diameter or width) |
|---|---|
| shaft press fit, vertical hole | +0.1 to +0.2 (TT D-shaft: 5.7/3.9 MEASURED firm) |
| rotating or sliding, vertical hole | +0.3 to +0.4 |
| horizontal hole | +0.2 extra; it prints oval, so use a teardrop or flat roof |
| M3 clearance / M3 self-tap into PLA | 3.3 to 3.4 / pilot 2.5 to 2.8 |
| slide-in tab in a slot | 0.2 to 0.3 per side |
| print-in-place gap | ≥ 0.4, 0.5 is safer |
| 2 mm steel wire in a printed bore | 2.4 MEASURED |
| first layer | elephant foot ~0.2: chamfer the bottom edge of holes and of mating faces on the plate |

Check the fit along the **whole insertion path and every assembly step**:
can each part go in, in the order the user will assemble it, with the parts that
are already present at that step?

## Step 6: Cross-check the build script's coverage

Read `build_report.txt`. For each requirement in step 2, is there a check
that **can fail**? Look for:

- pairs of parts that were never tested against each other
- checks that compare against the same param they were built from
- bought-part models missing features (step 2)
- a check that has never been seen failing. Break it once (cad-validation:
  "Verifying a check").

## Step 7: Coupon, the cheapest insurance

When anything rests on an assumption, or the part is big (> ~30 g or > 2 h),
propose a coupon: the critical interface only. Typical coupons:

- the bore with a 2 to 3 mm wall, 4 to 6 mm tall (the fit only)
- a **tolerance ladder**: the same feature at 3 to 5 sizes in one print (e.g.
  2.2/2.4/2.6 bores for a 2 mm wire)
- the corner or pocket where a bought part seats, cut out with a thin floor

Prefer cutting it in the build script from the exact shape (`shape.common(box)`)
and exporting it to `vN/test/stl/coupon_*.stl`. The `coupon` key in the spec
cuts it from the STL when that's all there is. Give grams and minutes for
the coupon vs the full part.

## Step 8: After every fix, review the whole thing again

Fixes create new faults. Adding the rear shaft exposed a boss clash, and a
roof added to stop hovering hovered itself. After any change, re-run steps 3
to 6 on **all** affected parts, not only the line that failed. Then give a
fresh verdict.

## Never

- Say "ready" or "support off" without the renders read and the per-layer
  support check run.
- Put a value from params into the spec as the "expected" value.
- Pass a fit as READY when the bought part's dimension is SCALED or ASSUMED.
- Hide what wasn't checked.
