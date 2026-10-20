# Verification scope

This document separates recorded integration results from behavior that has not been verified. Local evidence, CAD files, logs and sliced jobs are private test artifacts and are not distributed in the public repository.

## Recorded integration checks — 18 October 2026

- The original automated suite passed **34 tests**, using synthetic fixtures without cloud accounts or physical printing.
- The agent skill passed the `skill-creator` validator.
- Fusion **2705.1.30**: a temporary design exercised BRep and mesh inspection, parameters in declared units (20 mm and 10 degrees), plate FDM checks, mixed STL/3MF exports and F3D archive export. The original design was restored without changing its timeline.
- A mismatched `document_id` was rejected before command execution.
- Mixed STL export contained 24 triangles with X bounds of 0–40 mm; exported files were nonempty.
- Bambu Studio **02.08.02.61**: real slicing from STL and 3MF, including Fusion exports, with A1 PLA 0.4, detailed PLA 0.2 and structural PETG 0.4 configurations, plus automatic orientation.
- Sliced projects contained G-code; ZIP integrity, checksums and embedded printer/nozzle/plate/material settings were verified.
- Integrity and concurrency checks rejected modified projects/presets, duplicate uncertain submissions and concurrent attempts to reserve the same job.

These application versions describe the tested installation. They do not establish compatibility with every version, operating system or printer.

## Unverified behavior and limitations

- **No cloud submission, physical print start or print completion has been verified.** The GUI integration check encountered a disconnected-printer warning and a computer-control timeout.
- Cloud submission is a workflow through the official authenticated Bambu Studio GUI, not a `b360` cloud endpoint. Opening a project or recording a state does not prove submission.
- Preset selection is guided by part requirements and slicer results; it does not establish global optimality, mechanical strength or photographic likeness.
- Geometric checks do not certify minimum wall thickness, exact collisions, adhesion or load capacity.

## Reproducing automated checks

On 20 October 2026 the expanded suite passed **44 tests**, including the installer cases
below. Python/shell syntax, local documentation links and the skill validator also passed.
Live Fusion modeling, slicing and cloud submission were not repeated for this documentation
and installation update.

```bash
python3 -m unittest discover -s tests -v
```

The suite also includes isolated installer checks added for public installation: fresh/repeated install, paths with spaces, conflict preservation, dry run, checkout relocation, legacy skills, rollback after receipt failure, custom AddIns paths and uninstall. These checks do not modify the real user's installation.

Live Fusion/Studio checks require those applications and separate integration testing. Use a new temporary design and ignored output directory. Any physical print requires a specific user request, an available printer and visual review in Studio; it is not part of automated development tests.
