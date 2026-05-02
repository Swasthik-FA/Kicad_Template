# KiCad PCB CI/CD Template

[![Feature push](https://github.com/OWNER/REPO/actions/workflows/feature-push.yml/badge.svg)](../../actions/workflows/feature-push.yml)
[![PR to dev](https://github.com/OWNER/REPO/actions/workflows/pr-to-dev.yml/badge.svg?branch=dev)](../../actions/workflows/pr-to-dev.yml)
[![PR to qa](https://github.com/OWNER/REPO/actions/workflows/pr-to-qa.yml/badge.svg?branch=qa)](../../actions/workflows/pr-to-qa.yml)
[![PR to main](https://github.com/OWNER/REPO/actions/workflows/pr-to-main.yml/badge.svg?branch=main)](../../actions/workflows/pr-to-main.yml)
[![Release](https://github.com/OWNER/REPO/actions/workflows/release.yml/badge.svg)](../../actions/workflows/release.yml)

> Replace `OWNER/REPO` in the badge URLs with your actual GitHub `owner/repo` once the project is pushed.

A complete GitHub Actions pipeline for KiCad 8.x projects. Visual previews on every feature branch push, ERC/DRC gating on every promotion, and a versioned manufacturing ZIP on every release tag.

---

## Branching strategy

```
   feature/*  ──► dev  ──► qa  ──► main  ──► tag (v1.0.0)
       │          │        │       │           │
       │          │        │       │           └──── Stage 5: build & publish
       │          │        │       │                 release ZIP + GitHub Release
       │          │        │       │
       │          │        │       └──────────────── Stage 4: re-run ERC/DRC,
       │          │        │                         build release-candidate
       │          │        │
       │          │        └──────────────────────── Stage 3: re-run ERC/DRC,
       │          │                                  build full QA package
       │          │                                  (gerbers, BOM, 3D, …)
       │          │
       │          └────────────────────────────────  Stage 2: ERC/DRC GATE.
       │                                             Failure blocks the merge.
       │                                             On success: visual exports
       │                                             + interactive HTML BOM.
       │
       └───────────────────────────────────────────  Stage 1: visual preview
                                                     (PNG/SVG of schematic and
                                                      PCB). NO ERC/DRC.
```

| Stage | Trigger | What runs | Blocks merge? |
|------:|---------|-----------|---------------|
| 1 | push to `feature/**` | visual exports only | n/a |
| 2 | PR → `dev` | ERC + DRC + visual + iBOM | **yes (on fail)** |
| 3 | PR → `qa` | ERC + DRC + full manufacturing package | **yes (on fail)** |
| 4 | PR → `main` | ERC + DRC + release-candidate package | **yes (on fail)** |
| 5 | tag `v*` push | full package zipped + GitHub Release | n/a |

---

## Project layout

```
.
├── hardware/              ← KiCad project files (.kicad_pro, .kicad_sch, .kicad_pcb)
├── manufacturing/         ← .gitkeep only — generated files live in CI artifacts
├── docs/                  ← manual documentation
├── config/
│   ├── kibot-visual.yaml      ← Stage 1 preset: PNG/SVG previews, no checks
│   ├── kibot-full.yaml        ← Stages 2–5 preset: ERC/DRC + full outputs
│   └── generate_error_report.py  ← parses ERC/DRC JSON → error-report.html
└── .github/workflows/
    ├── feature-push.yml
    ├── pr-to-dev.yml
    ├── pr-to-qa.yml
    ├── pr-to-main.yml
    └── release.yml
```

The KiCad project name is configured via the `KICAD_PROJECT` environment variable at the top of every workflow. Default: `Nano-Board-rev-2`. To reuse this template for another board:

1. Move your KiCad files into `hardware/`
2. Edit the `KICAD_PROJECT:` line in each workflow file in `.github/workflows/`

---

## Quick start

1. **Move existing KiCad files** into `hardware/`:
   ```
   hardware/
   ├── Nano-Board-rev-2.kicad_pro
   ├── Nano-Board-rev-2.kicad_sch
   ├── Nano-Board-rev-2.kicad_pcb
   ├── *.kicad_sym, *.kicad_mod          (any project-local libraries)
   └── 3d/, fp/, ...                     (any local model directories)
   ```

2. **Push to GitHub** and create the three protected branches:
   ```bash
   git checkout -b dev   && git push -u origin dev
   git checkout -b qa    && git push -u origin qa
   git checkout main     && git push -u origin main
   ```

3. **Configure branch protection** for `dev`, `qa`, `main` (see next section).

4. **Start a feature branch** and push:
   ```bash
   git checkout -b feature/add-power-stage dev
   # ... edit board ...
   git push -u origin feature/add-power-stage
   ```
   The Stage 1 workflow runs and uploads visual previews as a workflow artifact.

5. **Open a PR** `feature/* → dev`. Stage 2 runs; if ERC/DRC fail, the PR is blocked and an `error-report.html` is uploaded.

6. **Promote** with PRs `dev → qa` and then `qa → main`.

7. **Tag a release** on `main` to publish the manufacturing ZIP:
   ```bash
   git checkout main && git pull
   git tag -a v1.0.0 -m "First production release"
   git push origin v1.0.0
   ```

---

## Branch protection setup

Configure these rules in GitHub: **Settings → Branches → Add branch ruleset** (or *Branch protection rules* on classic).

### `dev`
- ☑ Restrict deletions
- ☑ Require a pull request before merging
  - ☑ Require approvals — **1**
- ☑ Require status checks to pass before merging
  - ☑ Require branches to be up to date before merging
  - **Required check:** `ERC + DRC gate`  ← exact job name from `pr-to-dev.yml`
- ☑ Block force pushes

### `qa`
- ☑ Restrict deletions
- ☑ Require a pull request before merging
  - ☑ Require approvals — **1**
- ☑ Require status checks to pass before merging
  - **Required check:** `QA package build`  ← from `pr-to-qa.yml`
- ☑ Block force pushes

### `main`
- ☑ Restrict deletions
- ☑ Require a pull request before merging
  - ☑ Require approvals — **1** (or **2** for stricter gating)
  - ☑ Dismiss stale approvals on new commits
- ☑ Require status checks to pass before merging
  - **Required check:** `Release-candidate build`  ← from `pr-to-main.yml`
- ☑ Block force pushes
- ☑ Restrict who can push (recommended: maintainers only)

> The required-check names **must match the `name:` field of each job** in the workflow file. If you rename the jobs, update the protection rule.

---

## What you get from each stage

### Stage 1 — feature push
- `visual-preview-<branch>-<sha>` artifact:
  - `visual/schematic/*.svg` and `*.pdf`
  - `visual/pcb/*-pcb-top.png`, `*-pcb-bottom.png`
  - `visual/pcb/*-pcb-top.svg`, `*-pcb-bottom.svg`

### Stage 2 — PR → dev
- **On success:** `pr-review-<PR#>` artifact with visual exports + interactive HTML BOM.
- **On failure:** `error-report` artifact → open `error-report.html` in your browser (see below).

### Stages 3 & 4 — PR → qa, PR → main
- **On success:** full manufacturing package artifact:
  - `manufacturing/gerbers/` — gerbers + Excellon drills (JLCPCB defaults)
  - `manufacturing/assembly/*-pick-place.csv`
  - `bom/*-bom.csv` (Reference, Value, Footprint, Quantity, LCSC, MPN, Manufacturer)
  - `bom/*-ibom.html` — interactive HTML BOM
  - `visual/schematic/*.pdf`, `visual/pcb/*.pdf`
  - `visual/3d/*-3d-top.png`, `*.step`
- **On failure:** `error-report` artifact (same as Stage 2).

### Stage 5 — release tag
- A GitHub Release is created with auto-generated notes (commits since the previous tag) and a single attached file:
  - `<project>-<tag>-manufacturing.zip` containing all of the above

---

## The error report

When ERC or DRC fails at any gated stage, the pipeline writes a single self-contained `error-report.html` and uploads it as the `error-report` artifact (14–30 day retention). It contains:

- A red FAIL banner with project, branch, commit SHA, run timestamp, and a link to the workflow run.
- Summary cards: ERC errors / warnings, DRC errors / warnings, pass/fail badges per check.
- An ERC violations table: severity badge, code, description, affected components, sheet, coordinates.
- A DRC violations table: severity, violation type, description, nets/pads, layer, coordinates, clearance values.
- Optional embedded PCB top-view image when available.
- Live filters: search by ref/net, filter by severity, filter by code.
- A "How to fix" tips section covering the most common ERC/DRC violations.
- Print-friendly CSS — open in browser and Ctrl+P for a PDF.

Download from **Actions → the failed run → Artifacts → `error-report`** and open `error-report.html` locally.

---

## Local development tips

- Run the same KiBot config locally before pushing:
  ```bash
  docker run --rm -v "$PWD:/work" -w /work \
    ghcr.io/inti-cmnb/kicad8_auto_full:latest \
    kibot -c config/kibot-full.yaml -d output \
          -e hardware/Nano-Board-rev-2.kicad_sch \
          -b hardware/Nano-Board-rev-2.kicad_pcb
  ```
- Test the error report generator locally:
  ```bash
  python3 config/generate_error_report.py \
    --erc-json output/reports/erc.json \
    --drc-json output/reports/drc.json \
    --output error-report.html
  ```

---

## Editing the pipeline

- **Add an output:** edit `config/kibot-full.yaml`, push to a feature branch, watch the Stage 2 PR show it in artifacts.
- **Change ERC/DRC severity:** in `config/kibot-full.yaml`, set `erc_warnings: true` or `drc_warnings: true` to fail on warnings as well as errors.
- **Skip a noisy violation:** add it to the `filters:` block in `config/kibot-full.yaml`.
- **Use a different project:** change `KICAD_PROJECT` (and `KICAD_PROJECT_DIR` if needed) at the top of each workflow.
