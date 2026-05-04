#!/usr/bin/env python3
"""
convert_to_glb.py
=================

Produces a browser-compatible GLB (binary glTF) for the project's PCB,
ready to embed in <model-viewer> on the navigate_3d page.

Conversion path
---------------
Calls `kicad-cli pcb export glb` directly on the .kicad_pcb. We do NOT
go via the intermediate .step file: kicad-cli's PCB->GLB export is
tighter (preserves copper, zones, mounted 3D models, layer colours)
and uses the same OCC backend a STEP->GLB tool would. PCB->GLB is a
single CLI hop with no extra dependencies in the kicad_auto:ki9 image.

Usage
-----
    # Auto-discover the PCB under hardware/ and write to HTML/3d/<name>.glb
    python scripts/convert_to_glb.py

    # Explicit paths
    python scripts/convert_to_glb.py \
        --pcb hardware/Nano-Board-rev-2.kicad_pcb \
        --output HTML/3d/Nano-Board-rev-2.glb

The script is intended to run after KiBot's full group has populated
output/. CI should call it on every push that updates HTML/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_pcb(repo_root: Path) -> Path | None:
    for hw in ("hardware", "pcb", "."):
        d = repo_root / hw
        if d.is_dir():
            candidates = sorted(d.glob("*.kicad_pcb"))
            if candidates:
                return candidates[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", type=Path,
                    help="Input .kicad_pcb. Auto-detected if omitted.")
    ap.add_argument("--output", type=Path,
                    help="Output .glb path. Defaults to HTML/3d/<pcb-stem>.glb.")
    ap.add_argument("--no-tracks", action="store_true",
                    help="Skip copper tracks in the model (smaller file).")
    ap.add_argument("--no-zones", action="store_true",
                    help="Skip filled zones in the model.")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    pcb: Path = args.pcb or find_pcb(repo_root)
    if pcb is None:
        print("error: could not auto-detect .kicad_pcb. Pass --pcb explicitly.",
              file=sys.stderr)
        return 1
    if not pcb.exists():
        print(f"error: PCB file not found: {pcb}", file=sys.stderr)
        return 1

    out: Path = args.output or (repo_root / "HTML" / "3d" / f"{pcb.stem}.glb")
    out.parent.mkdir(parents=True, exist_ok=True)

    if not shutil.which("kicad-cli"):
        print("error: `kicad-cli` is not on PATH. Install KiCad 9 (or run "
              "this inside the kicad_auto:ki9 Docker image).",
              file=sys.stderr)
        return 1

    cmd = [
        "kicad-cli", "pcb", "export", "glb",
        "--subst-models",
        "-o", str(out),
    ]
    if not args.no_tracks:
        cmd.append("--include-tracks")
    if not args.no_zones:
        cmd.append("--include-zones")
    cmd.append(str(pcb))

    print(f"$ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"error: kicad-cli failed with exit code {exc.returncode}",
              file=sys.stderr)
        return exc.returncode

    if not out.exists():
        print(f"error: kicad-cli reported success but {out} is missing.",
              file=sys.stderr)
        return 1

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nWrote {out} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
