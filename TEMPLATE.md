# Using this repo as a project template

This repo is set up as a reusable starting point for KiCad projects. To
spin up a new board:

1. **Create a new repo from this template.** On GitHub, click "Use this
   template → Create a new repository", or clone and reset history:
   ```powershell
   git clone https://github.com/<owner>/Kicad_Template.git MyBoard
   cd MyBoard
   Remove-Item -Recurse -Force .git
   git init
   git remote add origin https://github.com/<owner>/MyBoard.git
   ```

2. **Rename the project.** Run the rename script — it edits every
   workflow, the KiBot title, README/CLAUDE/TEMPLATE references, and
   renames the four `hardware/<name>.kicad_*` files plus their backups,
   3D models, gerbers, and production files in one shot:
   ```powershell
   python scripts/rename_project.py MyBoard-rev-1
   ```
   Use `--dry-run` first to preview. The script refuses to run on a
   dirty git tree unless you pass `--force`.

3. **Commit the rename and your initial board.**
   ```powershell
   git add .
   git commit -m "init: rename to MyBoard-rev-1"
   git push -u origin main
   ```

4. **Set up branch protection** on `dev`/`qa`/`main` so the merge gates
   run. For each branch on GitHub:
   *Settings → Branches → Add ruleset → Required status check*:
   - `dev` → `ERC + DRC gate`
   - `qa` → `QA build`
   - `main` → `Release-candidate build`

5. **(Optional) Enable GitHub Pages** so the rendered `HTML/` site is
   browsable from any device:
   *Settings → Pages → Source: "GitHub Actions"*. Then push the Pages
   workflow if you want auto-deploy (not included by default — ask if
   you want it added).

That's it. After step 3, every push to a `feature/**` branch produces
3D PNG renders, schematic PDF, iBOM, and a navigate page committed
back under `HTML/`.

---

## What's pinned to a specific version

| Thing | Where | Why it matters |
|---|---|---|
| **KiCad 9** | `container: image: ghcr.io/inti-cmnb/kicad_auto:ki9` in every workflow | Open the `.kicad_pro` in KiCad 9. A newer KiCad will silently upgrade the file format on save and CI may fail to parse it. Stick to one version per project. |
| **KiBot config schema** | `kibot:\n  version: 1` in every YAML under `config/kibot/` | KiBot 1.x. If you upgrade KiBot major version, expect to update these. |
| **Project name + dir** | `KICAD_PROJECT` and `KICAD_PROJECT_DIR` env blocks in all 5 workflows | Use `scripts/rename_project.py`. |
| **KiBot navigate-page title** | `TITLE: '<name>'` in `config/kibot/kibot_main.yaml` | Same — handled by the rename script. |

## Common gotchas

- **DRC gate fails after rename but the board has no errors.** Likely
  the old project name is still cached in `output/` or `HTML/` from a
  previous run. Both are wiped at the start of each CI run, so a fresh
  push fixes it.
- **`kicad-cli` reports fewer errors than KiCad's GUI.** This is a
  known difference — `kicad-cli` ignores the `rule_severities`
  overrides in `.kicad_pro`. The workflows run preflights via KiBot
  (which honors them) for exactly this reason; do not switch back to
  `kicad-cli`.
- **HTML/ keeps changing on every push.** Expected. Each CI run
  regenerates `HTML/` from scratch and auto-commits with `[skip ci]`.
  This means hand-edits to anything under `HTML/` are lost on the
  next push.

## What only the schematic, no PCB?

The PCB-dependent outputs (DRC, gerbers, drills, 3D, STEP, BOM,
pick-place, navigate page) all fail or get skipped, and the merge
gates error out because `kibot_pre_drc_report.yaml` runs
unconditionally. To support schematic-only projects you'd need a
separate KiBot group (e.g., `schematic_only`) and a workflow variant
that runs only that group. Worth doing only if you actually have such
projects.

## Will it run on another PC?

- **Viewing the GitHub repo / Pages site**: any browser, anywhere.
- **Editing the board**: needs KiCad 9 installed locally.
- **Reproducing CI locally**: pull `ghcr.io/inti-cmnb/kicad_auto:ki9`
  with Docker, then run the same `kibot ... full` command CI runs (see
  `CLAUDE.md → Common commands`).
