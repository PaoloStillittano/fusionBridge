# FusionBridge

**Build CAD parts in Autodesk Fusion with an AI assistant, inspect the geometry, and prepare sliced Bambu Studio projects.**

FusionBridge connects an assistant such as Codex or Claude Code to Fusion through a local Python add-in. You can also use both command-line tools directly, without an AI assistant.

[Guida in italiano](docs/README.it.md) · [Installation and troubleshooting](docs/installation.md) · [Agent workflow](skill/fusion360/SKILL.md)

## What works today

- **Model in Fusion:** execute Python scripts, create sketches and solids, edit parameters, inspect bodies and timeline health, and capture screenshots.
- **Inspect and export:** handle solids and meshes, check bed contact and build-volume bounds, and export STL, 3MF, STEP or F3D where supported.
- **Prepare A1 jobs:** resolve installed printer/material/process presets, slice with the real Bambu Studio CLI, and inspect embedded G-code, settings, estimates and warnings.
- **Review before printing:** produce a checked project for the official Bambu Studio interface and record observed submission states.

**Supported installation: macOS. Current slicing target: Bambu Lab A1**, with 0.4 or 0.2 mm nozzles and installed compatible PLA/PETG presets. Windows/Linux installation and other printer models are not currently supported by this workflow.

Cloud submission and physical print completion remain **unverified**. `b360` does not upload files or start a print. Sending a job uses the authenticated Bambu Studio interface, manually or through an assistant with computer-control tools. See [verification scope](VERIFICATION.md).

## Install

