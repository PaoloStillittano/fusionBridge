# Installation and maintenance

[Back to README](../README.md) · [Italian quick start](README.it.md)

## Requirements

| Requirement | When needed |
| --- | --- |
| macOS | Supported automatic installation and tested application workflow |
| Python 3.9 or newer | Installer and both CLIs; runtime uses the standard library |
| Git | Clone and update the repository |
| Autodesk Fusion, opened at least once | Modeling and the Fusion add-in |
| Bambu Studio, opened and configured | Optional local slicing; current `b360` target is A1 |
| A configured A1 in your own Studio cloud account | Sending a print through the official GUI |
| A local assistant with shell access | Optional natural-language modeling; CLIs also work directly |

The installer does not install Fusion, Studio, Python, an AI client, or account credentials. Check `python3 --version` and `git --version` first. If Python is missing, install it from [python.org](https://www.python.org/downloads/macos/) or your preferred package manager, then reopen the terminal.

The last recorded live integration checks used Fusion 2705.1.30 and Bambu Studio 02.08.02.61. They are verification versions, not universal compatibility guarantees or minimum versions. See [verification](../VERIFICATION.md).

## Install from a checkout

Choose a stable folder: installed links continue pointing to this checkout.

```bash
git clone https://github.com/PaoloStillittano/fusionBridge.git
cd fusionBridge
./install.sh --dry-run
./install.sh --agent codex
```

| Option | Effect |
| --- | --- |
| `--agent codex` | Install the Codex skill and both CLIs |
| `--agent claude` | Install the Claude Code skill and both CLIs |
| `--agent both` | Install both skills; this is the default |
| `--agent none` | Install both CLIs without a skill |
| `--skip-fusion` | Skip the Fusion add-in, useful for Studio-only use |
| `--fusion-addins '/custom/AddIns'` | Explicit Fusion AddIns directory |
| `--dry-run` | Print the plan without writing files |
| `--uninstall` | Remove owned installation links; preserve projects and application data |
| `--home '/temporary/test-user'` | Alternative user root for isolated installer testing |

No administrator privileges or pip installation are needed. The installer does not edit your shell profile. Add `export PATH="$HOME/.local/bin:$PATH"` yourself if needed.

## What is installed

| Destination | Target in checkout |
| --- | --- |
| `~/.local/bin/f360` | `cli/f360` |
| `~/.local/bin/b360` | `cli/b360` |
| `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionBridge` | `addin/FusionBridge/` |
| `~/.agents/skills/fusion360` | `skill/fusion360/`, when Codex is selected |
| `~/.claude/skills/fusion360` | `skill/fusion360/`, when Claude is selected |

Existing legacy Codex installations at `~/.codex/skills/fusion360` are retained and updated instead of creating a second entry. Fresh Codex installs use the user skill directory documented in [OpenAI's skill guide](https://developers.openai.com/codex/skills/).

An installation receipt at `~/.fusion-bridge/install.json` records managed links for updates and uninstall. It contains local paths and stays outside the repository. It is separate from the add-in's private runtime `connection.json`.

If Fusion's Autodesk user directory is absent, the installer prints **SKIP** for the add-in and continues with the CLIs/selected skills. Open Fusion once and rerun, or supply `--fusion-addins`.

## Activate and verify

1. In Fusion, open **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins**.
2. Select **FusionBridge → Run**. Optionally enable **Run on Startup**.
3. If it is not listed, use **+** and select `addin/FusionBridge` from your checkout.
4. Run `f360 ping`. A successful connection returns `ok: true`; when a design is active, retain its `document_id` for guarded editing.
5. For slicing, run `b360 doctor`. It checks the installed binary, preset directory and required CLI options. It does not contact your printer or verify cloud login.
6. Open your assistant's skill list and check for `fusion360`; restart the client if discovery has not refreshed. The CLI works independently of skill discovery.

The first end-to-end local example is in the [README](../README.md#first-part-a-plate-with-two-holes). It creates a new Fusion document and exports into ignored `outputs/`. It does not send a print.

## Updates and moving the checkout

For normal updates, review local changes first, then:

```bash
git pull --ff-only
./install.sh --agent codex
```

Use the same agent selection as your original installation. Symlinks expose source changes immediately; Fusion may still need a reload or add-in restart. Stop the add-in before moving the checkout or changing its server code.

If you move the checkout, rerun the installer from the new location. The receipt allows replacing links owned by the previous location, including links whose old targets no longer exist. If there is no receipt and links point somewhere else, they are treated as unrelated; inspect and remove or relocate them manually before retrying.

## Conflicts and uninstall

The installer checks the entire destination plan before creating links. It refuses to replace real files or unrelated symlinks, including broken links. Review the reported path, preserve any content you need, and resolve the conflict yourself; do not use `sudo` to force an installation.

```bash
./install.sh --uninstall --dry-run
./install.sh --uninstall
```

Uninstall removes only matching managed links, plus recognizable links to this checkout from the original installer. Replaced files or links are preserved. The checkout, model files, account data, runtime connection file and shell configuration remain untouched. Stop FusionBridge in Fusion first; removing its symlink does not terminate an already running add-in. Remove a manually registered Add-Ins entry in Fusion if it remains listed.

## Troubleshooting

**`command not found: f360` / `b360`**

Add `~/.local/bin` to PATH, reopen your terminal, or invoke `python3 cli/f360 --help` / `python3 cli/b360 --help` from the checkout. Check the links have not been broken by moving or deleting the checkout.

**FusionBridge is not listed or `ping` cannot connect**

Activate the add-in as above. If a sandbox reports a network-permission error, the loopback connection may have been blocked; approve only the specific local command in your assistant rather than changing global sandbox settings. A modal dialog or busy Fusion process may delay a command. A timeout is not proof that an executing model operation stopped: inspect before retrying. Never share the token from `connection.json`.

**Bambu Studio is installed somewhere else**

The default is `/Applications/BambuStudio.app`. Use a global option before the command:

```bash
b360 --app '/path/to/BambuStudio.app' doctor
```

Alternatively set `BAMBU_STUDIO_APP` in your own environment. For an explicit executable rather than an app bundle, also set `BAMBU_STUDIO_PROFILES` to its installed `profiles/BBL` directory. These overrides do not add verified support for another OS or printer.

**Missing or incompatible presets**

Open the installed Studio version and configure the appropriate A1 profiles. Discover exact names with `b360 presets machine`, `b360 presets process`, and `b360 presets filament`. The tool resolves installed system presets, not arbitrary account-synced custom profiles. Do not copy preset bundles or credentials into this repository.

**Slicer aborts under an assistant sandbox**

Studio may require access to macOS graphics services. Review the private job's `slicer.log` and approve the narrow local slicing command if required. Keep the isolated data directory; do not bypass slicer checks or reuse the GUI's account data directory.

**Slicing succeeded but the printer is offline**

Slicing and `doctor` do not establish a cloud connection. Inspect Device in Studio and verify the actual printer, account and physical setup before a specific requested print. `handoff` performs no upload; `status` is a local observation record.

## Sharing a bug report

Include the tool revision, OS, Python/Fusion/Studio versions, command structure and a sanitized error. Remove names, local user paths, tokens, printer identifiers, account details and private geometry. Reproduce with the supplied synthetic example when possible. Full logs, screenshots and 3MF job bundles can contain personal data and should not be attached without review.
