#!/usr/bin/env python3
"""
convert_to_glb.py

Export a KiCad PCB to a browser-ready GLB (binary glTF) for the
Three.js viewer at config/web/3d-viewer.html.

Thin wrapper around `kicad-cli pcb export glb`. PCB->GLB is a single
step in modern KiCad (>=8) and produces correct materials (green
solder mask, gold pads, white silkscreen) without needing an
intermediate STEP file.

Usage:
    # Auto-discover the PCB under hardware/ and write to output/3d/<name>.glb
    python scripts/convert_to_glb.py

    # Explicit paths
    python scripts/convert_to_glb.py \
        --pcb hardware/Nano-Board-rev-2.kicad_pcb \
        --output output/3d/Nano-Board-rev-2.glb
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_pcb(repo_root: Path) -> Path | None:
    candidates = sorted((repo_root / "hardware").glob("*.kicad_pcb"))
    return candidates[0] if candidates else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pcb", type=Path, default=None,
                   help="Path to .kicad_pcb. Defaults to first match under hardware/.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output .glb path. Defaults to output/3d/<pcb-stem>.glb.")
    p.add_argument("--include-tracks", action="store_true", default=True,
                   help="Include copper tracks in the export (default: true).")
    p.add_argument("--include-zones", action="store_true", default=True,
                   help="Include filled zones / copper pours (default: true).")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    pcb: Path = args.pcb or find_pcb(repo_root)
    if not pcb or not pcb.exists():
        print(f"error: no .kicad_pcb found (looked under {repo_root/'hardware'})",
              file=sys.stderr)
        return 1

    out: Path = args.output or (repo_root / "output" / "3d" / f"{pcb.stem}.glb")
    out.parent.mkdir(parents=True, exist_ok=True)

    if not shutil.which("kicad-cli"):
        print("error: kicad-cli not on PATH", file=sys.stderr)
        return 2

    cmd = [
        "kicad-cli", "pcb", "export", "glb",
        "--include-tracks",
        "--include-zones",
        "--subst-models",
        "-o", str(out),
        str(pcb),
    ]
    print("running:", " ".join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        return res.returncode

    size = out.stat().st_size if out.exists() else 0
    print(f"wrote {out} ({size/1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
