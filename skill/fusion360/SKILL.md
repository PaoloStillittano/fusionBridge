---
name: fusion360
description: Create, modify, inspect and export CAD parts in Autodesk Fusion through FusionBridge, and prepare Bambu A1 print jobs with real Studio presets and slicing. Use for Fusion modeling and model-to-print workflows, including Bambu Studio cloud submission when a specific print is requested.
---

# FusionBridge: Fusion modeling and Bambu printing

`f360` talks to the FusionBridge add-in running inside Fusion on this machine. You write
Python against the Fusion API, run it inside Fusion, then **look at the result** before going on.
`b360` prepares reproducible sliced Bambu Studio projects. For preparing, slicing, sending or
monitoring a print, read [reference/bambu.md](reference/bambu.md). Cloud transport uses the
authenticated Studio GUI, not copied account credentials. The agent is Codex/Claude; this
project exposes a CLI and a skill, not an MCP server or a separate autonomous agent.

If the commands are missing from PATH, resolve the directory containing this skill (it may
be a symlink) and invoke `python3 <project>/cli/f360` or `python3 <project>/cli/b360`.

## Printer profile

Bambu Lab A1, build volume **256 x 256 x 256 mm** (`f360 fdm --bed 256x256x256`).
Design defaults: **0.4 nozzle, PLA, textured PEI plate**. Supported alternatives include
**0.2 nozzle, PETG, smooth PEI plate** when actually available to the user. These defaults
do not identify the hardware currently mounted. If you deviate, say why
and let the user confirm (it means changing hardware/filament on the printer).
When and what changes in the design: [reference/fdm.md](reference/fdm.md#printer-options).
Design a part for one setup, and state it in the final summary: nozzle, material, plate, orientation.

## Loop

0. **Intake**: read [reference/intake.md](reference/intake.md) - what a request must contain,
   when to write a brief first (complex parts only), how to use the user's images,
   how many screenshots to take.
1. `f360 ping` - must return `ok`. Exit code 2 can mean either a sandbox/network restriction
   or an inactive add-in: check the actual error before asking for a restart. If the add-in
   is genuinely inactive, ask the user to start FusionBridge in Fusion's Add-Ins panel.
   Keep the returned `document_id` and pass `--document-id ID` before subsequent commands
   when operating on an existing design; a change of active document must not redirect edits.
2. Use the user's requested project directory, or `~/Desktop/3d/<part-name>/` by default
   (`brief.md`, `steps/`, `shots/`, `export/`). Keep private designs and generated evidence
   out of the public tool repository; use ignored `outputs/` when working inside it.
   `f360 new` for a new part (parametric, mm), or `f360 tree` to understand the open one.
3. Write one script per logical stage (base, holes, fillets...) in `steps/NN_<stage>.py`
   and run `f360 exec steps/NN_<stage>.py`. Not one huge script: the steps, rerun in
   order on a new document, must rebuild the part.
4. After every step that changes geometry, check it:
   - `f360 shot -o shots/NN_<stage>.png -v iso` then **open the PNG** and look
     (3 views at the end of a stage, see intake.md).
   - `f360 tree` for exact numbers (bbox, volume, timeline health).
5. Before calling it finished: `f360 shot -v iso_bottom`, `f360 fdm --bed 256x256x256`,
   then `f360 export export/<part-name>.3mf` (or `.stl`, `.step`), `f360 save <part-name>`,
   and the final summary (dimensions, parameters, orientation, supports, files).

On a script exception, newly appended timeline entries are removed only when the original
document is still active and the timeline was at its end. Existing parameter edits, files,
direct modeling and document changes are not a transaction. Inspect before retrying. A
timeout after a job started does not stop it: inspect the model before running it again.
`f360 rollback N` deletes timeline entries from N onward; it is not a history-view command.

## Commands

| Command | Use |
|---|---|
| `f360 ping` | connection, document, units |
| `f360 new [--units mm]` | new parametric design |
| `f360 exec FILE` / `-c CODE` / `-` (stdin) | run Python in Fusion. `--keep-on-error` disables rollback |
| `f360 shot -o P.png -v iso,front,top,right,iso_bottom [--style edges\|shaded\|wire] [--size 1280x960]` | screenshots; one view = exact path, several = `P_<view>.png` |
| `f360 tree` | bodies (bbox mm, volume), sketches, user params, timeline with health |
| `f360 params [--set NAME EXPR]...` | list/set user parameters, the model recomputes |
| `f360 fdm [--bed 256x256x256] [--mode plate\|part] [--strict] [--bodies A,B]` | BRep + mesh checks, bed contact, combined bounds; `--strict` fails on review warnings |
| `f360 export P.stl\|.3mf\|.step\|.f3d [--bodies A,B] [--each]` | export |
| `f360 rollback N` | delete timeline items from index N on |
| `f360 save NAME` | save to the active cloud project |
| `f360 api ExtrudeFeatures.createInput` / `f360 api --search Fillet` | docs from the live API |
| `f360 reload` | reload add-in code after editing it |

Every command prints JSON. `exec` prints your script's stdout first, then `--- summary ---`
with `result`, `timeline`, `feature_problems`, `error`.
`ok` reports command execution, not overall design validity. Read `feature_problems` and
FDM `validation`/warnings. Parameter `value` uses the declared unit; `internal_value`
retains Fusion's cm/radians value. `tree` includes `kind: brep|mesh`.

## The exec environment

Already in scope: `adsk`, `app`, `ui`, `design`, `root` (root component), `math`,
and **`h`** (helpers). Set `result = ...` to return data. `print()` works.

```python
h.param('thick', 4)                                         # user parameter (mm)
sk = h.sketch('xy', name='base')
h.rect(sk, 60, 40)                                          # centered
h.circle(sk, 3.4, center=(-22, -12)); h.circle(sk, 3.4, center=(22, 12))
plate = h.extrude(h.profile(sk, 'largest'), 'thick', name='plate').bodies.item(0)
h.fillet(h.edges_along(plate, 'z'), 5)                      # round the vertical corners
h.chamfer(h.bottom_edges(plate), 0.6)                       # chamfer bottom: no elephant foot
result = h.bbox(plate)
```

Helper reference: [reference/helpers.md](reference/helpers.md).
Raw-API patterns and gotchas: [reference/fusion-api.md](reference/fusion-api.md).

## Rules that prevent most failures

- **Units**: helpers take mm. The raw API takes **cm** (`ValueInput.createByReal(0.5)` = 5 mm)
  and radians. Use `h.length(mm)` / `h.pt(x,y,z)` or strings like `'5 mm'`.
- **+Z is up / print direction**, shared bed is Z=0. `fdm --mode part` explicitly evaluates
  each part after dropping it to its own minimum; it does not validate a shared layout.
- **Parametric first**: put key dimensions in `h.param(...)` and use the names in expressions
  (`'w/2 - 4 mm'`). Sketch primitives such as `h.rect` and `h.circle` take numeric sizes:
  connect sketch dimensions/constraints explicitly for those sizes to update with parameters.
- **Profiles**: a closed sketch can give several profiles (a rectangle with a circle gives
  the ring + the circle). `h.profile(sk, 'largest')` is the plate-with-holes case. To be sure,
  `print(len(h.profiles(sk)))`.
- **Sketch coordinates are local**. On `xy` they match the model. On `xz`/`yz`/faces they don't:
  pass 3-tuples `(x, y, z)` (model mm) to helpers and they get projected.
- **Fillets and chamfers last**, and on few edges at a time. If one fails, try a smaller radius
  or fewer edges; check `feature_problems`.
- **Don't trust, verify**: after each step check `bbox`/volume in `tree` and look at a shot.
  Never claim a part is right without having looked at it.
- If unsure about an API signature, use `f360 api ClassName.method` instead of guessing.
- Name things (`name=` on sketches and features, `body.name = 'lid'`): it makes `tree`
  readable and exports clean.

## FDM 3D printing

Read [reference/fdm.md](reference/fdm.md) before designing anything with fits, holes, threads,
snaps, thin walls or overhangs. Short version: walls in multiples of the line width
(0.4 nozzle: 0.8/1.2/1.6 mm), clearance 0.2-0.3 mm per side for sliding fits, holes +0.2 mm,
overhangs <= 45 deg, chamfer (not fillet) edges facing the bed, teardrop horizontal holes.

## Mechanical vs aesthetic

- Mechanical (brackets, enclosures, adapters, jigs): sketch + extrude/cut, parametric,
  exact dimensions, tolerances from fdm.md, `f360 fdm` before export.
- Aesthetic (vases, lamps, organic shapes, decorative): revolve splines, lofts between
  sections, sweeps, shells, big fillets. Iterate on shape with several views
  (`-v iso,front,iso_back --style shaded`) and show the user the renders for feedback.
Recipes for both: [reference/recipes.md](reference/recipes.md).
