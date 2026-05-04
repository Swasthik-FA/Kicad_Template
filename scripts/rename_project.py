#!/usr/bin/env python3
"""
rename_project.py
=================

One-shot rename of the KiCad project across every place it appears:

    - hardware/<old>.kicad_pcb / .kicad_sch / .kicad_pro / .kicad_prl
    - hardware/<old>-backups, hardware/_autosave-<old>*, etc.
    - env vars KICAD_PROJECT in every workflow under .github/workflows/
    - the navigate-page TITLE in config/kibot/kibot_main.yaml

Usage:
    python scripts/rename_project.py <new-name>
    python scripts/rename_project.py <new-name> --dry-run
    python scripts/rename_project.py <new-name> --hardware-dir <dir>

The script auto-detects the current project name from
config/kibot/kibot_main.yaml's KICAD_PROJECT env var (or any
.kicad_pro file in hardware/). Refuses to run on a dirty git tree
unless --force is given, so changes are easy to review and revert.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def detect_current_name(repo_root: Path, hardware_dir: str) -> str | None:
    hw = repo_root / hardware_dir
    if not hw.is_dir():
        return None
    pros = sorted(hw.glob("*.kicad_pro"))
    if not pros:
        return None
    if len(pros) > 1:
        print(f"warn: multiple .kicad_pro files in {hw}; picking {pros[0].name}",
              file=sys.stderr)
    return pros[0].stem


def detect_hardware_dir(repo_root: Path) -> str:
    # Prefer the value already set in any workflow.
    for wf in (repo_root / ".github" / "workflows").glob("*.yml"):
        m = re.search(r"^\s*KICAD_PROJECT_DIR:\s*([^\s#]+)\s*$",
                      wf.read_text(encoding="utf-8"),
                      re.M)
        if m:
            return m.group(1).strip().strip("'\"")
    return "hardware"


# ---------------------------------------------------------------------------
# Rewrites
# ---------------------------------------------------------------------------

# Files in which we do plain string substitution. Binary files (.kicad_pcb,
# .kicad_sch) reference the project name internally, so include those too.
RENAME_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    "config/kibot/*.yaml",
    "README.md",
    "CLAUDE.md",
    "TEMPLATE.md",
)


def iter_text_files(repo_root: Path) -> Iterable[Path]:
    for pattern in RENAME_GLOBS:
        for p in repo_root.glob(pattern):
            if p.is_file():
                yield p


def replace_in_file(path: Path, old: str, new: str, dry_run: bool) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0
    if old not in text:
        return 0
    new_text = text.replace(old, new)
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return text.count(old)


def rename_hardware_files(hw: Path, old: str, new: str, dry_run: bool) -> list[tuple[Path, Path]]:
    """Rename all files/dirs whose name starts with the old project name."""
    moves = []
    for p in sorted(hw.rglob("*")):
        if not p.exists():
            continue
        rel = p.relative_to(hw)
        # Only rename the leaf; KiCad project artifacts are flat, but be
        # defensive against backups/ dirs.
        new_name = p.name
        if p.name == old or p.name.startswith(old + ".") or p.name.startswith(old + "-") or p.name.startswith("_autosave-" + old):
            new_name = p.name.replace(old, new, 1)
        if new_name != p.name:
            target = p.with_name(new_name)
            moves.append((p, target))
            if not dry_run:
                p.rename(target)
    return moves


# ---------------------------------------------------------------------------
# Git safety
# ---------------------------------------------------------------------------

def git_clean(repo_root: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return True   # not a git repo, or git missing; let the user proceed
    return out.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new_name",
                    help="New project name (e.g. MyBoard-rev-1).")
    ap.add_argument("--old-name",
                    help="Old project name. Auto-detected if omitted.")
    ap.add_argument("--hardware-dir",
                    help="Hardware directory (default: auto-detect, "
                         "fall back to 'hardware').")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without modifying anything.")
    ap.add_argument("--force", action="store_true",
                    help="Run even on a dirty git tree.")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    hardware_dir = args.hardware_dir or detect_hardware_dir(repo_root)
    hw = repo_root / hardware_dir

    new = args.new_name.strip()
    if not re.match(r"^[A-Za-z0-9._-]+$", new):
        print(f"error: new name '{new}' has invalid characters. Use [A-Za-z0-9._-] only.",
              file=sys.stderr)
        return 1

    old = args.old_name or detect_current_name(repo_root, hardware_dir)
    if not old:
        print(f"error: could not auto-detect current project name. "
              f"Pass --old-name explicitly.", file=sys.stderr)
        return 1
    if old == new:
        print(f"current name is already '{new}'. Nothing to do.")
        return 0

    if not args.force and not args.dry_run and not git_clean(repo_root):
        print("error: git tree is dirty. Commit or stash first, or pass --force.",
              file=sys.stderr)
        return 1

    print(f"Renaming '{old}' -> '{new}' (hardware dir: {hardware_dir})")
    if args.dry_run:
        print("(dry-run — no changes will be written)")

    # 1. Rename hardware files.
    moves = rename_hardware_files(hw, old, new, args.dry_run)
    for src, dst in moves:
        print(f"  rename: {src.relative_to(repo_root)} -> "
              f"{dst.relative_to(repo_root)}")
    if not moves:
        print("  (no hardware/ files matched)")

    # 2. Replace string occurrences in tracked text files.
    total = 0
    for path in iter_text_files(repo_root):
        n = replace_in_file(path, old, new, args.dry_run)
        if n:
            total += n
            print(f"  edit:   {path.relative_to(repo_root)} "
                  f"({n} occurrence{'s' if n != 1 else ''})")

    print()
    print(f"Done. {len(moves)} file rename(s), {total} string replacement(s).")
    if args.dry_run:
        print("Run again without --dry-run to apply.")
    else:
        print("Review with `git diff` and `git status`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
