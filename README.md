<!--PCB_BLOCK-->
<table align="center">
  <tr>
    <td align="center">
      <img alt="Front" src="HTML/3d/Nano-Board-rev-2-3d-top.png" width="380">
      <br><sub><b>Front</b></sub>
    </td>
    <td align="center">
      <img alt="Back" src="HTML/3d/Nano-Board-rev-2-3d-bottom.png" width="380">
      <br><sub><b>Back</b></sub>
    </td>
  </tr>
</table>

***

## SPECIFICATIONS

| Parameter | Value |
| --- | --- |
| Dimensions | 125.74 x 53.08 mm |
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
