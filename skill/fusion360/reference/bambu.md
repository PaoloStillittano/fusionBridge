# Model to Bambu Studio cloud print

This workflow supports **Bambu Lab A1**. Cloud printing requires the user's own printer
connected to their **Bambu cloud account** in Studio; do not assume it is configured.
For a requested cloud job, keep that transport; do not enable LAN Only, Developer Mode or replace the
printer firmware as a workaround. Account login and printer communications remain in the
official Bambu Studio GUI. Do not extract account tokens, passwords or printer access codes.

## What the tools actually do

- `b360 doctor`: locate Studio, its version, presets and supported CLI flags. It does not
  verify cloud login, the installed nozzle, the actual filament, or whether a printer is online.
- `b360 presets machine|process|filament --search TEXT [--compatible "EXACT PRINTER"]`:
  discover installed system presets. Inherited settings and machine G-code includes are resolved.
- `b360 prepare INPUT... --out NEW_JOB_DIR`: copy inputs, snapshot full presets, arrange,
  slice in an isolated data directory and produce `project.3mf`, `job.json`, settings,
  logs, exact command and checksums. Existing output directories are never overwritten.
- `b360 inspect PROJECT.3mf`: inspect embedded settings, sliced G-code, estimates and warnings.
- `b360 handoff JOB_DIR`: verify project/preset hashes and return the exact file for GUI review.
  It neither uploads nor starts a print.
- `b360 record JOB_DIR --state STATE --printer NAME --evidence "ACTUAL OBSERVATION" [--task-id ID]`:
  persist a state observed in the GUI. This does not operate the printer or fetch telemetry.
- `b360 status JOB_DIR`: read that observation history, including uncertainty.

Studio CLI may need execution outside an agent's filesystem sandbox to access graphics
services. Diagnose an actual abort; use ordinary tool approval for the narrow local command.
Run the CLI through `b360`, which isolates Studio's incidental `result.json` and data files.

## Choose the setup for the part

Start from the requested function, finish, load direction, mating surfaces and hardware
actually available. The default design setup is 0.4 mm / PLA / textured PEI, not an assertion
about the hardware currently mounted. Use the user's exact filament brand/profile when known.
Other installed compatible PLA/PETG system presets can be chosen by exact name.

Supported `prepare` options:

```text
--nozzle 0.4|0.2
--purpose balanced|strength|detail|draft
--filament "EXACT INSTALLED PRESET"
--process "EXACT INSTALLED PRESET"          optional explicit process
--plate textured|smooth|cool|supertack
--supports auto|tree|none
--orientation preserve|auto
--set-process KEY VALUE                    repeatable, controlled process keys
```

`balanced`, `strength`, `detail` and `draft` choose existing A1 process presets. They are
starting points, not an automatic proof of optimality or strength. For 0.2 strength, the
standard process is adjusted to four walls and 25% infill. All changes are written to the job.
The slicer checks preset compatibility; it cannot verify installed hardware.

Preserve an orientation intentionally modeled for strength, clearances or visible finish.
Use auto orientation only when suitable, then inspect the result. For an assembly, export
the intended printable bodies separately (`f360 export ... --each`) before passing them
together to `prepare`: the mounted assembly is not a plate arrangement. For a single organic
mesh, preserve the flat base; mesh closure does not prove photo likeness.

Adapt supports, brim, wall count, infill and layer height to the piece. Compare a small number
of justified alternatives on the same hardware when the trade-off matters, using actual
slicer seconds/grams and visual review. Do not call a preset optimal solely because it has
the shortest time. Do not select another nozzle/material without accounting for a physical change.

Before preparation, inspect the model and FDM warnings. `--mode plate` uses Z=0 and combined
bounds; `--mode part` reports each body's local base. Neither substitutes for slicer collision,
exclusion-zone or toolpath checks. Do not use Studio's `--no-check` to force a job through.

Example (paths stand for the current part's export and a new job directory):

```bash
b360 prepare part.stl --out jobs/pla-detail-01 --nozzle 0.4 --purpose detail \
  --filament "Bambu PLA Basic @BBL A1" --plate textured --supports tree
b360 inspect jobs/pla-detail-01/project.3mf
b360 handoff jobs/pla-detail-01
```

Inspect the embedded warnings as well as command success. Estimate fields are slicer
predictions. A sliced job starts as `sliced_needs_visual_review`, `cloud_state: not_submitted`.

## Open and review in Studio

Use available computer-use tools for the GUI, and derive controls from fresh state. On
macOS the usual app bundle is `com.bambulab.bambu-studio`. Prefer accessible controls and keyboard
shortcuts when custom toolbar buttons are absent from the accessibility tree.

Open the exact file returned by `handoff` as a **project**, not just imported geometry. Preserve
any pre-existing unsaved project. On macOS `Cmd+O`, then `Cmd+Shift+G` in the Open dialog,
allows selecting an absolute path. Inspect the loaded filename, printer, nozzle, bed, filament,
layers, supports and arrangement in Preview. Do not save over the immutable prepared file;
prepare a new job if settings change. Embedded thumbnail images alone do not validate toolpaths.

In Studio, **Print plate** opens the submission dialog. The official source lists
`Cmd+Shift+G` on macOS (`Ctrl+Shift+G` on Windows/Linux) for this action. This shortcut is
context-sensitive: inside the macOS Open dialog it means Go to Folder. Observe the result.
Do not press the shortcut when a different dialog has focus.

## Cloud submission and monitoring

Developing this tool, preparing files, or a generic desire for printing does not choose a
specific model to print. Submit only when the user has requested the concrete job and target;
honor existing explicit authorization without repeatedly asking. Have the actual nozzle,
plate, filament mapping and bed availability established for that print.

1. Run `handoff` and review the exact sliced project in Studio. Open Print plate and read
   the selected A1, online/idle state, filament/AMS mapping and options. A logged-in account
   is not proof that the intended device is connected. If login/device selection is missing,
   resolve it in the official GUI; do not substitute a different printer.
2. Immediately before Send, record `submission_pending` with the target printer and the
   observed job/setup. This atomically reserves the attempt across agents/processes. If it
   fails or a previous attempt exists, inspect its state instead of clicking Send.
3. Click Send once. Observe its result and record `submitted`, `printing`, `failed` or
   `unknown` with actual evidence. Do not treat an upload acknowledgment as printing.
4. Read Device for the same target/job, recording task ID when shown, progress and actual
   completion/failure. `status` is a local history, never a substitute for reading Device.
   If later monitoring is requested, use the platform's automation tools to schedule it.

After an uncertain response, inspect Device and the print history before any further action.
The same bundle cannot be handed off again after an attempt. A deliberate reprint uses a
new prepared bundle after resolving the old attempt. Do not fabricate state observations or
reset the ledger to make an uncertain operation retryable. A local ledger cannot prevent
someone from manually printing a file outside this workflow.

If GUI control is unavailable, complete preparation and provide the ready project plus the
concrete GUI blocker. Label cloud submission/monitoring as unverified, not completed.

## Sources and tested boundary

- [Official Studio CLI](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage):
  settings, filaments, arrangement, slicing and 3MF export. It does not document cloud Send.
- [Official keyboard shortcut definitions](https://github.com/bambulab/BambuStudio/blob/master/src/slic3r/GUI/KBShortcutsDialog.cpp).
- Local validation on 18 October 2026: Studio 02.08.02.61, real A1 PLA 0.4 / PLA 0.2 /
  PETG 0.4 slicing, embedded G-code and matching settings. Actual submission and physical
  print completion must be validated on the chosen printer/job; they are not implied by these tests.