You need Git, **Python 3.9+**, and [Autodesk Fusion](https://www.autodesk.com/products/fusion-360/overview), installed and opened at least once. Install [Bambu Studio](https://bambulab.com/en/download/studio) if you want slicing. A cloud account and configured printer are needed only when sending a print through Studio.

```bash
git clone https://github.com/PaoloStillittano/fusionBridge.git
cd fusionBridge
./install.sh --dry-run
./install.sh --agent codex
```

Use `--agent claude`, `--agent both` (the default), or `--agent none` for CLI-only use. No pip packages are required. The installer creates user-level symlinks and downloads nothing; **keep the checkout in place**.

If `f360` is not found, add this to your current terminal, and optionally your shell configuration:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

In Fusion, open **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins**, select **FusionBridge**, and click **Run**. Enable **Run on Startup** if desired. If absent, use **+** to select this checkout's `addin/FusionBridge` directory.

```bash
f360 ping
b360 doctor   # optional: checks Studio, not cloud login or printer connectivity
```

The assistant needs local shell access. A browser-only chat cannot directly operate this local add-in. See the [installation guide](docs/installation.md) for paths, updates, conflicts, uninstall and sandbox troubleshooting.

## First part: a plate with two holes

Run from the repository directory with Fusion open and the add-in running. `new` creates a separate design; the example refuses to modify a nonempty document.

```bash
f360 new
f360 exec examples/plate.py
f360 tree
f360 shot -o outputs/plate.png -v iso,front,top
f360 fdm --bed 256x256x256 --strict
f360 export outputs/plate.stl
f360 export outputs/plate.3mf
```

The example creates a **40 × 30 × 4 mm** plate with two **3.4 mm** through holes, **24 mm** apart. `plate_thickness` drives the extrusion; the sketch sizes are numeric. Open the generated screenshots and inspect the model before proceeding. Save in Fusion if you want to retain the editable design.

When editing an existing design, copy `document_id` from `f360 ping` or `tree` and guard subsequent commands:

```bash
f360 --document-id YOUR_DOCUMENT_ID params --set plate_thickness '5 mm'
```

## Slice for Bambu A1

For an A1 with a 0.4 mm nozzle, PLA and textured PEI, start with:

```bash
b360 doctor
b360 presets filament --search PLA --compatible 'Bambu Lab A1 0.4 nozzle'
b360 prepare outputs/plate.stl --out outputs/jobs/plate-01 \
  --nozzle 0.4 --purpose balanced --plate textured --supports none
b360 inspect outputs/jobs/plate-01/project.3mf
b360 handoff outputs/jobs/plate-01
```

`prepare` uses installed presets; without `--filament`, it selects the machine preset's default. To match your actual material, choose an exact name from `presets` and pass `--filament 'EXACT PRESET NAME'`.

Each job needs a **new output directory**. It contains input copies, resolved presets, the exact command, slicer logs, checksums and a sliced `project.3mf`. Studio uses an isolated data directory, separate from the GUI's account settings.

Choose `balanced`, `strength`, `detail` or `draft` for a starting process preset. You can specify installed process/material names, supports, plate type, orientation and selected process overrides. Use `b360 prepare --help` and the [Bambu workflow](skill/fusion360/reference/bambu.md) for details. Preset selection does not prove optimality or physical strength.

`handoff` verifies integrity and returns the project path; it does not open or upload it. Open that file **as a project** in Studio, inspect Preview, and check the actual printer, nozzle, filament, plate, layers and supports before **Print plate**. An uncertain Send result requires checking Device before retrying.

`b360 record` saves a state you actually observed; `b360 status` reads that local history. Neither provides live printer telemetry. Documentation, installation and slicing do not authorize a physical print.

## How it fits together

```text
Assistant / terminal → f360 → authenticated localhost HTTP → FusionBridge add-in → Fusion API
                    → b360 → installed Bambu Studio CLI → sliced project.3mf
User / GUI-capable assistant → authenticated Studio GUI → cloud-connected printer
```

This repository provides **an add-in, two CLIs and an agent skill**. It is not an MCP server or a separate autonomous agent.

| Component | Purpose |
| --- | --- |
| `addin/FusionBridge/` | Runs inside Fusion; executes queued commands on Fusion's main thread |
| `cli/f360` | JSON-oriented Fusion command-line client |
| `cli/b360`, `cli/printbridge/` | Installed preset resolution, slicing, project integrity and observed-state records |
| `skill/fusion360/` | Modeling and print workflow for a local assistant |
| `examples/plate.py` | Small reproducible modeling example |
| `scripts/install.py` | Reversible user-level installation |

## Limits and privacy

- Geometric checks are screening tools, not proof of adhesion, collision-free toolpaths, minimum wall thickness or load capacity. `fdm --mode plate` checks global Z=0 and combined bounds; `part` checks individual bases.
- STEP cannot preserve arbitrary meshes: visible mesh geometry causes explicit rejection. STL/3MF include supported visible solids and meshes, with millimeter output and nonempty-file checks.
- A command's `ok` reports execution. Also inspect feature health, geometry, warnings and Preview. Rollback covers only supported appended timeline entries; a timed-out command may still be running.
- The bridge listens on `127.0.0.1` and uses a private token file at `~/.fusion-bridge/connection.json`. `exec` runs Python inside your Fusion process: run trusted scripts only and do not expose the bridge publicly.
- Keep personal CAD files, photos, exports, sliced jobs, screenshots, logs and credentials under ignored `outputs/` or outside this repository. Do not attach unsanitized job bundles to public issues. See [AGENTS.md](AGENTS.md).

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests use synthetic fixtures and temporary directories. They do not use cloud accounts or start prints. Installer tests leave your real application and skill directories untouched. Live Fusion and Studio integration checks are separate; [VERIFICATION.md](VERIFICATION.md) states the recorded scope.

After changing `helpers.py`, `commands.py` or `fdm.py`, run `f360 reload`. Changes to `server.py` or `FusionBridge.py` require stopping and restarting the add-in.

For modeling scripts, start with the [helper reference](skill/fusion360/reference/helpers.md), [Fusion API notes](skill/fusion360/reference/fusion-api.md), and [recipes](skill/fusion360/reference/recipes.md).
