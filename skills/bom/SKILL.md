---
name: bom
description: Build a complete bill of materials for a CAD/maker project - every screw, nut, pin, magnet, motor, electronic part, consumable and printed part, with quantities, where each number came from, and what is not designed yet. Use when the user runs /bom, asks "what parts do I need?", "what do I need to buy?", "shopping list", "parts list", "vad behöver jag köpa?", "komponentlista", or before a full build of a project with many printed and bought parts.
model: sonnet
---

# /bom: everything needed to build it

The user builds 3D-printed projects (e.g. FreeCAD models printed on a Bambu
printer) that also need bought hardware and sometimes electronics. They want
one list of everything, to check against what they have and to buy the
rest, **before** they find the missing M3 × 20 halfway through assembly.

**Your stance: derive, don't remember.** Every quantity and length comes from
the current version's geometry, build report or a decision the user has made.
A screw length "by habit" has shipped wrong before (cad-validation:
"Wrong screw length").

## Output

1. A short summary in chat, in the user's language: number of items, what to
   buy, and **what is blocking** (fasteners that fit nothing, parts not
   designed yet).
2. `BOM.md` in the version folder (`vN/BOM.md`), with checkboxes so the user
   can tick off what they have. A BOM is documentation, not geometry, so
   writing it into the current version folder is fine. Regenerate it, don't
   hand-edit, when the version changes.

Every row gets a **status**:

| Status | Meaning |
|---|---|
| CHECKED | in the geometry and verified by a build-report check (length, reach) |
| DERIVED | worked out now from the geometry (holes probed, grip measured) |
| DECIDED | the user decided it (memory, chat), with no geometry behind it |
| ASSUMED | your guess. Say what it rests on, and ask |
| NOT DESIGNED | the function is needed, but nothing exists yet. List the **need** (counts, voltage, current) and candidate options, never a fake part number |

## Step 1: Gather the sources

For the version folder (the current one per the project's memory or README):

- `params.py`: screw lengths, pilot/clearance, bought-part dimensions
- `*/build_report.txt`: print list (qty, grams), fastener checks, and the
  "NOT CHECKED" / "ASSUMED" notes
- `README.md`: assembly order (every step that says "screw", "pin", "glue")
- model code: grep for `screw_clear`, `screw_pilot`, `magnet`, `pivot`, `pin`,
  `nut`, `insert`, `pocket`, `glue`. **Every hole is a fastener**, and every
  fastener needs a row
- side projects the build depends on (bench tests, sub-assemblies)
- the project memory: bought parts, measured values, decisions

## Step 2: Fasteners, worked out from the holes

For every hole pattern:

1. **Type** from the hole: clearance in one part + pilot in the other means
   a self-tapper. Clearance in both means a bolt + nut. A blind clearance with
   nothing beyond needs a question.
2. **Grip**: probe the material along the axis in the assembled pose
   (`cadcheck.boss_span`, or the probe below). Self-tapper: grip + 6 to 10 mm
   into the pilot, without bottoming. Bolt: grip + nut (2.4) + 1 to 2 mm.
   Round to lengths you can buy (6, 8, 10, 12, 16, 20, 25, 30).
3. **Does it join anything?** The probe must pass material in **both**
   parts, and `cadcheck.axis_reaches_air` must find a way in for the
   screwdriver at that assembly step. A hole in air, in a hollow, or
   blind at both ends **is not a BOM row; it is a FINDING**. List it in a
   "Fasteners that don't work" section and say so in the summary.
4. **Count** = holes per part × part quantity. Group identical screws into
   one row, with a per-location breakdown underneath.

Probe for material segments along a line (run with freecadcmd):

```python
def segs(shape, o, u, L=400.0, r=0.2):
    o, u = V(*o), V(*u); u.normalize(); start = o - u * (L / 2)
    c = shape.common(Part.makeCylinder(r, L, start, u))
    return sorted((min((v.Point - start).dot(u) for v in s.Vertexes) - L / 2,
                   max((v.Point - start).dot(u) for v in s.Vertexes) - L / 2)
                  for s in c.Solids)
```

Run it on the parts **before** the holes are cut, or keep the probe inside
the hole radius and read gaps as the hole. Measure split pieces on the full
part, at the split's own recursion level.

## Step 3: The other categories

- **Printed parts:** a summary per part (qty, g), total filament + ~10 %
  for tests and failures. Point to the print list; don't duplicate it.
- **Mechanical, non-printed:** pins, magnets (size from the pocket, pocket
  = part + 0.1 to 0.2), panels, wire, springs, bearings, feet.
- **Motion:** motors and servos. Quantity, and the exact variant (e.g. a
  single- or dual-shaft TT gear motor). Link to the measured values.
- **Electronics:** derive the **needs** from the design: number of actuators
  and their direction (one-way or reversing?), number of inputs (buttons,
  sensors), voltage, rough current (stall!), one-at-a-time or
  simultaneous. If the circuit is not designed, write NOT DESIGNED and give 1
  or 2 candidate setups with the trade-off. Don't present them as decided.
- **Consumables:** glue/epoxy, heat-set inserts, wire, heat-shrink, solder.
- **Tools** worth checking the user has, only where unusual (a long
  screwdriver for a deep pocket, a soldering iron).

## Step 4: Check before writing

- Does every assembly step in the README have its parts in the list?
- Does every ASSUMED or NOT DESIGNED row appear in the summary as a question
  or a decision?
- Counts × quantities: recompute the totals once.
- Suggest a standard kit when it's cheaper than single items (e.g. an
  M3 assortment with nuts), but keep the exact counts.

## Step 5: Check against what the user has

Only if the `inventory` skill is installed (from
[maker-inventory](https://github.com/AlbinOdelstav/maker-inventory)): follow it
to write the rows as needs to a project file (it says where the tool and data
live), run its `check`, and mark each BOM row HAVE / BUY in `BOM.md`. The
shopping list in the summary is then only what `check` says is missing.
Without the skill, skip this step and say the stock was not checked.

## Never

- Invent a part number or a length that nothing in the project supports.
- List a fastener that can't be fitted as if it were fine.
- Hide that electronics or anything else is not designed.
