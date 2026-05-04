# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A KiCad PCB project (`hardware/Nano-Board-rev-2.kicad_*`) wrapped in a KiBot-driven CI pipeline. The repo holds *no* firmware — it is the hardware design plus everything needed to render reports, generate manufacturing artifacts, and gate merges on ERC/DRC.

The KiCad project is the source of truth. Everything under `HTML/`, `manufacturing/`, and report files is *generated* by CI and committed back via `[skip ci]` auto-commits. Do not hand-edit those.

## CI pipeline (5 stages)

The workflows in `.github/workflows/` form a graduated pipeline keyed off branch and event:

| Stage | File | Trigger | Behavior |
|-------|------|---------|----------|
| 1 | `feature-push.yml` | push to `feature/**` | Informational. Runs full KiBot group; never fails the run. Auto-commits refreshed `HTML/` and README repo-name placeholder. |
| 2 | `pr-to-dev.yml` | PR → `dev` | **Merge gate.** Counts `severity=error` entries in DRC/ERC JSON; comments + fails on any. |
| 3 | `pr-to-qa.yml` | PR → `qa` | Same gate; on pass, builds full manufacturing artifact (`qa-package-<PR#>`). |
| 4 | `pr-to-main.yml` | PR → `main` | Same gate; produces `release-candidate-<PR#>`. |
| 5 | `release.yml` | push of tag `v*` | Builds full package, zips, creates GitHub Release. |

Branch protection on `dev`/`qa`/`main` requires the gate job's name as a status check (`ERC + DRC gate`, `QA build`, `Release-candidate build`).

## CI gotcha: ERC/DRC must run via KiBot, not `kicad-cli`

`kicad-cli pcb drc` / `kicad-cli sch erc` **do not honor the `rule_severities` overrides in `Nano-Board-rev-2.kicad_pro`**. A check the project promotes to `error` (e.g. `hole_clearance: error`) is reported as a `warning` by `kicad-cli`, which silently passes the gate. All four workflows now run preflights via `kibot ... visual` (or `... full` in `feature-push.yml`); the preflight engine matches the KiCad GUI behavior.

If you ever swap that step back to `kicad-cli`, the merge gates become useless.

## KiBot configuration layout

`config/kibot/kibot_main.yaml` is the orchestrator. It imports a templated set of single-purpose YAML files (one per output) and defines two groups:

- `visual` — schematic PDF, 4× 3D PNG renders, iBOM, navigate page.
- `full` — `visual` + STEP, gerbers, drills, CSV BOM, CSV pos.

Preflights (`kibot_pre_erc_report.yaml`, `kibot_pre_drc_report.yaml`) run before any group unless `--skip-pre erc,drc` is passed. Their output filenames are `erc-erc.{html,rpt,json}` and `drc-drc.{html,rpt,json}` (the `%i%I%v` template resolves the preflight name twice). The workflows depend on these exact paths.

`kibot_globals.yaml` lists numeric warning filters for known harmless KiBot warnings (missing 3D models on Windows-only paths, font substitutions, etc.). When a new noisy warning appears, add its number here rather than working around it elsewhere.

## Report generation

`config/generate_error_report.py` post-processes the KiBot/kicad-cli JSON+RPT outputs into styled HTML. Two modes, decided by which CLI flags are passed:

- Both `--erc-*` and `--drc-*` → combined `error-report.html`.
- Only one kind → single-kind page (`erc-erc.html` or `drc-drc.html`). The other kind's cards, status badge, and section are hidden.

The `feature-push.yml` publish step also strips `.rpt`/`.json` `output-box` tiles from the auto-generated `*-navigate_reports.html` (so the navigate page only links to the HTML pages, with download buttons embedded in the per-kind HTML).

## Common commands

```bash
# Run the full CI flow locally (mirrors what feature-push.yml does)
kibot -c config/kibot/kibot_main.yaml -d output \
      -e hardware/Nano-Board-rev-2.kicad_sch \
      -b hardware/Nano-Board-rev-2.kicad_pcb \
      --log kibot_run.log full

# Just the preflight (DRC + ERC), matches the merge-gate behavior
kibot -c config/kibot/kibot_main.yaml -d output \
      -e hardware/Nano-Board-rev-2.kicad_sch \
      -b hardware/Nano-Board-rev-2.kicad_pcb \
      visual

# Regenerate the styled HTML report from existing JSON/RPT
python3 config/generate_error_report.py \
    --erc-json output/reports/erc-erc.json \
    --drc-json output/reports/drc-drc.json \
    --erc-rpt  output/reports/erc-erc.rpt \
    --drc-rpt  output/reports/drc-drc.rpt \
    --output   output/error-report.html
```

The `kicad_auto:ki9` Docker image (`ghcr.io/inti-cmnb/kicad_auto:ki9`) is the reference environment used by all workflows. Reproduce CI locally with it if behavior diverges.

## Template usage

This repo is a reusable starting point. Spinning up a new project is a
two-step flow:

1. Create a new repo from this template (or clone + reset history).
2. Run `python scripts/rename_project.py <new-name>`.

The rename script edits the `KICAD_PROJECT` env in every workflow, the
KiBot navigate title in `kibot_main.yaml`, README/CLAUDE/TEMPLATE
references, and renames every `hardware/<old>*` file (kicad_pro,
kicad_pcb, kicad_sch, backups, 3D models, gerbers, production zip)
to match. See `TEMPLATE.md` for the full setup checklist (branch
protection, Pages, KiCad version pinning).

## Branch / commit / PR conventions

The repo follows the Fastbit firmware SOP (see global `~/.claude/CLAUDE.md`). Highlights that bind here:

- Never push directly to `main`, `qa`, or `dev`.
- Feature branches off `dev`; hotfixes off `main`, then cherry-pick to `dev`.
- Use `/fastbit-branch`, `/fastbit-commit`, `/fastbit-checkin`, `/fastbit-create-mr`.
- No mention of Claude/AI in commits, PR descriptions, or code comments.

## Things that look weird but aren't

- `HTML/` is fully wiped (`find HTML -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} +`) on every feature-push run before being repopulated. Don't put anything by hand in `HTML/` — it disappears on the next push.
- `Nano-Board-rev-2-drc.rpt` / `Nano-Board-rev-2-erc.rpt` in `hardware/` are KiCad GUI-side reports the user generates locally; they may diverge from `HTML/reports/*` if uncommitted board edits exist.
- The README has a `<!--REPO_NAME-->...<!--/REPO_NAME-->` marker that the publish step rewrites from `${{ github.event.repository.name }}` so the title tracks repo renames automatically.
