---
name: print-settings
description: Produce a ready-to-use Bambu Studio settings sheet for a set of STLs — plate split, global settings, per-object overrides and hardware list. Use when the user asks for print settings, slicer settings, "how do I print this", or is about to send parts to a Bambu printer.
model: sonnet
---

# /print-settings — Bambu Studio sheet

The values below are for a **Bambu Lab P1S, 0.4 mm nozzle, PLA**; if the
user's CLAUDE.md or project names another printer, nozzle or material, adjust
them and say so. Produce the sheet from
the *current build output*, never from memory — which parts need support and
how big they are changes every rebuild.

## Gather first

1. **Find the STLs** (usually `<version>/test/stl/` or `<version>/machine/stl/`).
2. **Read the build report** (`test/build_report.txt`) for the OVERHANGS
   section — that says which parts need support and why. If there is no
   report, run the build script. Do not guess.
3. **Sizes and weights** come from the report's PRINTABILITY and SOLID SANITY
   sections.
4. **Screw sizes** come from the report's fastener-length checks, not habit.

## Split into plates by support requirement

Support is per-plate in practice — per-object overrides are fiddly and easy to
get wrong. So:

- **Plate 1:** the parts needing support
- **Plate 2:** everything else

If nothing needs support, one plate.

## The settings

State **Expert mode** up front — Ironing and Support→Advanced are hidden
otherwise, which is an easy way to miss a setting.

**Plate with supports**

| Tab → group | Setting | Value |
|---|---|---|
| Quality | Layer height | 0.20 mm |
| Strength | Wall loops | 4 |
| Strength | Sparse infill density | 25 % |
| Strength | Sparse infill pattern | Gyroid |
| Support | Enable support | ON |
| Support | Type | Normal (auto) |
| Support | Style | Snug |
| Support | Threshold angle | 45° |
| Support | On build plate only | **OFF** if the overhang is internal |
| Support → Advanced | Top Z distance | 0.2 mm |

**Plate without**

Same, but supports OFF and 3 walls. Add these when the plate holds small
parts (under ~40 mm), because heat soak costs more than stringing does:

| Tab → group | Setting | Value |
|---|---|---|
| Filament | Nozzle temp | 205 °C |
| Filament | Fan | 100 % |
| Filament → Cooling | Min layer time | 8 s |
| Others | Avoid crossing wall | ON |

**Per-object overrides** only where the geometry demands it — e.g. a rotating
part gets 4 walls and seam *Rear* to keep the seam off a sealing face.

## Always include

- **"All STLs are pre-rotated — do not rotate them."** The build poses them.
- **"If the slicer offers to repair a mesh, decline."** The build checks
  watertightness; a repair prompt means something is wrong.
- **Hardware list** with the screw lengths from the report.
- **Post-print fit checks** for any running fit, and which part to reprint
  with what X-Y compensation if it is tight or loose.

## Say what is not covered

End with what the settings cannot guarantee — an untested mechanism, an
assumed dimension. "All checks pass" reads as "safe to print", and filament has
been lost to that before.
