<p align="center" width="100%">
  <img alt="Logo" width="33%" src="Logos/dummy_logo.svg">
</p>

<h1 align="center">Board Name</h1>

<p align="center" width="100%">
  <a href="https://github.com/Swasthik-FA/Kicad_Template/actions/workflows/feature-push.yml">
    <img alt="CI Badge" src="https://github.com/Swasthik-FA/Kicad_Template/actions/workflows/feature-push.yml/badge.svg">
  </a>
</p>

<p align="center" width="100%">
    <img src="Images/dummy_image.png">
</p>

***

<table align="center">
  <tr>
    <td align="center">
      <img alt="Front" src="design/pcb/outputs/Images/Nano-Board-rev-2-3d-top.png" width="380">
      <br><sub><b>Front</b></sub>
    </td>
    <td align="center">
      <img alt="Back" src="design/pcb/outputs/Images/Nano-Board-rev-2-3d-bottom.png" width="380">
      <br><sub><b>Back</b></sub>
    </td>
  </tr>
</table>

***

## SPECIFICATIONS

| Parameter | Value | 
| --- | --- |
| Dimensions | 106.58 × 54.37 mm |

***

## DIRECTORY STRUCTURE

    .
    ├─ Computations       # Misc calculations
    ├─ HTML               # HTML files for generated webpage
    ├─ Images             # Pictures and renders
    │
    ├─ kibot_resources    # External resources for KiBot
    │  ├─ colors          # Color theme for KiCad
    │  ├─ fonts           # Fonts used in the project
    │  ├─ scripts         # External scripts used with KiBot
    │  └─ templates       # Templates for KiBot generated reports
    │
    ├─ kibot_yaml         # KiBot YAML config files
    ├─ KiRI               # KiRI (PCB diff viewer) files
    │
    ├─ lib                # KiCad footprint and symbol libraries
    │  ├─ 3d_models       # Component 3D models
    │  ├─ lib_fp          # Footprint libraries
    │  └─ lib_sym         # Symbol libraries
    │
    ├─ Logos              # Logos
    │
    ├─ Manufacturing      # Assembly and fabrication documents
    │  ├─ Assembly        # Assembly documents (BoM, pos, notes)
    │  │
    │  └─ Fabrication     # Fabrication documents (ZIP, notes)
    │     ├─ Drill Tables # CSV drill tables
    │     └─ Gerbers      # Gerbers
    │
    ├─ Report             # Reports for ERC/DRC
    ├─ Schematic          # PDF of schematic
    ├─ Templates          # Title block templates
    ├─ Testing
    │  └─ Testpoints      # Testpoints tables      
    │
    └─ Variants           # Outputs for assembly variants
