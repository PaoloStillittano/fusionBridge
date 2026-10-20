# Repository instructions

These rules apply to contributors and coding agents throughout FusionBridge.

## Communication and scope

- Lead with the conclusion, then the reason. Be concise without omitting causes, trade-offs or limitations.
- Match the user's language. Separate verified results, assumptions and untested behavior.
- For multiple requests, number them and identify the current one. Ask one consolidated question only when missing information materially changes the work.
- Preserve the structure of drafts being revised and explain significant changes.
- Inspect the working tree before editing. Preserve unrelated changes and do not revert user work.
- Do not create commits, push, publish releases, or rewrite history unless the user explicitly requests it. Stage only named, reviewed files; never use blanket staging.

## Public repository: private data must stay out of Git

- Never commit credentials, tokens, passwords, API keys, account/session data, printer access codes, Wi-Fi configuration, private addresses, device identifiers, or cloud connection files.
- Never commit personal photos, customer files, private CAD designs, exports, sliced projects, G-code, screenshots, job manifests, logs, backups, or local configuration. Keep generated work under ignored `outputs/` or outside the repository.
- Use synthetic fixtures and placeholder identities in tests and examples. Public project attribution and public repository URLs are intentional metadata; do not replace them with personal runtime data.
- Do not copy Bambu Studio login data, network plugins, proprietary preset bundles, or Autodesk installations into this repository. Resolve installed presets locally.
- Do not expose secret values in terminal output, issue reports, review comments, screenshots, or documentation. Redact evidence before sharing it.
- `.gitignore` is a first barrier, not proof of privacy: it does not protect files already tracked. Before an authorized commit, inspect `git status --short`, `git diff`, `git diff --cached --stat`, and `git diff --cached`; review every staged file, including new and binary files.
- If a credential is discovered in a tracked file, stop publication and report its location without printing the value. Removing the current line does not remove Git history; credential rotation and any history rewrite require a separately agreed response.
- Never silently force-add ignored files or weaken privacy exclusions. Deliberately public, synthetic binary fixtures require explicit review.

## Architecture and compatibility

- FusionBridge is a Fusion add-in, two Python CLIs, and an agent skill. It does not currently implement an MCP server or an independent autonomous agent.
- Runtime Python code uses the standard library outside Fusion. Fusion API imports belong in the add-in, not in the local CLI or installer.
- The supported installation workflow is macOS. The current `b360` slicing target is Bambu Lab A1; do not claim other printers or platforms are supported without implementation and verification.
- Keep installation reversible. Do not overwrite existing files or unrelated symlinks, change shell configuration automatically, install external applications silently, or request administrator privileges for a normal user installation.
- Keep public instructions portable: no author-specific absolute paths, installed hardware assumptions, or account details.
- Use an appropriate public or GitHub noreply Git identity for authorized commits. Check both author and committer email before publication; never inherit an unrelated global/work identity silently.

## CAD and print invariants

- Bind operations on existing designs to `document_id`. Do not redirect edits to whichever document happens to become active.
- Helpers use millimeters; raw Fusion API lengths use centimeters and angles use radians. Public parameter values use their declared unit; retain explicit internal values separately.
- Preserve BRep and mesh handling in inspection and STL/3MF exports. Never silently omit unsupported visible geometry. Successful exports must produce nonempty files.
- `fdm --mode plate` evaluates the shared global Z=0 bed and combined bounds. `part` evaluates individual bodies relative to their bases; it cannot prove a complete plate fits.
- A successful command, watertight mesh, or sliced file does not prove visual fidelity, printability, load capacity, or an optimal preset. Report checks and remaining limits accurately.
- Rollback only covers supported appended timeline operations. A timed-out job may still be running: inspect before retrying.
- Preserve full local preset resolution, isolated slicer data, input/project integrity checks, unique job directories, and serialized submission records.

## Physical printing and cloud state

- Development, installation, documentation, and automated tests do not authorize a physical print. Start a print only for a specific user-requested part and destination after checking the actual nozzle, material, plate, and device availability.
- Cloud submission uses the official authenticated Bambu Studio interface. Do not extract credentials or invent an unsupported cloud API.
- Distinguish preparation, opening a project, submission, printing, and completion. `record` stores observations and `status` reads local history; neither is live printer telemetry.
- After an uncertain Send result, inspect the Device page and existing task before another attempt. Do not bypass duplicate-attempt or integrity guards.

## Validation and documentation

- Run `python3 -m unittest discover -s tests -v` for behavioral changes. Add meaningful regression coverage for changed behavior, especially installation ownership, units, mesh export, and job integrity.
- Test installation in temporary directories. Never use a real account, user's active design, or printer as an automated test fixture.
- Live Fusion/slicer checks are separate integration checks. Report exact versions and what was observed; never label an unexecuted integration check as passed.
- Keep README, installation instructions, CLI help, and skill references consistent when commands or supported workflows change.
- Keep generated evidence private and ignored. Commit only sanitized, reproducible findings; do not claim that local evidence is available in the public clone.
