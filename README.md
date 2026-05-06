<!--PCB_BLOCK-->
<!--/PCB_BLOCK-->

***

## DIRECTORY STRUCTURE

    .
    ├─ .github/workflows  # CI pipeline (feature push, PR gates, release)
    ├─ HTML               # Generated reports / Pages site (CI output)
    ├─ config             # KiBot YAML configs and report templates
    │  ├─ kibot           # Orchestrator + per-output YAMLs
    │  └─ web             # Themed CSS and 3D viewer template
    ├─ docs               # Project images and documentation assets
    ├─ hardware           # KiCad project (source of truth)
    ├─ manufacturing      # Auto-generated fabrication artifacts
    └─ scripts            # Helper scripts (rename project, GLB export)

<p align="center" width="100%">
  <img alt="Logo" width="33%" src="docs/Kicad_Template.png">
</p>

<h1 align="center"><!--REPO_NAME-->Kicad_Template<!--/REPO_NAME--></h1>
